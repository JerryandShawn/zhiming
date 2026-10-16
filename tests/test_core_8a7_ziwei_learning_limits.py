"""Original synthetic-profile provider output through actual PG/LangGraph/ziwei.

The diagnosis fixture is byte-for-byte original. Only opaque references are
rebound to the new isolated run; chart execution and all validators are real.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
import uuid

from mingjing_core.domain.consultation import InvalidAnswer
from tests import test_core_76b_provider_denials as helpers

FIXTURE = Path(__file__).parent / 'fixtures' / '8a7_ziwei_learning_limit_diagnosis.json'
FIXTURE_SHA256 = '674b13a040f2eef56b5235e90a23c82e3cd6468b64f2b40ccf0ea500742ed357'
SYMBOLIC = '象征解释被提升为现实确定性或概率'
ACTUAL_LIMIT = '命盘与流日象征仅供反思，不构成学习成效保证'
QUESTION = '请依据紫微命盘讨论2026-10-11的学习主题，保留专业字段和局限。'
STAGES = ('synthesis', 'review', 'model:repair')
RUN_EVIDENCE = []


class OriginalZiweiModel:
    def __init__(self, service, owner, evidence, *, unsafe=False, invalid=None):
        self.service = service
        self.owner = owner
        self.evidence = evidence
        self.unsafe = unsafe
        self.invalid = invalid
        self.run_id = None
        self.calls = []
        self.mapping = {}
        self.outputs = {}
        original = evidence['outputs']['synthesis']['output']['cited_fact_ids']
        facts = [f['id'] for f in service.memory.facts(owner) if f.get('kind') == 'profile']
        if len(original) != 6 or len(facts) != 6:
            raise AssertionError('Both runs must have the same six synthetic profile facts')
        # These are citation sets of the complete six-field profile, not
        # field-specific prose references. Do not replace any human wording.
        self.mapping.update(zip(sorted(original), sorted(facts)))

    def bind(self, value):
        if isinstance(value, dict): return {key: self.bind(item) for key, item in value.items()}
        if isinstance(value, list): return [self.bind(item) for item in value]
        if isinstance(value, str):
            for old, new in self.mapping.items(): value = value.replace(old, new)
        return value

    def generate(self, **kwargs):
        purpose = kwargs['purpose']; self.calls.append(purpose)
        if purpose != 'intake':
            actual = self.service._record(self.owner, self.run_id, 'calculation')
            original = self.evidence['outputs']['calculation']['output']
            for old in original['claims']:
                matches = [c for c in actual['claims'] if all(c[k] == old[k]
                    for k in ('system', 'rule_id', 'school_id', 'time_scale'))]
                if len(matches) != 1: raise AssertionError('No unique actual released ziwei rule')
                self.mapping[old['claim_id']] = matches[0]['claim_id']
            for category in ('artifacts', 'profiles'):
                old_ids = sorted(original['calculation'][category])
                new_ids = sorted(actual['calculation'][category])
                if len(old_ids) != 1 or len(new_ids) != 1:
                    raise AssertionError('One actual ziwei chart/profile is required')
                self.mapping.update(zip(old_ids, new_ids))
        if purpose == 'intake':
            output = {'plan': deepcopy(self.evidence['outputs']['plan']['output']),
                      'proposals': [], 'retire_fact_ids': [], 'attachment_observations': []}
        elif purpose == 'specialist:ziwei':
            output = self.bind(deepcopy(self.evidence['outputs']['specialists']['output']['specialists'][0]))
        else:
            stage = 'model:repair' if purpose == 'repair' else purpose
            output = self.bind(deepcopy(self.evidence['outputs'][stage]['output']))
            if purpose == 'synthesis' and self.unsafe:
                output['plain_summary'] += '命盘保证学习成功。'
            if self.invalid:
                field = 'cited_fact_ids' if self.invalid == 'fact' else 'cited_claim_ids'
                output[field].append('invented-synthetic-' + self.invalid)
        self.outputs[purpose] = deepcopy(output)
        return {'output': output, 'usage': {'input_tokens': 1, 'output_tokens': 1},
                'model': 'synthetic-original-8a7-ziwei-learning-limit'}


class ZiweiLearningLimitsPG(unittest.TestCase):
    setUp = helpers.Provider76bDenialRegression.setUp
    tearDown = helpers.Provider76bDenialRegression.tearDown

    def recorded(self, *, unsafe=False, invalid=None):
        evidence = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), FIXTURE_SHA256)
        self.assertTrue(evidence['synthetic_only'])
        self.assertEqual(evidence['commit'], '8a7ca631b793a4d084a3cfc4830f36cb1ecb1f5d')
        for stage in STAGES:
            self.assertEqual(evidence['outputs'][stage]['issues'], [SYMBOLIC])
            self.assertIn(ACTUAL_LIMIT, evidence['outputs'][stage]['output']['caveats'])
        model = OriginalZiweiModel(self.service, self.owner, evidence, unsafe=unsafe, invalid=invalid)
        self.service.model = model
        run = self.service.submit(owner=self.owner, message=QUESTION, request_id='8a7-ziwei-' + uuid.uuid4().hex)
        model.run_id = run['id']
        result = None
        try:
            result = self.service.execute(self.owner, run['id'])
        except InvalidAnswer:
            pass
        current = self.repo.fetch_run(self.owner, run['id'])
        issues = {stage: self.service._validate(self.owner, current,
            model.bind(deepcopy(evidence['outputs'][stage]['output']))) for stage in STAGES}
        RUN_EVIDENCE.append({'kind': 'original-ziwei', 'unsafe_synthesis': unsafe, 'invalid_reference': invalid,
            'status': current['status'], 'calls': current['calls'], 'limit': current['call_limit'],
            'repair_used': current['repair_used'], 'purposes': model.calls[:], 'original_stage_issues': issues})
        return run, current, result, model, issues

    def assert_actual_chart(self, run, result):
        calculation = self.service._record(self.owner, run['id'], 'calculation')
        self.assertEqual(calculation['calculation']['errors'], [])
        self.assertEqual({c['rule_id'] for c in calculation['claims']}, {'ziwei.daily.mutagen-structure.v1'})
        self.assertTrue(self.service.knowledge.revalidate_claims(calculation['calculation'], calculation['claims'])['eligible'])
        self.assertEqual(set(result['cited_fact_ids']), {f['id'] for f in self.service.memory.facts(self.owner)
            if f.get('kind') == 'profile'})
        self.assertEqual(set(result['cited_claim_ids']), {c['claim_id'] for c in calculation['claims']})
        self.assertTrue(result['validation']['valid'])
        self.assertEqual(len(self.service.memory.facts(self.owner)), 7)

    def test_full_original_three_stages_and_standard_replay_need_no_repair(self):
        run, current, result, model, issues = self.recorded()
        self.assertEqual(issues, {stage: [] for stage in STAGES})
        self.assertEqual((current['status'], current['calls'], current['call_limit'], current['repair_used']),
                         ('succeeded', 3, 6, False))
        self.assertEqual(model.calls, ['intake', 'specialist:ziwei', 'synthesis'])
        self.assertEqual(result['plain_summary'], model.outputs['synthesis']['plain_summary'])
        self.assert_actual_chart(run, result)
        self.assertEqual(self.service.execute(self.owner, run['id']), result)
        self.assertEqual(len(model.calls), 3)
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), FIXTURE_SHA256)

    def test_true_positive_synthesis_uses_exact_original_full_repair_once(self):
        run, current, result, model, issues = self.recorded(unsafe=True)
        self.assertEqual(issues, {stage: [] for stage in STAGES})
        self.assertEqual((current['status'], current['calls'], current['call_limit'], current['repair_used']),
                         ('succeeded', 4, 6, True))
        self.assertEqual(model.calls, ['intake', 'specialist:ziwei', 'synthesis', 'repair'])
        self.assertEqual(self.service.validation_attempts[:2], [[SYMBOLIC], []])
        self.assertEqual(result['plain_summary'], model.outputs['repair']['plain_summary'])
        self.assert_actual_chart(run, result)
        self.assertEqual(self.service.execute(self.owner, run['id']), result)
        self.assertEqual(len(model.calls), 4)

    def local(self, passage, *, extra=None, issue=None):
        model = helpers.LocalAnswerModel(passage)
        if extra:
            original_generate = model.generate
            def generate(**kwargs):
                response = original_generate(**kwargs)
                if kwargs['purpose'] != 'intake': response['output'].update(deepcopy(extra))
                return response
            model.generate = generate
        self.service.model = model
        run = self.service.submit(owner=self.owner, message='学习条件仍待核实，不排盘。',
            request_id='8a7-bounded-' + uuid.uuid4().hex)
        if issue:
            with self.assertRaises(InvalidAnswer) as caught: self.service.execute(self.owner, run['id'])
            self.assertEqual(caught.exception.code, 'REFERENCE_ERROR')
        else:
            result = self.service.execute(self.owner, run['id'])
            self.assertTrue(result['validation']['valid'])
        current = self.repo.fetch_run(self.owner, run['id'])
        self.assertEqual((current['status'], current['calls'], current['call_limit'], current['repair_used']),
            ('failed', 3, 6, True) if issue else ('succeeded', 2, 6, False))
        if issue:
            self.assertIsNone(current['result'])
            self.assertIn(issue, self.service.validation_attempts[-1])
        RUN_EVIDENCE.append({'kind': 'bounded-clause', 'passage': passage, 'extra': extra,
            'expected_issue': issue, 'status': current['status'], 'calls': current['calls'],
            'repair_used': current['repair_used']})

    def test_finite_synonyms_allow_only_optional_preposition_and_particle(self):
        for noun in ('学习效果', '学习成效', '学习成果'):
            for preposition in ('', '对'):
                for particle in ('', '的'):
                    with self.subTest(noun=noun, preposition=preposition, particle=particle):
                        self.local('命盘与流日象征仅供反思，不构成' + preposition + noun + particle + '保证。')
        self.local('命盘不构成对学习成效、成绩或他人动机的任何保证。')
        self.local('命盘不能构成学习成果保证。')

    def test_positive_double_denial_quotes_contrasts_and_unbounded_objects_stay_rejected(self):
        passages = (
            '命盘构成学习成效保证。', '命盘保证学习成果。',
            '命盘不是不构成学习成效保证。', '命盘并非不能构成学习成果保证。',
            '命盘不会不构成学习成效保证。', '命盘不应不构成学习成果保证。',
            '命盘没有不构成学习成效保证。', '命盘未曾不构成学习成果保证。',
            *(f'命盘{prefix}{space}不构成学习成效保证。'
              for prefix in ('不会', '不应', '没有', '未曾') for space in (' ', '\t')),
            '不是“命盘不构成学习成效保证”。', '“命盘不构成学习成效保证”。',
            '命盘“不构成学习成果保证”。', '命盘不能“不构成学习成果保证”。',
            '命盘不构成学习成效保证，但命盘保证成功。',
            '命盘不构成学习成效保证，但保证成功。',
            '命盘不构成学习成效保证。牌面保证成功。',
            '不构成学习成效。命盘保证成功。',
            '命盘不构成学习成效之外的任意内容保证。',
            '命盘不构成学习成效和投资收益的保证。',
            '命盘不构成投资收益保证。',
        )
        for passage in passages:
            with self.subTest(passage=passage): self.local(passage, issue=SYMBOLIC)

    def test_denial_in_another_field_cannot_authorize_a_new_positive(self):
        for field in ('explanation', 'professional_appendix', 'caveats'):
            value = ['命盘保证学习成果。'] if field == 'caveats' else '命盘保证学习成果。'
            with self.subTest(field=field): self.local(ACTUAL_LIMIT + '。', extra={field: value}, issue=SYMBOLIC)

    def test_original_prose_cannot_authorize_unknown_fact_or_claim_references(self):
        for reference in ('fact', 'claim'):
            with self.subTest(reference=reference):
                run, current, result, model, issues = self.recorded(invalid=reference)
                expected = '引用了本轮有效范围之外的事实' if reference == 'fact' else '引用了未通过规则核验的声明'
                self.assertEqual((current['status'], current['calls'], current['repair_used']), ('failed', 4, True))
                self.assertIsNone(result); self.assertIsNone(current['result'])
                self.assertEqual(self.service.validation_attempts[-4:-3], [[expected]])
                self.assertEqual(issues, {stage: [] for stage in STAGES})


if __name__ == '__main__': unittest.main()
