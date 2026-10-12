"""Original synthetic 035 decision repair and bounded wording via actual PG."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from mingjing_core.domain.consultation import InvalidAnswer
from tests import test_core_76b_provider_denials as providers

FIXTURE = Path(__file__).parent / 'fixtures' / '035_second_decision_denials.json'


class Original035SecondDecisionDenials(unittest.TestCase):
    def setUp(self):
        providers.Provider76bDenialRegression.setUp(self)
        self.evidence = json.loads(FIXTURE.read_text(encoding='utf-8'))
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

    def test_full_initial_guarantee_requires_original_repair_three_calls_and_exact_replay(self):
        before = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        self.assertTrue(self.evidence['synthetic_only'])
        self.assertEqual(self.evidence['source_commit'], '035f29f6c85c1229f20467c756e6920ef2c10c97')
        run = self.service.submit(owner=self.owner, message=self.sample['question'],
                                  request_id='035-original-decision', depth='standard')
        result = self.service.execute(self.owner, run['id'])
        current = self.repo.fetch_run(self.owner, run['id'])
        self.assertEqual((current['status'], current['calls'], current['call_limit'], current['repair_used']),
                         ('succeeded', 3, 6, True))
        self.assertEqual(self.model.calls, ['intake', 'synthesis', 'repair'])
        self.assertEqual(self.service.validation_attempts, [[providers.GUARANTEE], []])
        self.assertEqual(result['plain_summary'], self.model.outputs['repair']['plain_summary'])
        self.assertEqual(result['decision_options'], self.model.outputs['repair']['decision_options'])
        self.assert_actual_references(run, result, set())
        self.assertEqual(result['cited_fact_ids'], [self.fact_id])
        self.assertEqual([r['write_status'] for r in result['memory_receipts']], ['pending_confirmation'])
        self.assertIn(providers.GUARANTEE, self.service._validate(self.owner, current,
            self.model.bind(deepcopy(self.sample['outputs']['synthesis']))))
        self.assertEqual(self.service._validate(self.owner, current,
            self.model.bind(deepcopy(self.sample['outputs']['repair']))), [])
        replay = self.service.submit(owner=self.owner, message=self.sample['question'],
                                     request_id='035-original-decision', depth='standard')
        self.assertEqual(replay['id'], run['id'])
        self.assertEqual(self.service.execute(self.owner, replay['id']), result)
        self.assertEqual(len(self.model.calls), 3)
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), before)

    def test_exact_finite_list_and_adjacent_postposed_denial_pass(self):
        passages = (
            '不能推断为可无损退出或零风险。',
            '不能推断为低价、可无损退出或零风险。',
            '不能推断为零费用、零风险或完全可逆。',
            '两者都不该被当作零风险。',
            '未作任何零风险推断。',
            '未作任何零风险、完全可逆或无损失推断。',
            '未作任何“零风险、完全可逆或无损失”推断。',
            '未作任何零风险或可逆性推断。',
            '未作任何“零风险或可逆性”推断。',
        )
        for index, passage in enumerate(passages):
            with self.subTest(passage=passage):
                run, result = self.local(passage, '035-finite-decision-' + str(index))
                current = self.repo.fetch_run(self.owner, run['id'])
                self.assertEqual((current['calls'], current['repair_used']), (2, False))
                self.assertTrue(result['validation']['valid'])
                self.assertEqual(len(self.service.memory.facts(self.owner)), 7)

    def test_direct_double_denial_new_assertion_object_and_cross_sentence_fail(self):
        passages = (
            '可无损退出或零风险。', '低价、可无损退出或零风险。',
            '零费用、零风险或完全可逆。', '两者都该被当作零风险。',
            '不是“不能推断为可无损退出或零风险”。',
            '不能“不能推断为低价、可无损退出或零风险”。',
            '不是“不能推断为零费用、零风险或完全可逆”。',
            '不是不该被当作零风险。', '不是“不该被当作零风险”。',
            '不能“不该被当作零风险”。',
            '不能推断为零费用、零风险，但付款完全可逆。',
            '不该被当作零风险，却保证无损失。',
            '不该被当作A零风险或B完全可逆。',
            '未作任何零风险。', '未作任何零风险报价推断。',
            '未作任何零风险推断并确认付款无损失。',
            '不是未作任何零风险推断。',
            '不是“未作任何零风险、完全可逆或无损失推断”。',
            '不能说“未作任何“零风险、完全可逆或无损失”推断”。',
            '不能“未作任何零风险推断”。',
            '不代表未作任何零风险推断。',
            '未作任何零风险或A完全可逆推断。',
            '未作任何零风险推断。但B完全可逆。',
            '未作任何零风险推断，付款无损失。',
            '未作任何零风险或可逆性推断。付款完全可逆。',
            '未作任何零风险或可逆性推断，但B完全可逆。',
            '未作任何零风险或A可逆性推断。',
        )
        for index, passage in enumerate(passages):
            with self.subTest(passage=passage):
                operation = '035-unsafe-decision-' + str(index)
                with self.assertRaises(InvalidAnswer): self.local(passage, operation)
                run = self.run_for(operation)
                self.assertEqual((run['status'], run['calls'], run['repair_used']), ('failed', 3, True))
                self.assertIsNone(run['result'])
                self.assertIn(providers.GUARANTEE, self.service.validation_attempts[-1])

    def test_postposed_denied_user_source_does_not_authorize_positive_guarantee(self):
        content = '未作任何零风险、完全可逆或无损失推断'
        source = self.service.memory.receive(self.owner, content='请记住：' + content, source_id='035-denied-inference-source')
        receipt = self.service.memory.save_fact(self.owner, 'self', source['id'], content, 'background',
                                                operation_id='035-denied-inference-fact')
        self.assertEqual(receipt['write_status'], 'saved')
        with self.assertRaises(InvalidAnswer): self.local('付款零风险、完全可逆或无损失。', '035-source-is-not-affirmation')
        self.assertIn(providers.GUARANTEE, self.service.validation_attempts[-1])


if __name__ == '__main__':
    unittest.main()
