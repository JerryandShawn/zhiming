"""Real PG/service repair regressions; only provider outputs are synthetic."""
import unittest
import json
from copy import deepcopy
from pathlib import Path

from mingjing_core.application.consultation import ConsultationService
from mingjing_core.domain.consultation import InvalidAnswer
from tests import test_core_compatibility as helpers


# Exact synthetic fc4 repair passage, without unrelated identities/references.
REAL_REPAIR_PASSAGE = '本轮修复说明：上一轮将"暂缓核实"选项描述为"完全可逆"，这属于过度承诺——核实行为本身不产生费用且可撤回，但拖延可能带来错过开课期或名额的机会成本，该成本因开课时间未知而无法量化，故修正为"核实行为本身可逆，机会成本未知"。'


class CoreReversibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): helpers.CoreCompatibilityTests.setUpClass.__func__(cls)
    setUp = helpers.CoreCompatibilityTests.setUp
    tearDown = helpers.CoreCompatibilityTests.tearDown
    consult = helpers.CoreCompatibilityTests.consult
    run_by_request = helpers.CoreCompatibilityTests.run_by_request
    save = helpers.CoreCompatibilityTests.save

    def configure(self, *, first, repaired=None, explanation=''):
        self.provider = helpers.CompatibilityProvider()
        self.provider.plan_patch = {'mode': 'decision', 'decision': True, 'systems': []}
        self.provider.final_patch = {'plain_summary': first, 'explanation': explanation,
                                    'decision_options': helpers.CoreCompatibilityTests.options('先核实尚未确认的费用与退出条件。')}
        if repaired is not None:
            self.provider.repair_patch = {'plain_summary': repaired, 'explanation': explanation}
        self.service = ConsultationService(self.repo, model=self.provider)
        self.save('请记住：我不接受未经确认的额外费用。')

    def test_unsafe_first_answer_then_actual_fc4_retraction_passes_repair(self):
        self.configure(first='报名完全可逆，可以随时退款。', repaired='费用与退出条件尚未确认，不能保证完全可逆，也不能承诺无损失退出。', explanation=REAL_REPAIR_PASSAGE)
        result = self.consult(message='A是白天学习，B是晚间学习，两者费用与退出条件未知，该怎么选？',
                              request_id='fc4-retraction', depth='standard')
        run = self.run_by_request('fc4-retraction')
        self.assertEqual(run['status'], 'succeeded'); self.assertEqual(run['calls'], 3)
        self.assertEqual([request['purpose'] for request in self.provider.requests], ['intake','synthesis','repair'])
        self.assertEqual(result['explanation'], REAL_REPAIR_PASSAGE)
        self.assertTrue(result['cited_fact_ids'])
        self.assertEqual(result['validation']['status'], 'validated')

    def test_explicit_denials_are_not_unsupported_guarantees(self):
        self.configure(first='这些安排不是零风险，也并非完全可逆；不能保证没有任何损失，不能承诺无损失，不能保证随时退出，也不能承诺随时退款。')
        result = self.consult(request_id='all-explicit-denials', depth='standard')
        self.assertEqual(result['meta']['core_run']['calls'], 2)
        self.assertTrue(result['cited_fact_ids'])

    def test_denial_then_new_affirmation_in_another_sentence_remains_rejected(self):
        self.configure(first='不能保证完全可逆。事实上这门课程完全可逆。')
        with self.assertRaises(InvalidAnswer):
            self.consult(request_id='renewed-guarantee', depth='standard')
        run = self.run_by_request('renewed-guarantee')
        self.assertEqual(run['status'], 'failed'); self.assertIsNone(run['result']); self.assertEqual(run['calls'], 3)
        repair = self.service._record('alice', run['id'], 'model:repair')
        self.assertIn('费用、退出和风险条件未经确认，不能承诺完全可逆或无损失', self.service._validate('alice', run, repair))

    def test_denial_in_same_sentence_cannot_authorize_other_guarantee(self):
        self.configure(first='不能保证零风险，但这门课程完全可逆。')
        with self.assertRaises(InvalidAnswer): self.consult(request_id='contrast-guarantee', depth='standard')
        self.assertEqual(self.run_by_request('contrast-guarantee')['status'], 'failed')

    def test_quotes_without_explicit_withdrawal_and_double_negation_remain_rejected(self):
        variants = ('上一轮说"完全可逆"，现在仍然可以这样承诺。', '不是不能保证完全可逆。',
                    '不能否认完全可逆。', '不可否认完全可逆。', '不排除完全可逆。',
                    '不能说不是完全可逆。', '不能不保证零风险。',
                    '我没有撤回上一轮"完全可逆"的承诺。', '我不是撤回上一轮"完全可逆"的承诺。')
        for index, text in enumerate(variants):
            with self.subTest(text=text):
                self.configure(first=text)
                with self.assertRaises(InvalidAnswer): self.consult(request_id='quoted-or-double-'+str(index), depth='standard')
                self.assertIsNone(self.run_by_request('quoted-or-double-'+str(index))['result'])

    def test_explicit_withdrawal_before_quote_or_denial_after_claim_is_accepted(self):
        self.configure(first='我撤回上一轮"完全可逆"的承诺；零风险这个说法没有依据。')
        result = self.consult(request_id='explicit-withdrawal', depth='standard')
        self.assertEqual(result['meta']['core_run']['calls'], 2)

    def test_each_unauthorized_affirmative_variant_remains_rejected(self):
        variants = ('这门课程零风险。','报名完全可逆。','报名没有任何损失。','报名可以无损失退出。','报名后可以随时退出。','缴费后可以随时退款。')
        for index, text in enumerate(variants):
            with self.subTest(text=text):
                self.configure(first=text)
                with self.assertRaises(InvalidAnswer): self.consult(request_id='affirmative-'+str(index), depth='standard')
                self.assertEqual(self.run_by_request('affirmative-'+str(index))['status'], 'failed')

    def test_repaired_retraction_never_bypasses_fact_citation_validation(self):
        self.configure(first='报名完全可逆。', repaired='不能保证完全可逆。', explanation=REAL_REPAIR_PASSAGE)
        self.provider.repair_patch['cited_fact_ids'] = ['unrelated-fact']
        with self.assertRaises(InvalidAnswer):
            self.consult(request_id='retraction-invalid-citation', depth='standard')
        run = self.run_by_request('retraction-invalid-citation')
        self.assertIsNone(run['result'])
        repair = self.service._record('alice', run['id'], 'model:repair')
        self.assertIn('引用了本轮有效范围之外的事实', self.service._validate('alice', run, repair))

    def test_both_complete_actual_fc4_comparison_repairs_pass_the_real_service(self):
        fixtures = json.loads((Path(__file__).parent / 'fixtures/fc4_decision_repairs.json').read_text(encoding='utf-8'))
        for arm, repair in fixtures.items():
            with self.subTest(arm=arm):
                self.configure(first='报名完全可逆，可以随时退款。')
                self.save('我不能上夜班')
                self.save('先核实班次、费用和退出条件', kind='preference')
                # Preserve every actual response field, replacing only foreign
                # synthetic IDs with real active fixture IDs from this service.
                self.provider.repair_patch = deepcopy(repair)
                result = self.consult(request_id='actual-comparison-'+arm, depth='standard',
                                      message='A班次尚未确认，B明确白班但费用与退出条件未知，该怎么选？')
                self.assertEqual(result['meta']['core_run']['calls'], 3)
                for field in ('plain_summary','explanation','decision_options','professional_appendix','caveats'):
                    self.assertEqual(result[field], repair[field])
                self.assertTrue(result['cited_fact_ids'])

    def test_actual_question_or_quoted_denial_never_authorizes_a_renewed_guarantee(self):
        variants = (
            '核实通常是低承诺行为，但是否完全可逆、是否零成本未经验证，需先确认。事实上报名完全可逆。',
            '不能预先保证"完全可逆、无损失"；但报名完全可逆且无损失。',
            '不能保证"完全可逆，但事实上完全可逆"。',
            '是否完全可逆未经验证，但已经保证完全可逆。',
        )
        for index, text in enumerate(variants):
            with self.subTest(text=text):
                self.configure(first=text)
                with self.assertRaises(InvalidAnswer): self.consult(request_id='renewed-actual-'+str(index), depth='standard')
                self.assertEqual(self.run_by_request('renewed-actual-'+str(index))['status'], 'failed')

    def test_negative_question_and_other_guarantee_source_do_not_authorize_affirmation(self):
        variants = (
            ('不要说完全可逆。费用和退出条件未知，该怎么选？', '报名完全可逆。'),
            ('不能保证完全可逆。费用和退出条件未知，该怎么选？', '报名完全可逆。'),
            ('是否完全可逆？请比较两种安排。', '报名完全可逆。'),
            ('我撤回上一轮完全可逆的说法。请重新比较两种安排。', '报名完全可逆。'),
            ('不排除完全可逆。请比较两种安排。', '报名完全可逆。'),
            ('已确认这门课程零风险。请比较两种安排。', '报名后可以随时退款。'),
        )
        for index, (source, answer) in enumerate(variants):
            with self.subTest(source=source):
                self.configure(first=answer)
                with self.assertRaises(InvalidAnswer):
                    self.consult(message=source, request_id='source-not-affirmative-'+str(index), depth='standard')
                self.assertIsNone(self.run_by_request('source-not-affirmative-'+str(index))['result'])

    def test_same_kind_explicit_source_is_supported_without_cross_kind_exemption(self):
        self.configure(first='课程完全可逆，退出方式仍需核实。')
        result = self.consult(message='已确认这门课程完全可逆。请比较两种安排。', request_id='confirmed-same-kind', depth='standard')
        self.assertEqual(result['meta']['core_run']['calls'], 2)


if __name__ == '__main__': unittest.main()
