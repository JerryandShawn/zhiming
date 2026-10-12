"""Actual in-progress 88 comparison contracts through real PG and LangGraph.

Only the model is substituted. The draft contains real promises; the complete
repair contains closed denials. The source is not a sealed batch or commit proof.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from mingjing_core.domain.consultation import InvalidAnswer
from tests import test_core_comparison_repairs as helpers


FIXTURE = Path(__file__).parent / 'fixtures' / '88_comparison_decision_denials.json'
SAFE = (
    '因此不存在零成本、零风险或完全可逆的路径',
    '不把未知退出条件解释为无损失退出',
    '未把未知班次、费用、退出条件或时限推断为有利、零成本、零风险或完全可逆',
    '不能假设费用可接受或退出无损失',
)
RUN_EVIDENCE = []


class Recorded88Model(helpers.RecordedComparisonModel):
    def __init__(self, evidence):
        super().__init__(evidence)
        self.patch = None

    def generate(self, **kwargs):
        self.final_patch = self.patch['plain_summary'] if self.patch else None
        result = super().generate(**kwargs)
        if self.patch and kwargs['purpose'] in ('synthesis', 'repair'):
            result['output'].update(deepcopy(self.patch))
            self.outputs[kwargs['purpose']] = deepcopy(result['output'])
        return result


class Recorded88ComparisonDecisionDenials(unittest.TestCase):
    def setUp(self):
        helpers.RecordedComparisonRepairs.setUp(self)
        self.evidence = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.model = Recorded88Model(self.evidence)
        self.model.case_id = self.case
        self.service.model = self.model

    tearDown = helpers.RecordedComparisonRepairs.tearDown
    consult = helpers.RecordedComparisonRepairs.consult

    def execute(self, operation, *, patch=None, invalid=False):
        self.model.patch = patch
        before = len(self.model.calls)
        start = len(self.service.validation_attempts)
        try:
            if invalid:
                with self.assertRaises(InvalidAnswer) as caught:
                    self.consult(operation)
                self.assertEqual(caught.exception.code, 'REFERENCE_ERROR')
                with self.repo.connection() as connection:
                    current = connection.execute(helpers.sql.SQL(
                        'SELECT * FROM {} WHERE owner=%s AND operation_id=%s').format(
                            self.repo.table('core_runs')), (self.owner, operation)).fetchone()
                self.assertIsNone(current['result'])
                self.assertEqual(self.service.validation_attempts[start:],
                    [[helpers.GUARANTEE_ISSUE], [helpers.GUARANTEE_ISSUE]])
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
            RUN_EVIDENCE.append({'operation': operation,
                'calls': self.model.calls[before:],
                'validation_attempts': self.service.validation_attempts[start:]})

    def test_complete_actual_draft_requires_repair_original_repair_commits_and_replays(self):
        before = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        sample = self.evidence['samples'][0]
        self.assertTrue(self.evidence['synthetic_only'])
        self.assertEqual(self.evidence['operator_observed_commit'], '88f30cc113ab2fba203a77576eb633e2655ae6b8')
        self.assertIsNone(self.evidence['embedded_commit'])
        self.assertIsNone(self.evidence['source_verified_end'])
        self.assertEqual(self.evidence['source_batch_state'], 'running')
        self.assertEqual((sample['original_status'], sample['original_calls'], sample['original_error_code']),
            ('failed', 3, 'REFERENCE_ERROR'))
        self.assertEqual([x['issues'] for x in sample['original_validation_attempts']],
            [[helpers.GUARANTEE_ISSUE], [helpers.GUARANTEE_ISSUE]])
        self.assertEqual(sample['outputs']['synthesis'], sample['original_validation_attempts'][0]['contract_output'])
        self.assertEqual(sample['outputs']['repair'], sample['original_validation_attempts'][1]['contract_output'])
        facts = self.service.memory.facts(self.owner)
        current, result = self.execute('88-actual-repair')
        for key, value in self.model.outputs['repair'].items():
            self.assertEqual(result[key], value)
        self.assertEqual(self.service.memory.facts(self.owner), facts)
        self.assertEqual(result['cited_claim_ids'], [])
        snapshot = self.service._record(self.owner, current['id'], 'snapshot')
        self.assertTrue(set(result['cited_fact_ids']) <= set(snapshot['fact_ids']))
        calculation = self.service._record(self.owner, current['id'], 'calculation')
        self.assertEqual(calculation['claims'], [])
        self.assertTrue(self.service.knowledge.revalidate_claims(calculation['calculation'], [])['eligible'])
        replay, replay_result = self.consult('88-actual-repair')
        self.assertEqual(replay['id'], current['id'])
        self.assertEqual(replay_result, result)
        self.assertEqual(len(self.model.calls), 3)
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), before)

    def test_each_observed_closed_denial_commits_without_repair(self):
        for index, passage in enumerate(SAFE):
            with self.subTest(passage=passage):
                self.execute('88-finite-safe-' + str(index), patch={'plain_summary': passage + '。'})

    def test_actual_draft_promises_remain_rejected(self):
        promises = ('在签约付款前完全可逆', '纯询问阶段完全可逆，不产生承诺',
            '完全可逆，但仅指不承诺这一点')
        for index, passage in enumerate(promises):
            with self.subTest(passage=passage):
                self.execute('88-actual-promise-' + str(index),
                    patch={'plain_summary': passage + '。'}, invalid=True)

    def test_double_denials_quotes_and_renewed_guarantees_stay_rejected(self):
        for index, passage in enumerate(SAFE):
            mutations = ('不是' + passage, '不能说' + passage, '“' + passage + '”',
                '此前称“情况未知；' + passage + '。之后再决定”',
                '不能说：' + passage, passage + '，但报名完全可逆',
                passage + '。付款无损失', passage + '并保证报名无损失')
            for mutation_index, mutation in enumerate(mutations):
                with self.subTest(mutation=mutation):
                    self.execute('88-unsafe-' + str(index) + '-' + str(mutation_index),
                        patch={'plain_summary': mutation + '。'}, invalid=True)

    def test_new_objects_verbs_and_truncated_denials_stay_rejected(self):
        passages = ('因此存在零成本、零风险或完全可逆的路径',
            '不存在零成本、零风险或完全可逆的报名路径',
            '不把未知退出条件解释为保证无损失退出',
            '不把未知退款条件解释为无损失退出',
            '把未知退出条件解释为无损失退出',
            '未把未知班次、费用、退出条件或时限推断为有利、零成本、零风险或保证完全可逆',
            '未把未知班次、费用、退出条件或时限推断为有利、零成本、零风险或完全可逆并保证无损失',
            '不能假设费用可接受或退出保证无损失',
            '可以假设费用可接受或退出无损失')
        for index, passage in enumerate(passages):
            with self.subTest(passage=passage):
                self.execute('88-boundary-' + str(index),
                    patch={'plain_summary': passage + '。'}, invalid=True)

    def test_negative_fields_cannot_authorize_other_fields(self):
        for index, passage in enumerate(SAFE):
            with self.subTest(passage=passage):
                self.execute('88-cross-field-' + str(index),
                    patch={'plain_summary': passage + '。', 'professional_appendix': '报名完全可逆，付款无损失。'},
                    invalid=True)


if __name__ == '__main__': unittest.main()
