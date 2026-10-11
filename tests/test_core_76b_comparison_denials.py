"""Recorded synthetic comparison failures through actual PG/Core/card rules."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from mingjing_core.domain.consultation import InvalidAnswer
from tests import test_core_comparison_repairs as helpers
from tests import test_core_76b_provider_denials as provider_helpers
from tools.compare_core_providers import card_projection

FIXTURE = Path(__file__).parent / 'fixtures' / '76b_comparison_denials.json'


class RecordedComparison76bModel(helpers.RecordedComparisonModel):
    def __init__(self, evidence):
        super().__init__(evidence)
        self.unsafe_review = False

    def generate(self, **kwargs):
        response = super().generate(**kwargs)
        if kwargs['purpose'] == 'review' and self.unsafe_review:
            response['output']['plain_summary'] += '但实际报名完全可逆。'
            self.outputs['review'] = deepcopy(response['output'])
        return response


class Comparison76bDenialRegression(unittest.TestCase):
    def setUp(self):
        helpers.RecordedComparisonRepairs.setUp(self)
        self.evidence = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.model = RecordedComparison76bModel(self.evidence)
        self.model.case_id = self.case; self.service.model = self.model

    tearDown = helpers.RecordedComparisonRepairs.tearDown
    def consult(self, operation):
        sample = self.model.sample; tarot = sample['scenario'] == 'tarot'
        if tarot and self.draw is None:
            draw = self.service.tarot.create_draw(self.owner, subject_id='self', case_id=self.case,
                question=self.evidence['questions']['tarot'], spread_id='reflect3', draw_source='manual',
                manual_cards=self.evidence['fixed_cards'], idempotency_key='76b-fixed-cards')['draw']
            self.draw = self.service.tarot.reveal(self.owner, draw['id'])
        run = self.service.submit(owner=self.owner, message=self.evidence['questions']['tarot' if tarot else 'decision'],
            conversation_id='synthetic-conversation', request_id=operation, case_ids=[self.case], depth=sample['depth'],
            selection={'date': '2026-10-11', 'systems': (['tarot'] if sample['arm'] == 'new_single_specialist'
                else ['tarot', 'bazi', 'ziwei', 'astro']) if tarot else []},
            draw_id=self.draw['id'] if tarot else None)
        return run, self.service.execute(self.owner, run['id'])

    def select(self, arm, scenario):
        self.model.sample = next(s for s in self.evidence['samples']
                                 if s['arm'] == arm and s['scenario'] == scenario)
        return self.model.sample

    def bound(self, value):
        if isinstance(value, dict): return {key: self.bound(item) for key, item in value.items()}
        if isinstance(value, list): return [self.bound(item) for item in value]
        if isinstance(value, str):
            for old, new in self.model.mapping.items(): value = value.replace(old, new)
        return value

    def assert_refs(self, run, result):
        record = self.service._record(self.owner, run['id'], 'calculation')
        self.assertTrue(self.service.knowledge.revalidate_claims(record['calculation'], record['claims'],
            record.get('tarot_provenance'))['eligible'])
        self.assertTrue(set(result['cited_fact_ids']) <= {f['id'] for f in self.service.memory.facts(self.owner)})
        self.assertTrue(set(result['cited_claim_ids']) <= {c['claim_id'] for c in record['claims']})
        self.assertTrue(result['validation']['valid'])

    def test_both_full_decision_syntheses_remain_unsafe_and_original_repairs_commit_once(self):
        before = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        self.assertTrue(self.evidence['synthetic_only'])
        for arm in ('new_single_specialist', 'new_controlled_multi_specialists'):
            with self.subTest(arm=arm):
                sample = self.select(arm, 'decision'); start = len(self.model.calls)
                self.assertEqual(sample['original_calls'], 3)
                run, result = self.consult('full-76b-' + arm)
                current = self.repo.fetch_run(self.owner, run['id'])
                self.assertEqual((current['status'], current['calls'], current['repair_used']), ('succeeded', 3, True))
                self.assertEqual(self.model.calls[start:], ['intake', 'synthesis', 'repair'])
                self.assertEqual(self.service.validation_attempts[-2:], [[helpers.GUARANTEE_ISSUE], []])
                self.assertEqual(result['plain_summary'], self.model.outputs['repair']['plain_summary'])
                self.assertEqual(result['decision_options'], self.model.outputs['repair']['decision_options'])
                self.assertIn(helpers.GUARANTEE_ISSUE,
                    self.service._validate(self.owner, current, self.bound(deepcopy(sample['outputs']['synthesis']))))
                self.assertEqual(self.service._validate(self.owner, current,
                    self.bound(deepcopy(sample['outputs']['repair']))), [])
                self.assert_refs(run, result)
                self.assertEqual(self.service.execute(self.owner, run['id']), result)
                self.assertEqual(len(self.model.calls) - start, 3)
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), before)

    def test_single_tarot_saved_state_initial_is_rejected_then_full_original_repair_commits(self):
        sample = self.select('new_single_specialist', 'tarot')
        self.assertEqual(sample['original_calls'], 4)
        run, result = self.consult('full-76b-single-tarot')
        current = self.repo.fetch_run(self.owner, run['id'])
        self.assertEqual((current['status'], current['calls'], current['call_limit'], current['repair_used']), ('succeeded', 4, 6, True))
        self.assertEqual(self.model.calls, ['intake', 'specialist:tarot', 'synthesis', 'repair'])
        self.assertIn(helpers.SAVE_ISSUE, self.service.validation_attempts[0])
        self.assertEqual(self.service.validation_attempts[-1], [])
        self.assertEqual(result['plain_summary'], self.model.outputs['repair']['plain_summary'])
        self.assert_refs(run, result)
        self.assertIn(helpers.SAVE_ISSUE, self.service._validate(self.owner, current,
            self.bound(deepcopy(sample['outputs']['synthesis']))))
        self.assertEqual(card_projection(self.service.tarot.get(self.owner, self.draw['id'])), self.evidence['fixed_cards'])
        self.assertEqual(self.service.execute(self.owner, run['id']), result); self.assertEqual(len(self.model.calls), 4)

    def test_deep_full_original_review_commits_seven_calls_with_all_four_real_systems(self):
        sample = self.select('new_controlled_multi_specialists', 'tarot')
        self.assertEqual(sample['original_calls'], 8)
        run, result = self.consult('full-76b-deep-tarot')
        current = self.repo.fetch_run(self.owner, run['id'])
        self.assertEqual((current['status'], current['calls'], current['call_limit'], current['repair_used']), ('succeeded', 7, 10, False))
        self.assertEqual(self.model.calls, sample['original_purposes'][:-1])
        self.assertEqual(self.service.validation_attempts, [[]]); self.assert_refs(run, result)
        calculation = self.service._record(self.owner, run['id'], 'calculation')
        self.assertEqual({c['system'] for c in calculation['claims']}, {'tarot', 'bazi', 'ziwei', 'astro'})
        for purpose in ('synthesis', 'review', 'repair'):
            self.assertEqual(self.service._validate(self.owner, current,
                self.bound(deepcopy(sample['outputs'][purpose]))), [])
        self.assertEqual(result['plain_summary'], self.model.outputs['review']['plain_summary'])
        self.assertEqual(card_projection(self.service.tarot.get(self.owner, self.draw['id'])), self.evidence['fixed_cards'])
        self.assertEqual(self.service.execute(self.owner, run['id']), result); self.assertEqual(len(self.model.calls), 7)

    def test_deep_unsafe_review_uses_full_original_repair_once_with_eight_cumulative_calls(self):
        sample = self.select('new_controlled_multi_specialists', 'tarot'); self.model.unsafe_review = True
        run, result = self.consult('full-76b-deep-unsafe-review')
        current = self.repo.fetch_run(self.owner, run['id'])
        self.assertEqual((current['status'], current['calls'], current['call_limit'], current['repair_used']), ('succeeded', 8, 10, True))
        self.assertEqual(self.model.calls, sample['original_purposes'])
        self.assertEqual(self.service.validation_attempts, [[helpers.GUARANTEE_ISSUE], []])
        self.assertEqual(result['plain_summary'], self.model.outputs['repair']['plain_summary']); self.assert_refs(run, result)
        self.assertEqual(self.service.execute(self.owner, run['id']), result); self.assertEqual(len(self.model.calls), 8)

    def local(self, passage, operation):
        self.service.model = provider_helpers.LocalAnswerModel(passage)
        run = self.service.submit(owner=self.owner, message='只比较现实条件，不排盘。', request_id=operation,
            case_ids=[self.case], depth='standard')
        return run, self.service.execute(self.owner, run['id'])

    def run_for(self, operation):
        with self.repo.connection() as connection:
            row = connection.execute(helpers.sql.SQL('SELECT id FROM {} WHERE owner=%s AND operation_id=%s').format(
                self.repo.table('core_runs')), (self.owner, operation)).fetchone()
        return self.repo.fetch_run(self.owner, row['id'])

    def test_only_observed_finite_negations_and_explicit_corrections_pass(self):
        passages = ('不能承诺任何一步完全可逆或无损失。', '不能视为零代价或完全可逆。',
            '不是“零代价完全可逆”。', '不能预先推断为可逆或无损失。',
            '不再对任何方案或动作宣称完全可逆、零风险或无损失。', '不按零风险处理。',
            '不能被推断为零风险、完全可逆或无损失。',
            '不声称本轮内容已被保存、更新或删除。', '白班事实不由牌面证明。',
            '本轮修复的错误：此前将"询问"表述为完全可逆、未强调损失可能，现已在各选项的reversibility字段中明确——退出条件、费用和风险条件均未经确认，不能承诺完全可逆。',
            '本轮修复说明：已将decision_options中所有reversibility表述从"完全可逆"修正为"可停止但已投入时间不可收回、承诺后可逆性取决于未知退出条件"。')
        for i, passage in enumerate(passages):
            with self.subTest(passage=passage):
                run, result = self.local(passage, 'new-finite-' + str(i))
                current = self.repo.fetch_run(self.owner, run['id'])
                self.assertEqual((current['status'], current['calls'], current['repair_used']), ('succeeded', 2, False))
                self.assertEqual(result['memory_receipts'], []); self.assertTrue(result['validation']['valid'])

    def test_positive_double_denial_cross_sentence_or_object_and_nonwithdrawal_quotes_still_fail(self):
        passages = ('任何一步完全可逆。', '零代价完全可逆。', '不是不能承诺任何一步无损失。',
            '不能不再对任何方案或动作宣称无损失。', '不再对任何方案或动作宣称，但报名无损失。',
            '不能被推断为无损失，但现在报名完全可逆。', '不是不能被推断为零风险。',
            '不是不按零风险处理。', '不按零风险统计。', '不按零风险处理，但行动完全可逆。',
            '不声称本轮内容，但档案已保存。', '不能不声称本轮内容已保存。',
            '白班事实由牌面证明。', '白班事实不是不由牌面证明。',
            '不由牌面安排。牌面证明白班事实。', '白班事实不由牌面证明，但牌面证明其他事实。',
            '此前将"询问"表述为完全可逆。', '此前将"询问"表述为完全可逆，现已认可此判断。',
            '不是此前将"询问"表述为完全可逆、未强调损失可能，现已在各选项的reversibility字段中明确——退出条件、费用和风险条件均未经确认。',
            '已将decision_options中所有reversibility表述从"完全可逆"修正为"无损失"。',
            '已将decision_options中所有reversibility表述从"完全可逆"未修正为"可停止但已投入时间不可收回、承诺后可逆性取决于未知退出条件"。',
            '不是已将decision_options中所有reversibility表述从"完全可逆"修正为"可停止但已投入时间不可收回、承诺后可逆性取决于未知退出条件"。',
            '已将decision_options中所有reversibility表述从"完全可逆"修正为"可停止但已投入时间不可收回、承诺后可逆性取决于未知退出条件"，但现在报名完全可逆。')
        for i, passage in enumerate(passages):
            with self.subTest(passage=passage):
                operation = 'new-unsafe-' + str(i)
                with self.assertRaises(InvalidAnswer): self.local(passage, operation)
                current = self.run_for(operation)
                self.assertEqual((current['status'], current['calls'], current['repair_used']), ('failed', 3, True))
                self.assertIsNone(current['result']); self.assertTrue(self.service.validation_attempts[-1])

    def test_deep_exact_employer_queries_prohibitions_and_no_symbolic_guarantee_pass(self):
        passages = ('不建议任何夜班例外或放宽。', '任何方案均不建议夜班例外、少量放宽。',
            '“不能上夜班”不设例外或放宽。', '不能上夜班不设例外或放宽。',
            '不能上夜班。今天向A发出班次与夜班例外书面问题。',
            '不能上夜班。在收到A书面班次/夜班例外答复后复盘。',
            '不能上夜班。只填已核实项与未知项：班次、夜班例外、费用、退出、通勤、学习时段、休息承受度。',
            '不能上夜班。A班次、夜班例外、轮班/顶班、报名截止与退出条件未知。',
            '星盘均为传统/编辑反思框架，未经科学事件预测验证，不提供吉凶保证、诊断或事件概率。',
            '不能当成低成本或完全可逆。')
        for i, passage in enumerate(passages):
            with self.subTest(passage=passage):
                run, result = self.local(passage, 'deep-denial-' + str(i))
                current = self.repo.fetch_run(self.owner, run['id'])
                self.assertEqual((current['status'], current['calls'], current['repair_used']), ('succeeded', 2, False))
                self.assertTrue(result['validation']['valid'])

    def test_night_user_negotiation_exceptions_doubles_and_renewed_symbolic_guarantees_fail(self):
        passages = ('是否可以接受每月一次夜班？', '问问自己能否偶尔夜班？',
            '不建议夜班例外，但每月一次可以试。', '建议少量夜班。', '建议夜班例外。',
            '不建议夜班例外，但可以少量夜班。', '不建议夜班例外但允许放宽。',
            '不是不建议夜班例外。', '不能不建议任何夜班例外。',
            '不是夜班不设例外。', '不能说夜班不设例外。', '不能保证夜班不设例外。',
            '夜班不是不设例外。', '不是不能上夜班不设例外。',
            '询问用户是否愿意接受夜班例外。', '询问岗位夜班例外，然后建议用户每周一次夜班。',
            '不能上夜班。今天向A发出班次与夜班例外书面问题，并问自己能否偶尔夜班。',
            '不能上夜班。只填已核实项与未知项：班次、夜班例外、费用、退出、通勤、学习时段、休息承受度，但每月一次可以接受。',
            '星盘提供吉凶保证。', '星盘不是不提供吉凶保证。', '星盘不能不提供吉凶保证。',
            '星盘不提供吉凶保证，但塔罗保证成功。', '星盘不提供吉凶保证。牌面证明真实班次。',
            '不能当成低成本，但实际上报名完全可逆。')
        for i, passage in enumerate(passages):
            with self.subTest(passage=passage):
                operation = 'deep-unsafe-' + str(i)
                with self.assertRaises(InvalidAnswer): self.local(passage, operation)
                current = self.run_for(operation)
                self.assertEqual((current['status'], current['calls'], current['repair_used']), ('failed', 3, True))
                self.assertIsNone(current['result']); self.assertTrue(self.service.validation_attempts[-1])


if __name__ == '__main__': unittest.main()
