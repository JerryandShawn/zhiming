"""Original synthetic 035 batch-two Tarot contracts with actual PG/Card/Core.

Only model responses are substituted. The original failed run stays historical;
this regression verifies its unchanged output using the narrow new grammar.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from mingjing_core.domain.consultation import InvalidAnswer
from tests import test_core_76b_provider_denials as providers
from tools.compare_core_providers import card_projection

FIXTURE = Path(__file__).parent / 'fixtures' / '035_second_tarot_denials.json'


class Original035SecondTarotDenials(unittest.TestCase):
    def setUp(self):
        providers.Provider76bDenialRegression.setUp(self)
        self.evidence = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.sample = self.evidence['samples'][0]
        self.model = providers.RecordedProvider(self.sample, self.evidence)
        self.service.model = self.model
        text = '合成学习决策。目标：在固定白天时间内学习'
        source = self.service.memory.receive(self.owner, content=text, source_id='synthetic-case-source')
        case = self.service.memory.create_case(self.owner, 'self', self.evidence['case_title'],
            goal=self.evidence['case_goal'], message_id=source['id'], operation_id='synthetic-case')
        self.case_id = case['id']
        draw = self.service.tarot.create_draw(self.owner, subject_id='self', case_id=self.case_id,
            question=self.evidence['draw_question'], spread_id='reflect3', draw_source='manual',
            manual_cards=self.evidence['fixed_cards'], idempotency_key='synthetic-fixed-cards')['draw']
        self.draw = self.service.tarot.reveal(self.owner, draw['id'])

    tearDown = providers.Provider76bDenialRegression.tearDown
    run_for = providers.Provider76bDenialRegression.run_for

    def local(self, passage, operation):
        self.service.model = providers.LocalAnswerModel(passage)
        run = self.service.submit(owner=self.owner, message='费用与退出规则未知，只比较现实条件，不排盘。',
                                  request_id=operation, depth='standard')
        return run, self.service.execute(self.owner, run['id'])

    def test_original_full_synthesis_commits_three_calls_and_exact_replay(self):
        before = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        self.assertTrue(self.evidence['synthetic_only'])
        self.assertEqual(self.evidence['source_commit'], '035f29f6c85c1229f20467c756e6920ef2c10c97')
        self.assertEqual((self.sample['original_calls'], self.sample['original_status']), (4, 'failed'))
        run = self.service.submit(owner=self.owner, message=self.sample['question'],
            request_id='original-035-second-tarot', depth='standard', draw_id=self.draw['id'])
        result = self.service.execute(self.owner, run['id'])
        current = self.repo.fetch_run(self.owner, run['id'])
        self.assertEqual((current['status'], current['calls'], current['call_limit'], current['repair_used']),
                         ('succeeded', 3, 6, False))
        self.assertEqual(self.model.calls, ['intake', 'specialist:tarot', 'synthesis'])
        self.assertEqual(self.service.validation_attempts, [[]])
        self.assertEqual(result['plain_summary'], self.model.outputs['synthesis']['plain_summary'])
        self.assertEqual(result['actions'], self.model.outputs['synthesis']['actions'])
        self.assertTrue(result['professional_appendix'].startswith(self.model.outputs['synthesis']['professional_appendix']))
        self.assertTrue(result['validation']['valid'])
        calculation = self.service._record(self.owner, run['id'], 'calculation')
        self.assertEqual({c['system'] for c in calculation['claims']}, {'tarot'})
        self.assertTrue(self.service.knowledge.revalidate_claims(calculation['calculation'], calculation['claims'],
            calculation.get('tarot_provenance'))['eligible'])
        self.assertEqual(result['cited_fact_ids'], [self.fact_id])
        self.assertEqual(set(result['cited_claim_ids']), {c['claim_id'] for c in calculation['claims']})
        original_repair = self.model.bind(deepcopy(self.sample['outputs']['repair']))
        self.assertEqual(self.service._validate(self.owner, current, original_repair), [])
        self.assertEqual(card_projection(self.service.tarot.get(self.owner, self.draw['id'])), self.evidence['fixed_cards'])
        replay = self.service.submit(owner=self.owner, message=self.sample['question'],
            request_id='original-035-second-tarot', depth='standard', draw_id=self.draw['id'])
        self.assertEqual(replay['id'], run['id'])
        self.assertEqual(self.service.execute(self.owner, replay['id']), result)
        self.assertEqual(len(self.model.calls), 3)
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), before)

    def test_exact_adjacent_past_denial_and_same_object_joined_list_pass(self):
        passages = (
            '未推断为零风险。', '未推断为零风险或完全可逆。',
            '费用未知，未推断为零风险、完全可逆或无损失。',
        )
        for index, passage in enumerate(passages):
            with self.subTest(passage=passage):
                run, result = self.local(passage, '035-past-denial-' + str(index))
                current = self.repo.fetch_run(self.owner, run['id'])
                self.assertEqual((current['calls'], current['repair_used']), (2, False))
                self.assertTrue(result['validation']['valid'])
                self.assertEqual(len(self.service.memory.facts(self.owner)), 7)

    def test_direct_quoted_double_denial_contrast_cross_sentence_or_new_object_fail(self):
        passages = (
            '推断为零风险。', '不是未推断为零风险。',
            '不是“未推断为零风险或完全可逆”。', '不能“未推断为零风险”。',
            '不代表未推断为完全可逆。', '未推断为零风险，但付款无损失。',
            '未推断为零风险。现在报名完全可逆。',
            '未推断为A零风险或B完全可逆。',
            '未推断为零风险或可以保证无损失。',
            '未推断为零风险，却确定完全可逆。',
        )
        for index, passage in enumerate(passages):
            with self.subTest(passage=passage):
                operation = '035-unsafe-past-denial-' + str(index)
                with self.assertRaises(InvalidAnswer): self.local(passage, operation)
                current = self.run_for(operation)
                self.assertEqual((current['status'], current['calls'], current['repair_used']), ('failed', 3, True))
                self.assertIsNone(current['result'])
                self.assertIn(providers.GUARANTEE, self.service.validation_attempts[-1])

    def test_past_denial_cannot_excuse_a_model_save_or_symbolic_fact_assertion(self):
        for index, (passage, issue) in enumerate((
                ('未推断为零风险。已保存塔罗声明。', providers.SAVE),
                ('未推断为零风险。牌面证明你会成功。', '象征解释被提升为现实确定性或概率'))):
            with self.subTest(passage=passage):
                with self.assertRaises(InvalidAnswer): self.local(passage, '035-other-guard-' + str(index))
                self.assertIn(issue, self.service.validation_attempts[-1])


if __name__ == '__main__':
    unittest.main()
