"""Full synthetic 9c outputs through real PG/Core/calculators/knowledge.

Only model responses are substituted; no service, rules or calculators are fake.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from mingjing_core.domain.consultation import InvalidAnswer
from tests import test_core_comparison_repairs as helpers
from tools.compare_core_providers import card_projection


FIXTURE = Path(__file__).parent / 'fixtures' / '9c_deep_tarot_denials.json'
GUARANTEE_ISSUE = helpers.GUARANTEE_ISSUE


class RecordedDeepTarotModel(helpers.RecordedComparisonModel):
    def __init__(self, evidence):
        super().__init__(evidence)
        self.unsafe_review = False
        self.invalid_reference = None
        self.repair_errors = []

    def generate(self, **kwargs):
        # The original helper binds only original evidence IDs to actual
        # current facts/claims from this real service's reference_data.
        response = super().generate(**kwargs)
        purpose = kwargs['purpose']
        if purpose == 'review' and self.unsafe_review:
            response['output']['plain_summary'] += '但当前报名完全可逆、无损失。'
        if purpose in ('synthesis', 'review', 'repair') and self.invalid_reference:
            field = 'cited_fact_ids' if self.invalid_reference == 'fact' else 'cited_claim_ids'
            response['output'][field].append('invented-synthetic-' + self.invalid_reference)
        if purpose == 'repair': self.repair_errors = deepcopy(kwargs['payload']['errors'])
        self.outputs[purpose] = deepcopy(response['output'])
        return response


class LocalGuaranteeModel:
    """Valid provider arrays use actual references; only tested wording varies."""
    def __init__(self, passage):
        self.passage = passage
        self.calls = []

    def generate(self, **kwargs):
        purpose = kwargs['purpose']; self.calls.append(purpose)
        data = kwargs['payload']['reference_data']
        if purpose == 'intake':
            output = {'plan': {'mode': 'decision', 'topic': 'career', 'systems': [],
                'target_date': '2026-10-11', 'time_scale': 'natal', 'decision': True,
                'rationale': '合成语法边界测试', 'missing_inputs': []},
                'proposals': [], 'retire_fact_ids': [], 'attachment_observations': []}
        else:
            output = {'plain_summary': self.passage, 'explanation': '实际费用和退出条件待核实。',
                'actions': ['核实书面班次与退出条件。'], 'decision_options': [
                    {'option': choice, 'benefit': '补齐现实条件后判断', 'cost': '投入核实时间',
                     'risk': '条件仍待确认', 'reversibility': '签约后的退出规则未知', 'first_step': '索取书面条件'}
                    for choice in ('先核实A', '先核实B')], 'follow_up': '收到答复后复盘。',
                'professional_appendix': '', 'cited_fact_ids': [f['id'] for f in data.get('facts', [])],
                'cited_claim_ids': [], 'caveats': []}
        return {'output': output, 'usage': {'input_tokens': 1, 'output_tokens': 1},
                'model': 'synthetic-local-negative-grammar'}


class DeepTarotNegativeDenialRegression(unittest.TestCase):
    def setUp(self):
        # Real isolated PG, authorized profile, selected case, two confirmed
        # facts and original history. No private production data is imported.
        helpers.RecordedComparisonRepairs.setUp(self)
        self.evidence = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.model = RecordedDeepTarotModel(self.evidence)
        self.model.case_id = self.case
        self.service.model = self.model

    tearDown = helpers.RecordedComparisonRepairs.tearDown

    def consult(self, operation):
        if self.draw is None:
            draw = self.service.tarot.create_draw(self.owner, subject_id='self', case_id=self.case,
                question=self.evidence['questions']['tarot'], spread_id='reflect3', draw_source='manual',
                manual_cards=self.evidence['fixed_cards'], idempotency_key='fixed-9c-deep-cards')['draw']
            self.draw = self.service.tarot.reveal(self.owner, draw['id'])
        run = self.service.submit(owner=self.owner, message=self.evidence['questions']['tarot'],
            conversation_id='synthetic-conversation', request_id=operation, case_ids=[self.case], depth='deep',
            selection={'date': '2026-10-11', 'systems': ['tarot', 'bazi', 'ziwei', 'astro']},
            draw_id=self.draw['id'])
        return run, self.service.execute(self.owner, run['id'])

    def bound(self, value):
        if isinstance(value, dict): return {key: self.bound(item) for key, item in value.items()}
        if isinstance(value, list): return [self.bound(item) for item in value]
        if isinstance(value, str):
            for old, new in self.model.mapping.items(): value = value.replace(old, new)
        return value

    def run_for(self, operation):
        with self.repo.connection() as connection:
            row = connection.execute(helpers.sql.SQL('SELECT id FROM {} WHERE owner=%s AND operation_id=%s').format(
                self.repo.table('core_runs')), (self.owner, operation)).fetchone()
        return self.repo.fetch_run(self.owner, row['id'])

    def guard_consult(self, passage, operation, message='只比较现实条件。不要排盘。'):
        provider = LocalGuaranteeModel(passage); self.service.model = provider
        run = self.service.submit(owner=self.owner, message=message, request_id=operation,
            case_ids=[self.case], depth='standard', selection={'systems': []})
        return run, self.service.execute(self.owner, run['id']), provider

    def test_full_original_synthesis_review_and_repair_keep_actual_evidence_and_cards(self):
        before = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        self.assertTrue(self.evidence['synthetic_only'])
        self.assertEqual(self.evidence['source_commit'], '9c46f7e3aa1f988dc7318d5ff597de2fab4925c0')
        self.assertEqual(self.evidence['original_calls'], 8)
        self.assertEqual(self.evidence['samples'][0]['original_validation_issues'], [[GUARANTEE_ISSUE], [GUARANTEE_ISSUE]])
        run, result = self.consult('full-9c-deep-original')
        current = self.repo.fetch_run(self.owner, run['id'])
        self.assertEqual((current['status'], current['calls'], current['call_limit'], current['repair_used']),
                         ('succeeded', 7, 10, False))
        self.assertEqual(self.model.calls, self.evidence['samples'][0]['original_purposes'][:-1])
        self.assertEqual(self.service.validation_attempts, [[]])
        self.assertTrue(result['validation']['valid'])
        self.assertEqual(result['explanation'], self.model.outputs['review']['explanation'])
        self.assertIn(self.model.outputs['review']['professional_appendix'], result['professional_appendix'])
        calculation = self.service._record(self.owner, run['id'], 'calculation')
        self.assertEqual({c['system'] for c in calculation['claims']}, {'tarot', 'bazi', 'ziwei', 'astro'})
        self.assertTrue(set(result['cited_claim_ids']) <= {c['claim_id'] for c in calculation['claims']})
        self.assertEqual(len(result['cited_claim_ids']), 7)
        self.assertEqual(self.service._validate(self.owner, current,
            self.bound(deepcopy(self.evidence['samples'][0]['outputs']['synthesis']))), [])
        full_repair = self.bound(deepcopy(self.evidence['samples'][0]['outputs']['repair']))
        self.assertEqual(self.service._validate(self.owner, current, full_repair), [])
        self.assertEqual(card_projection(self.service.tarot.get(self.owner, self.draw['id'])), self.evidence['fixed_cards'])
        self.assertEqual(self.service.execute(self.owner, run['id']), result)
        self.assertEqual(len(self.model.calls), 7)
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), before)

    def test_real_unsafe_review_then_full_original_repair_commits_with_eight_cumulative_calls(self):
        self.model.unsafe_review = True
        run, result = self.consult('unsafe-review-full-original-repair')
        current = self.repo.fetch_run(self.owner, run['id'])
        self.assertEqual((current['status'], current['calls'], current['call_limit'], current['repair_used']),
                         ('succeeded', 8, 10, True))
        self.assertEqual(self.model.calls, self.evidence['samples'][0]['original_purposes'])
        self.assertEqual(self.service.validation_attempts, [[GUARANTEE_ISSUE], []])
        self.assertIn(GUARANTEE_ISSUE, self.model.repair_errors)
        self.assertEqual(result['plain_summary'], self.model.outputs['repair']['plain_summary'])
        self.assertEqual(result['explanation'], self.model.outputs['repair']['explanation'])
        self.assertEqual(result['decision_options'], self.model.outputs['repair']['decision_options'])
        self.assertEqual(self.service.execute(self.owner, run['id']), result)
        self.assertEqual(len(self.model.calls), 8)

    def test_only_exact_adjacent_any_scheme_and_cannot_infer_exit_denials_pass(self):
        passages = ('不能宣称任何方案“完全可逆”或“无损失”。',
            '不能宣称任何方案无损失或完全可逆。', '不能推定退出无损失或完全可逆。',
            '不能推定退出“无损失”或“完全可逆”。')
        for index, passage in enumerate(passages):
            with self.subTest(passage=passage):
                run, result, provider = self.guard_consult(passage, 'tight-9c-deep-' + str(index))
                current = self.repo.fetch_run(self.owner, run['id'])
                self.assertEqual((current['status'], current['calls'], current['repair_used']), ('succeeded', 2, False))
                self.assertTrue(result['validation']['valid']); self.assertEqual(provider.calls, ['intake', 'synthesis'])

    def test_direct_positive_double_negative_nonadjacent_cross_clause_and_changed_object_fail(self):
        passages = ('任何方案完全可逆或无损失。', '推定退出无损失或完全可逆。',
            '不是不能宣称任何方案无损失。', '并非不能推定退出无损失。',
            '不能不推定退出无损失。', '不能说不是不能推定退出完全可逆。',
            '不能否认任何方案无损失。', '不可否认退出无损失。', '不排除退出无损失。',
            '不能宣称任何方案，但报名无损失。', '不能推定退出。报名无损失。',
            '不能宣称任何方案无损失，但报名完全可逆。',
            '不能推定退出无损失；事实上报名完全可逆。',
            '不能宣称任何方案无损失或保证完全可逆。',
            '不能推定退出无损失或保证完全可逆。',
            '不能宣称任何方案现在无损失。', '不能推定退出现在无损失。',
            '不能宣称任何某个方案无损失。', '不能推定报名无损失。',
            '不能推定退出任何合同现在无损失。')
        for index, passage in enumerate(passages):
            with self.subTest(passage=passage):
                operation = 'unsafe-9c-deep-' + str(index)
                with self.assertRaises(InvalidAnswer): self.guard_consult(passage, operation)
                current = self.run_for(operation)
                self.assertEqual((current['status'], current['calls'], current['repair_used']), ('failed', 3, True))
                self.assertIsNone(current['result'])
                self.assertEqual(self.service.validation_attempts[-2:], [[GUARANTEE_ISSUE], [GUARANTEE_ISSUE]])

    def test_denied_user_source_never_authorizes_a_positive_guarantee(self):
        for index, message in enumerate(('不要宣称任何方案无损失。', '不能推定退出无损失。')):
            with self.subTest(message=message):
                operation = 'negative-source-9c-deep-' + str(index)
                with self.assertRaises(InvalidAnswer):
                    self.guard_consult('实际报名无损失。', operation, message=message)
                self.assertEqual(self.run_for(operation)['status'], 'failed')
                self.assertEqual(self.service.validation_attempts[-1], [GUARANTEE_ISSUE])

    def test_original_denials_do_not_bypass_fact_or_claim_revalidation(self):
        for kind, issue in (('fact', '引用了本轮有效范围之外的事实'),
                            ('claim', '引用了未通过规则核验的声明')):
            with self.subTest(kind=kind):
                self.model = RecordedDeepTarotModel(self.evidence); self.model.case_id = self.case
                self.model.invalid_reference = kind; self.service.model = self.model
                operation = 'invalid-reference-9c-deep-' + kind
                with self.assertRaises(InvalidAnswer): self.consult(operation)
                current = self.run_for(operation)
                self.assertEqual((current['status'], current['calls'], current['repair_used']), ('failed', 8, True))
                self.assertIsNone(current['result']); self.assertIn(issue, self.service.validation_attempts[-1])


if __name__ == '__main__': unittest.main()
