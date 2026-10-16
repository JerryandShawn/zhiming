"""Actual 8a7 decision contracts via real PostgreSQL/LangGraph, model only."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest

from mingjing_core.domain.consultation import InvalidAnswer
from tests import test_core_comparison_repairs as helpers

FIXTURE = Path(__file__).parent / 'fixtures/8a7_comparison_decision_inference_denials.json'
TRIGGER = '未作零成本、无损失或签约后可逆的推断'
RUN_EVIDENCE = []


class RecordedInferenceModel(helpers.RecordedComparisonModel):
    def __init__(self, evidence):
        super().__init__(evidence)
        self.patch = None

    def generate(self, **kwargs):
        purpose = kwargs['purpose']
        raw = self.sample['outputs']
        original = raw['synthesis']
        if self.patch is not None and purpose == 'synthesis':
            raw['synthesis'] = raw['repair']
        try:
            result = super().generate(**kwargs)
        finally:
            raw['synthesis'] = original
        if self.patch is not None and purpose in ('synthesis', 'repair'):
            result['output'].update(deepcopy(self.patch))
            self.outputs[purpose] = deepcopy(result['output'])
        return result


class Recorded8a7DecisionInferenceDenials(unittest.TestCase):
    def setUp(self):
        helpers.RecordedComparisonRepairs.setUp(self)
        self.evidence = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.model = RecordedInferenceModel(self.evidence)
        self.model.case_id = self.case
        self.service.model = self.model

    tearDown = helpers.RecordedComparisonRepairs.tearDown
    consult = helpers.RecordedComparisonRepairs.consult

    def run_by_operation(self, operation):
        with self.repo.connection() as connection:
            return connection.execute(helpers.sql.SQL('SELECT * FROM {} WHERE owner=%s AND operation_id=%s').format(
                self.repo.table('core_runs')), (self.owner, operation)).fetchone()

    def execute(self, operation, patch=None, invalid=False, issue=helpers.GUARANTEE_ISSUE):
        self.model.patch = patch
        before = len(self.model.calls)
        start = len(self.service.validation_attempts)
        try:
            if invalid:
                with self.assertRaises(InvalidAnswer) as caught:
                    self.consult(operation)
                self.assertEqual(caught.exception.code, 'REFERENCE_ERROR')
                current = self.run_by_operation(operation)
                self.assertIsNone(current['result'])
                self.assertEqual(self.service.validation_attempts[start:], [[issue]] * 2)
                result = None
            else:
                run, result = self.consult(operation)
                current = self.repo.fetch_run(self.owner, run['id'])
                self.assertTrue(result['validation']['valid'])
                self.assertEqual(self.service.validation_attempts[start:],
                    [[helpers.GUARANTEE_ISSUE], []] if patch is None else [[]])
            repaired = invalid or patch is None
            self.assertEqual((current['status'], current['calls'], current['call_limit'], current['repair_used']),
                ('failed' if invalid else 'succeeded', 3 if repaired else 2, 6, repaired))
            self.assertEqual(self.model.calls[before:],
                ['intake', 'synthesis', 'repair'] if repaired else ['intake', 'synthesis'])
            return current, result
        finally:
            RUN_EVIDENCE.append({'operation': operation, 'calls': self.model.calls[before:],
                'validation_attempts': self.service.validation_attempts[start:]})

    def test_complete_actual_draft_requires_repair_original_repair_commits_and_replays(self):
        before = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        sample = self.evidence['samples'][0]
        self.assertEqual(self.evidence['operator_observed_commit'], '8a7ca631b793a4d084a3cfc4830f36cb1ecb1f5d')
        self.assertTrue(self.evidence['synthetic_only'])
        self.assertIsNone(self.evidence['embedded_commit'])
        self.assertIsNone(self.evidence['source_verified_end'])
        self.assertEqual(self.evidence['source_batch_state'], 'running')
        for purpose, attempt in zip(('synthesis', 'repair'), sample['original_validation_attempts']):
            self.assertEqual(sample['outputs'][purpose], attempt['contract_output'])
            self.assertEqual(attempt['issues'], [helpers.GUARANTEE_ISSUE])
        facts = self.service.memory.facts(self.owner)
        current, result = self.execute('8a7-original-repair')
        for key, value in self.model.outputs['repair'].items():
            self.assertEqual(result[key], value)
        self.assertEqual(self.service.memory.facts(self.owner), facts)
        self.assertEqual(result['cited_claim_ids'], [])
        snapshot = self.service._record(self.owner, current['id'], 'snapshot')
        self.assertTrue(set(result['cited_fact_ids']) <= set(snapshot['fact_ids']))
        self.assertEqual(self.service._record(self.owner, current['id'], 'calculation')['claims'], [])
        replay, replay_result = self.consult('8a7-original-repair')
        self.assertEqual(replay['id'], current['id'])
        self.assertEqual(replay_result, result)
        self.assertEqual(len(self.model.calls), 3)
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), before)

    def test_actual_trigger_is_only_repair_guarantee_occurrence(self):
        self.model.patch = {'professional_appendix': self.evidence['samples'][0]['outputs']['repair']['professional_appendix'].replace(TRIGGER, '未作有利推断')}
        run, result = self.consult('8a7-isolated-trigger')
        current = self.repo.fetch_run(self.owner, run['id'])
        original_repair = deepcopy(self.model.outputs['synthesis'])
        original_repair['professional_appendix'] = self.evidence['samples'][0]['outputs']['repair']['professional_appendix']
        # Preserve the complete text; only production fact IDs are bound to
        # the synthetic snapshot by the model fixture adapter.
        for old, new in self.model.mapping.items():
            original_repair['professional_appendix'] = original_repair['professional_appendix'].replace(old, new)
        asserted = []
        def trace(frame, event, arg):
            if frame.f_code.co_name == 'guarantee_is_asserted' and event == 'return' and arg:
                asserted.append({'clause': frame.f_locals['clause'], 'term': frame.f_locals['assertion'].group(),
                    'source': frame.f_locals['source']})
            return trace
        sys.settrace(trace)
        try:
            issues = self.service._validate(self.owner, current, original_repair)
        finally:
            sys.settrace(None)
        RUN_EVIDENCE.append({'operation': 'original-repair-diagnostic', 'issues': issues, 'asserted': asserted})
        self.assertEqual(issues, [])
        self.assertEqual(asserted, [])

    def test_closed_prefix_list_and_noun_forms_commit_without_repair(self):
        index = 0
        for verb in ('未作', '未做'):
            for any_term in ('', '任何'):
                for de in ('', '的'):
                    for noun in ('推断', '假设'):
                        passage = verb + any_term + '零成本、无损失或签约后可逆' + de + noun
                        with self.subTest(passage=passage):
                            self.execute('8a7-finite-' + str(index), {'plain_summary': passage + '。'})
                        index += 1
        for index, passage in enumerate(('未做“零风险、完全可逆或无损失”的推断',
                '未作任何零风险、低成本和签约后可逆的假设',
                '本轮未作低价及零风险的推断', '未做任何“零风险”或“无损失”的假设')):
            with self.subTest(passage=passage):
                self.execute('8a7-list-' + str(index), {'plain_summary': passage + '。'})

    def test_each_existing_finite_term_can_only_join_the_closed_enumeration(self):
        current, result = self.execute('8a7-term-snapshot', {'plain_summary': TRIGGER + '。'})
        terms = ('零风险', '完全可逆', '没有任何损失', '无损失', '零损失', '零成本退出',
            '随时退出', '随时可退出', '随时无损退出', '随时可无损退出', '随时退款', '随时可退款',
            '零成本', '低成本', '零代价', '无风险', '可逆', '可承受', '可退款', '低价',
            '可无损退出', '可退出', '零费用', '免费', '可逆性', '签约后可逆')
        checked = []
        for term in terms:
            for passage in ('未作任何' + term + '、零风险的推断', '未做零风险、' + term + '的假设'):
                with self.subTest(passage=passage):
                    answer = {key: deepcopy(value) for key, value in self.model.outputs['synthesis'].items()}
                    answer['plain_summary'] = passage + '。'
                    self.assertEqual(self.service._validate(self.owner, current, answer), [])
                    checked.append(passage)
        RUN_EVIDENCE.append({'operation': 'finite-term-enumeration', 'checked': checked})

    def test_actual_promises_new_claims_and_arbitrary_insertions_remain_rejected(self):
        passages = ('核实阶段完全可逆', '在费用和退出条款核实前不缴费不签约则完全可逆',
            '核实行为本身完全可逆', '发消息/打电话不花钱、不承诺、随时可停止，是完全可逆的小行动',
            '未作A零风险的推断', '未做任何A无损失的假设', '未作零风险或A完全可逆的推断',
            '未作零风险报价的推断', '未作零风险或保证完全可逆的假设',
            '未作零风险和报名后完全可逆的推断', '未作零风险的推断依据', '未作零风险',
            '作零风险的推断', '做零风险的假设', '未作零风险的推断并确认付款无损失',
            '未作零风险的推断，但付款无损失', '未作零风险的假设。报名完全可逆',
            TRIGGER + '，实际上报名完全可逆', '未作说明，但付款无损失')
        for index, passage in enumerate(passages):
            with self.subTest(passage=passage):
                self.execute('8a7-arbitrary-' + str(index), {'plain_summary': passage + '。'}, invalid=True)

    def test_double_denials_and_whole_quoted_denials_remain_rejected(self):
        passage = '未做任何零风险、无损失或签约后可逆的假设'
        variants = [prefix + passage for prefix in ('不是', '并非', '不能说', '没有', '未曾', '尚未', '不会', '不应', '未',
            '不是：', '不能说：', '不是：“')]
        for opening, closing in (('“','”'), ('"','"'), ('‘','’'), ("'","'"), ('「','」'), ('『','』'), ('`','`')):
            variants += ['报告写着' + opening + passage + closing,
                '报告写着' + opening + '前文。' + passage + closing,
                '报告写着' + opening + '情况未知；' + passage + '。之后再决定' + closing,
                '报告写着' + opening + passage,
                '报告写着' + opening + '前文。' + passage]
        variants += [passage + '”不是事实', '不是“未作零风险的推断”', '不能“未做零风险的假设”']
        variants += ['报告写着“未做零风险的推断', '报告写着「前文。未作零风险的假设']
        for index, mutation in enumerate(variants):
            with self.subTest(mutation=mutation):
                self.execute('8a7-quoted-' + str(index), {'plain_summary': mutation + '。'}, invalid=True)

    def test_negative_fields_cannot_authorize_other_fields(self):
        patches = ({'explanation': '报名完全可逆。'}, {'professional_appendix': '付款无损失。'},
            {'caveats': ['付款零风险。']}, {'actions': ['报名完全可逆。']})
        for index, extra in enumerate(patches):
            with self.subTest(extra=extra):
                self.execute('8a7-cross-field-' + str(index), {'plain_summary': TRIGGER + '。', **extra}, invalid=True)
        options = deepcopy(self.evidence['samples'][0]['outputs']['repair']['decision_options'])
        options[0]['reversibility'] = '报名完全可逆。'
        self.execute('8a7-cross-option', {'plain_summary': TRIGGER + '。', 'decision_options': options}, invalid=True)

    def test_negative_current_and_saved_sources_cannot_support_positive_guarantees(self):
        literals = ('未作零成本、零风险、完全可逆或无损失的推断',
            '未做任何低成本、零风险、完全可逆或无损失的推断',
            '报告写着“情况未知；未做零风险、完全可逆或无损失的推断”',
            '未做A零风险或A完全可逆或A无损失的推断',
            '未作任何未知费用零风险或完全可逆或无损失的推断',
            '报告写着“未做零风险、完全可逆或无损失的推断')
        for index, literal in enumerate(literals):
            source = self.service.memory.receive(self.owner, content='请记住：' + literal,
                source_id='8a7-negative-' + str(index))
            receipt = self.service.memory.save_fact(self.owner, 'self', source['id'], literal,
                'background', operation_id='8a7-save-negative-' + str(index))
            self.assertEqual(receipt['write_status'], 'saved')
            current, _ = self.execute('8a7-saved-source-' + str(index), {'plain_summary': '付款零风险、完全可逆且无损失。'}, invalid=True)
            for promise in ('付款零风险。', '报名完全可逆。', '付款无损失。'):
                final = deepcopy(self.model.outputs['repair']); final['plain_summary'] = promise
                self.assertEqual(self.service._validate(self.owner, current, final), [helpers.GUARANTEE_ISSUE])
        for index, literal in enumerate(literals + ('未做任何低成本、零风险、完全可逆或无损失的假设',)):
            original = self.evidence['questions']['decision']
            self.evidence['questions']['decision'] += '\n' + literal
            try:
                current, _ = self.execute('8a7-current-source-' + str(index), {'plain_summary': '付款零风险、完全可逆且无损失。'}, invalid=True)
                for promise in ('付款零风险。', '报名完全可逆。', '付款无损失。'):
                    final = deepcopy(self.model.outputs['repair']); final['plain_summary'] = promise
                    self.assertEqual(self.service._validate(self.owner, current, final), [helpers.GUARANTEE_ISSUE])
            finally:
                self.evidence['questions']['decision'] = original

    def test_save_and_reference_errors_keep_independent_rejection(self):
        for index, (extra, issue) in enumerate((
                ({'professional_appendix': '资料已长期保存。'}, helpers.SAVE_ISSUE),
                ({'cited_fact_ids': ['fact_outside_synthetic_snapshot']}, '引用了本轮有效范围之外的事实'),
                ({'cited_claim_ids': ['claim_outside_synthetic_calculation']}, '引用了未通过规则核验的声明'))):
            self.execute('8a7-independent-' + str(index), {'plain_summary': TRIGGER + '。', **extra}, invalid=True, issue=issue)


if __name__ == '__main__': unittest.main()
