"""Original synthetic 5908 contracts through actual PG/Core/LangGraph.

Only provider responses are substituted. Original unsafe drafts must still
consume the single semantic repair; observed local denials supply no facts.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from mingjing_core.domain.consultation import InvalidAnswer
from tests import test_core_76b_provider_denials as providers
from tests import test_core_comparison_repairs as comparisons
from tools.compare_core_providers import card_projection

DECISION = Path(__file__).parent / 'fixtures' / '5908_decision_denials.json'
TAROT = Path(__file__).parent / 'fixtures' / '5908_comparison_denials.json'
OLD_PAUSE = ('上一轮将"暂缓决定"描述为"完全可逆"，本轮已更正为'
             '"不产生付款承诺但消耗不可收回的时间与机会成本，不能视为零成本或完全无损失"')


class Original5908DecisionDenials(unittest.TestCase):
    def setUp(self):
        providers.Provider76bDenialRegression.setUp(self)
        self.evidence = json.loads(DECISION.read_text(encoding='utf-8'))
        self.sample = self.evidence['samples'][0]
        self.model = providers.RecordedProvider(self.sample, self.evidence)
        self.service.model = self.model

    tearDown = providers.Provider76bDenialRegression.tearDown
    run_for = providers.Provider76bDenialRegression.run_for
    assert_actual_references = providers.Provider76bDenialRegression.assert_actual_references

    def local(self, passage, operation):
        self.service.model = providers.LocalAnswerModel(passage)
        run = self.service.submit(owner=self.owner, message='费用与退出规则未知，只比较现实条件，不排盘。',
                                  request_id=operation, depth='standard')
        return run, self.service.execute(self.owner, run['id'])

    def test_original_unsafe_draft_requires_one_repair_three_calls_and_exact_replay(self):
        before = hashlib.sha256(DECISION.read_bytes()).hexdigest()
        self.assertTrue(self.evidence['synthetic_only'])
        self.assertEqual(self.evidence['source_commit'], '5908ecffb4b8186652df4d325837a0a310d92a0e')
        run = self.service.submit(owner=self.owner, message=self.sample['question'],
                                  request_id='original-5908-decision', depth='standard')
        result = self.service.execute(self.owner, run['id'])
        current = self.repo.fetch_run(self.owner, run['id'])
        self.assertEqual((current['status'], current['calls'], current['call_limit'], current['repair_used']),
                         ('succeeded', 3, 6, True))
        self.assertEqual(self.model.calls, ['intake', 'synthesis', 'repair'])
        self.assertEqual(self.service.validation_attempts, [[providers.GUARANTEE], []])
        self.assertEqual(result['decision_options'], self.model.outputs['repair']['decision_options'])
        self.assertEqual(result['explanation'], self.model.outputs['repair']['explanation'])
        self.assert_actual_references(run, result, set())
        self.assertIn(providers.GUARANTEE, self.service._validate(self.owner, current,
            self.model.bind(deepcopy(self.sample['outputs']['synthesis']))))
        self.assertEqual(self.service._validate(self.owner, current,
            self.model.bind(deepcopy(self.sample['outputs']['repair']))), [])
        replay = self.service.submit(owner=self.owner, message=self.sample['question'],
                                     request_id='original-5908-decision', depth='standard')
        self.assertEqual(replay['id'], run['id'])
        self.assertEqual(self.service.execute(self.owner, replay['id']), result)
        self.assertEqual(len(self.model.calls), 3)
        self.assertEqual(hashlib.sha256(DECISION.read_bytes()).hexdigest(), before)

    def test_only_adjacent_finite_lists_and_exact_pause_withdrawal_pass(self):
        passages = (
            '不能假设任一方零风险、无损失或完全可逆。',
            '不能承诺任一选项无损失或完全可逆。',
            '不能视为零成本或完全无损失。',
            '不能保证零风险、完全可逆或完全无损失。',
            '不能推断其可承受、可退款或付款后无损失。',
            '不能推断其可承受、可退款或付款后完全无损失。',
            OLD_PAUSE + '，付款后退出仍待核实。',
        )
        for index, passage in enumerate(passages):
            with self.subTest(passage=passage):
                run, result = self.local(passage, '5908-safe-' + str(index))
                current = self.repo.fetch_run(self.owner, run['id'])
                self.assertEqual((current['calls'], current['repair_used']), (2, False))
                self.assertTrue(result['validation']['valid'])
                self.assertEqual(len(self.service.memory.facts(self.owner)), 7)

    def test_direct_promises_quoted_double_denials_new_objects_and_new_assertions_fail(self):
        passages = (
            '任一方零风险、无损失或完全可逆。',
            '任一选项零风险、无损失或完全可逆。',
            '可承受、可退款或付款后无损失。',
            '不能假设任一方零风险，但B无损失。',
            '不能视为零成本。报名完全无损失。',
            '不能推断其可承受、可退款，付款后无损失。',
            '不能推断其可承受、可退款或保证付款后无损失。',
            '不能推断其可承受、可退款或付款后B无损失。',
            '不能推断其可承受、可退款或付款后无损失，但B完全可逆。',
            '不是“不能假设任一方零风险、无损失或完全可逆”。',
            '不能“不能承诺任一选项无损失或完全可逆”。',
            '不是“不能视为零成本或完全无损失”。',
            '不能“不能推断其可承受、可退款或付款后无损失”。',
            '不是“' + OLD_PAUSE + '”。',
            OLD_PAUSE + '，但现在报名完全可逆。',
            OLD_PAUSE + '。当前B无损失。',
            OLD_PAUSE.replace('暂缓决定', '报名'),
            OLD_PAUSE.replace('本轮已更正为', '本轮没有更正为'),
            OLD_PAUSE.replace('不产生付款承诺但消耗不可收回的时间与机会成本，不能视为零成本或完全无损失',
                              '今天核实合同条款') + '。报名完全可逆。',
            '历史答复不准确。报名完全可逆。',
        )
        for index, passage in enumerate(passages):
            with self.subTest(passage=passage):
                operation = '5908-unsafe-' + str(index)
                with self.assertRaises(InvalidAnswer): self.local(passage, operation)
                run = self.run_for(operation)
                self.assertEqual((run['status'], run['calls'], run['repair_used']), ('failed', 3, True))
                self.assertIsNone(run['result'])
                self.assertIn(providers.GUARANTEE, self.service.validation_attempts[-1])


class Original5908SingleTarotDenials(unittest.TestCase):
    def setUp(self):
        comparisons.RecordedComparisonRepairs.setUp(self)
        self.evidence = json.loads(TAROT.read_text(encoding='utf-8'))
        self.model = comparisons.RecordedComparisonModel(self.evidence)
        self.model.case_id = self.case
        self.service.model = self.model

    tearDown = comparisons.RecordedComparisonRepairs.tearDown
    consult = comparisons.RecordedComparisonRepairs.consult

    def test_full_original_unsafe_synthesis_then_safe_repair_four_calls_and_exact_replay(self):
        before = hashlib.sha256(TAROT.read_bytes()).hexdigest()
        self.assertTrue(self.evidence['synthetic_only'])
        self.assertEqual(self.model.sample['original_calls'], 4)
        run, result = self.consult('original-5908-single-tarot')
        current = self.repo.fetch_run(self.owner, run['id'])
        self.assertEqual((current['status'], current['calls'], current['call_limit'], current['repair_used']),
                         ('succeeded', 4, 6, True))
        self.assertEqual(self.model.calls, ['intake', 'specialist:tarot', 'synthesis', 'repair'])
        self.assertEqual(self.service.validation_attempts, [[providers.GUARANTEE], []])
        self.assertEqual(result['decision_options'], self.model.outputs['repair']['decision_options'])
        self.assertTrue(result['professional_appendix'].startswith(self.model.outputs['repair']['professional_appendix']))
        self.assertEqual(result['plain_summary'], self.model.outputs['repair']['plain_summary'])
        calculation = self.service._record(self.owner, run['id'], 'calculation')
        self.assertTrue(self.service.knowledge.revalidate_claims(calculation['calculation'], calculation['claims'],
            calculation.get('tarot_provenance'))['eligible'])
        self.assertEqual({c['system'] for c in calculation['claims']}, {'tarot'})
        self.assertTrue(set(result['cited_fact_ids']) <= {f['id'] for f in self.service.memory.facts(self.owner)})
        self.assertTrue(set(result['cited_claim_ids']) <= {c['claim_id'] for c in calculation['claims']})
        self.assertEqual(len(result['cited_fact_ids']), 3)
        self.assertEqual(len(result['cited_claim_ids']), 1)
        self.assertIn(providers.GUARANTEE,
            self.service._validate(self.owner, current, self.model.outputs['synthesis']))
        self.assertEqual(self.service._validate(self.owner, current, self.model.outputs['repair']), [])
        self.assertEqual(card_projection(self.service.tarot.get(self.owner, self.draw['id'])), self.evidence['fixed_cards'])
        self.assertEqual(self.service.execute(self.owner, run['id']), result)
        replay_run, replay_result = self.consult('original-5908-single-tarot')
        self.assertEqual(replay_run['id'], run['id']); self.assertEqual(replay_result, result)
        self.assertEqual(len(self.model.calls), 4)
        self.assertEqual(hashlib.sha256(TAROT.read_bytes()).hexdigest(), before)


if __name__ == '__main__':
    unittest.main()
