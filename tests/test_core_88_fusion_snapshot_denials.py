"""Exact synthetic 88 fusion outputs through real PG, charts and LangGraph.

Only model outputs are substituted. Fact IDs bind by the original owner and
source spans; claim IDs bind only after the actual rule and features match.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from mingjing_core.domain.consultation import InvalidAnswer
from mingjing_core.repositories.postgres import fingerprint
from tests import test_core_76b_provider_denials as providers

FIXTURE = Path(__file__).parent / 'fixtures' / '88_fusion_snapshot_denials.json'
FIXTURE_SHA256 = '46ffddce901070f5dfe167112cadf7fb98e4ba6919d25403822a0ec547760771'
ORIGINAL_OWNER = 'provider_eval_669a196a5a25424f'
SYMBOLIC = '象征解释被提升为现实确定性或概率'
PROFILE = {'gender': '男', 'birth.solar_datetime': '1990-05-03 13:18',
           'birth.location.lng': 104.07, 'birth.location.lat': 30.67,
           'birth.timezone_offset': 8, 'birth.precision': 'exact'}
DENIALS = ('八字仅正午快照，未证明整日不换日柱',
           '八字仅采用正午快照，未证明整日不更换日柱')
QUESTION = '请把八字、紫微和西方星盘在2026-10-11的学习主题下对照，说明差异与缺失，不能提供事件概率。'
RUN_EVIDENCE = []


def original_profile_ids():
    text = '请保存我已核对并确认的合成出生资料：\n' + '\n'.join(
        f'{field}：{value}' for field, value in PROFILE.items())
    source = 'msg_' + fingerprint([ORIGINAL_OWNER, 'web', 'synthetic-profile', 'user'])[:32]
    result = {}
    for field, value in PROFILE.items():
        quote = f'{field}：{value}'; start = text.index(quote)
        ident = 'fact_' + fingerprint([ORIGINAL_OWNER, source, start, start + len(quote),
                                      'profile', None, field, value])[:32]
        result[ident] = field
    return result


def original_constraint_id():
    text = '请记住：我不能上夜班。请帮我考虑白天的学习安排。'
    quote = '我不能上夜班'; start = text.index(quote)
    source = 'msg_' + fingerprint([ORIGINAL_OWNER, 'web', 'evaluate:memory', 'user'])[:32]
    return 'fact_' + fingerprint([ORIGINAL_OWNER, source, start, start + len(quote),
                                 'constraint', None, None, None])[:32]


class RecordedFusionModel:
    def __init__(self, evidence, *, unsafe_review=False):
        self.evidence = evidence
        self.unsafe_review = unsafe_review
        self.mapping = {}; self.calls = []; self.outputs = {}
        self.original_fields = original_profile_ids()
        self.original_constraint = original_constraint_id()
        for phase in ('synthesis', 'review', 'model:repair'):
            assert set(evidence['outputs'][phase]['output']['cited_fact_ids']) <= set(self.original_fields) | {self.original_constraint}

    def bind(self, value):
        if isinstance(value, dict): return {key: self.bind(item) for key, item in value.items()}
        if isinstance(value, list): return [self.bind(item) for item in value]
        if isinstance(value, str):
            for old, new in self.mapping.items(): value = value.replace(old, new)
        return value

    def generate(self, **kwargs):
        purpose = kwargs['purpose']; self.calls.append(purpose)
        data = kwargs['payload']['reference_data']
        if data.get('facts'):
            for old, field in self.original_fields.items():
                matches = [f for f in data['facts'] if f.get('field') == field and f.get('value') == PROFILE[field]]
                assert len(matches) == 1
                self.mapping[old] = matches[0]['id']
            matches = [f for f in data['facts'] if f.get('kind') == 'constraint' and f['content'] == '我不能上夜班']
            assert len(matches) == 1
            self.mapping[self.original_constraint] = matches[0]['id']
        if data.get('claims'):
            for old in self.evidence['outputs']['calculation']['output']['claims']:
                if purpose.startswith('specialist:') and old['system'] != purpose.split(':')[1]: continue
                matches = [c for c in data['claims'] if all(c[k] == old[k]
                           for k in ('system', 'rule_id', 'time_scale'))]
                assert len(matches) == 1
                assert [r['value'] for r in matches[0]['feature_refs']] == [r['value'] for r in old['feature_refs']]
                self.mapping[old['claim_id']] = matches[0]['claim_id']
        if purpose == 'intake':
            output = {'plan': deepcopy(self.evidence['outputs']['plan']['output']),
                      'proposals': [], 'retire_fact_ids': []}
        elif purpose.startswith('specialist:'):
            output = deepcopy(next(s for s in self.evidence['outputs']['specialists']['output']['specialists']
                                   if s['system'] == purpose.split(':')[1]))
        else:
            phase = 'model:repair' if purpose == 'repair' else purpose
            output = deepcopy(self.evidence['outputs'][phase]['output'])
            if purpose == 'review' and self.unsafe_review:
                output['plain_summary'] += '八字证明你一定学习成功。'
        output = self.bind(output); self.outputs[purpose] = deepcopy(output)
        return {'output': output, 'usage': {'input_tokens': 1, 'output_tokens': 1},
                'model': 'synthetic-original-88-fusion'}


class FusionSnapshotDenialsPG(unittest.TestCase):
    tearDown = providers.Provider76bDenialRegression.tearDown
    run_for = providers.Provider76bDenialRegression.run_for

    def setUp(self):
        providers.Provider76bDenialRegression.setUp(self)
        self.addCleanup(lambda: self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), FIXTURE_SHA256))
        self.evidence = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.assertEqual(self.evidence['commit'], '88f30cc113ab2fba203a77576eb633e2655ae6b8')
        self.assertTrue(self.evidence['synthetic_only'])
        self.assertEqual((self.evidence['calls'], self.evidence['limit'], self.evidence['repair_used']), (7, 10, True))

    def record(self, operation, row):
        RUN_EVIDENCE.append({'operation': operation, 'status': row['status'], 'calls': row['calls'],
            'limit': row['call_limit'], 'repair_used': row['repair_used'],
            'validation_attempts': deepcopy(self.service.validation_attempts), 'fixture_sha256': FIXTURE_SHA256})

    def fusion(self, operation, *, unsafe_review=False):
        self.model = RecordedFusionModel(self.evidence, unsafe_review=unsafe_review)
        self.service.model = self.model
        run = self.service.submit(owner=self.owner, message=QUESTION, request_id=operation, depth='deep')
        result = self.service.execute(self.owner, run['id'])
        row = self.repo.fetch_run(self.owner, run['id']); self.record(operation, row)
        self.assertEqual((row['status'], row['calls'], row['call_limit'], row['repair_used']),
                         ('succeeded', 7 if unsafe_review else 6, 10, unsafe_review))
        self.assertEqual(self.model.calls, ['intake', 'specialist:bazi', 'specialist:ziwei', 'specialist:astro',
                         'synthesis', 'review'] + (['repair'] if unsafe_review else []))
        self.assertEqual(self.service.execute(self.owner, run['id']), result)
        self.assertTrue(result['validation']['valid'])
        calculation = self.service._record(self.owner, run['id'], 'calculation')
        self.assertEqual({c['system'] for c in calculation['claims']}, {'bazi', 'ziwei', 'astro'})
        self.assertTrue(self.service.knowledge.revalidate_claims(calculation['calculation'], calculation['claims'])['eligible'])
        self.assertTrue(set(result['cited_fact_ids']) <= {f['id'] for f in self.service.memory.facts(self.owner)})
        self.assertTrue(set(result['cited_claim_ids']) <= {c['claim_id'] for c in calculation['claims']})
        return row, result

    def test_full_original_synthesis_review_and_repair_prose_validate_unchanged(self):
        row, result = self.fusion('original-88-fusion')
        self.assertEqual(self.service.validation_attempts, [[]])
        self.assertEqual(result['plain_summary'], self.model.outputs['review']['plain_summary'])
        for phase in ('synthesis', 'review', 'model:repair'):
            raw = self.evidence['outputs'][phase]['output']
            self.assertEqual(self.service._validate(self.owner, row, self.model.bind(deepcopy(raw))), [])
            self.assertEqual(self.model.bind(raw['caveats']), raw['caveats'])

    def test_new_unsafe_review_consumes_one_repair_and_original_repair_commits(self):
        row, result = self.fusion('forced-88-repair', unsafe_review=True)
        self.assertEqual(self.service.validation_attempts, [[SYMBOLIC], []])
        self.assertEqual(result['plain_summary'], self.model.outputs['repair']['plain_summary'])
        self.assertEqual(row['calls'], 7)

    def consult_local(self, passage, operation, *, unsafe=False):
        self.service.model = providers.LocalAnswerModel(passage)
        start = len(self.service.validation_attempts)
        run = self.service.submit(owner=self.owner, message='仅按现实费用、班次和退出规则讨论，不排盘。',
                                  request_id=operation)
        if unsafe:
            with self.assertRaises(InvalidAnswer): self.service.execute(self.owner, run['id'])
        else:
            result = self.service.execute(self.owner, run['id']); self.assertTrue(result['validation']['valid'])
        row = self.repo.fetch_run(self.owner, run['id']); self.record(operation, row)
        self.assertEqual((row['status'], row['calls'], row['repair_used']),
                         ('failed', 3, True) if unsafe else ('succeeded', 2, False))
        if unsafe:
            self.assertIsNone(row['result'])
            self.assertTrue(all(SYMBOLIC in issues for issues in self.service.validation_attempts[start:]))

    def test_exact_finite_snapshot_denials_need_no_repair(self):
        for index, passage in enumerate(DENIALS):
            with self.subTest(passage=passage): self.consult_local(passage + '。', 'safe-88-' + str(index))

    def test_positive_double_denial_quotes_and_cross_clause_assertions_fail(self):
        passages = [
            '八字仅正午快照，证明整日不换日柱。',
            '八字仅采用正午快照，已经证明整日不更换日柱。',
            '八字证明学习成功率100%。',
            '八字仅正午快照，未证明整日不换日柱且保证成功。',
            '八字仅正午快照，未证明整日不换日柱，但八字证明学习成功。',
            '八字仅正午快照，未证明整日不换日柱。星盘保证学习成功。',
            '未证明整日不换日柱，八字证明学习成功。',
            '八字仅正午快照，未证明整日不换日柱，实际已经证明整日稳定。',
        ]
        for denial in DENIALS:
            passages += [prefix + denial + '。' for prefix in ('不是', '并非', '不能说', '不意味着', '不代表', '不能', '无法', '不', '未')]
            for opening, closing in (('“', '”'), ('"', '"'), ('‘', '’'), ("'", "'"), ('「', '」'), ('『', '』'), ('`', '`')):
                passages += ['材料称' + opening + denial + closing + '。',
                             '不是' + opening + denial + closing + '。',
                             '材料称' + opening + denial + '。']
        for index, passage in enumerate(passages):
            with self.subTest(passage=passage): self.consult_local(passage, 'unsafe-88-' + str(index), unsafe=True)

    def test_safe_caveat_cannot_excuse_a_positive_in_another_field(self):
        class CrossFieldModel(providers.LocalAnswerModel):
            def generate(self, **kwargs):
                response = super().generate(**kwargs)
                if kwargs['purpose'] != 'intake':
                    response['output']['professional_appendix'] = '八字证明学习成功。'
                return response
        self.service.model = CrossFieldModel(DENIALS[0] + '。')
        run = self.service.submit(owner=self.owner, message='只按现实条件讨论。', request_id='88-cross-field')
        with self.assertRaises(InvalidAnswer): self.service.execute(self.owner, run['id'])
        row = self.repo.fetch_run(self.owner, run['id']); self.record('88-cross-field', row)
        self.assertEqual((row['status'], row['calls'], row['repair_used']), ('failed', 3, True))
        self.assertIn(SYMBOLIC, self.service.validation_attempts[-1])


if __name__ == '__main__': unittest.main()
