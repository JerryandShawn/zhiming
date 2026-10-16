"""4288 recorded comparison repair via actual PostgreSQL and LangGraph.

Only the model is substituted. Closed denials cannot authorize a new promise.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from mingjing_core.domain.consultation import InvalidAnswer
from tests import test_core_comparison_repairs as helpers


FIXTURE = Path(__file__).parent / 'fixtures' / '4288_comparison_decision_denials.json'
SAFE = (
    '不能认定之后可以无损失退出',
    '不能认定选择B可无损失退出',
    '不能承诺选择B之后完全可逆或无损失',
    '若B费用不可接受能否无损失退出，取决于B的退出条件，待核实',
)
RUN_EVIDENCE = []


class Recorded4288Model(helpers.RecordedComparisonModel):
    def __init__(self, evidence):
        super().__init__(evidence)
        self.patch = None

    def generate(self, **kwargs):
        # The existing fixture model clears unrelated final fields only when
        # exercising one finite predicate. Complete recorded contracts remain
        # untouched apart from binding fact and case IDs.
        self.final_patch = self.patch['plain_summary'] if self.patch else None
        result = super().generate(**kwargs)
        if self.patch and kwargs['purpose'] in ('synthesis', 'repair'):
            result['output'].update(deepcopy(self.patch))
            self.outputs[kwargs['purpose']] = deepcopy(result['output'])
        return result


class Recorded4288ComparisonDecisionDenials(unittest.TestCase):
    def setUp(self):
        helpers.RecordedComparisonRepairs.setUp(self)
        self.evidence = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.model = Recorded4288Model(self.evidence)
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

    def test_complete_recorded_draft_requires_one_repair_commits_and_replays_free(self):
        before = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        sample = self.evidence['samples'][0]
        self.assertTrue(self.evidence['synthetic_only'])
        self.assertEqual(self.evidence['source_commit'], '4288d5aa3e23c7b2678b37b64462b9e1a91ac1df')
        self.assertEqual((sample['original_status'], sample['original_calls'], sample['original_error_code']),
            ('failed', 3, 'REFERENCE_ERROR'))
        self.assertEqual([x['issues'] for x in sample['original_validation_attempts']],
            [[helpers.GUARANTEE_ISSUE], [helpers.GUARANTEE_ISSUE]])
        facts = self.service.memory.facts(self.owner)
        current, result = self.execute('4288-recorded-repair')
        for key, value in self.model.outputs['repair'].items():
            self.assertEqual(result[key], value)
        self.assertEqual(self.service.memory.facts(self.owner), facts)
        self.assertEqual(result['cited_claim_ids'], [])
        snapshot = self.service._record(self.owner, current['id'], 'snapshot')
        self.assertTrue(set(result['cited_fact_ids']) <= set(snapshot['fact_ids']))
        calculation = self.service._record(self.owner, current['id'], 'calculation')
        self.assertEqual(calculation['claims'], [])
        self.assertTrue(self.service.knowledge.revalidate_claims(calculation['calculation'], [])['eligible'])
        replay, replay_result = self.consult('4288-recorded-repair')
        self.assertEqual(replay['id'], current['id'])
        self.assertEqual(replay_result, result)
        self.assertEqual(len(self.model.calls), 3)
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), before)

    def test_each_closed_denial_and_complete_pending_question_commits_without_repair(self):
        for index, passage in enumerate(SAFE):
            with self.subTest(passage=passage):
                self.execute('4288-finite-safe-' + str(index), patch={'plain_summary': passage + '。'})

    def test_double_denials_quotes_and_renewed_guarantees_stay_rejected(self):
        for index, passage in enumerate(SAFE):
            mutations = ('不是' + passage, '不能说' + passage, '“' + passage + '”',
                '此前称“' + passage + '”', passage + '，但报名完全可逆',
                passage + '。付款无损失', passage + '并保证报名无损失',
                '不能说：' + passage, '不是“情况未知；' + passage + '，须核实”',
                '此前称“情况未知；' + passage + '。之后再决定”')
            for mutation_index, mutation in enumerate(mutations):
                with self.subTest(mutation=mutation):
                    self.execute('4288-unsafe-' + str(index) + '-' + str(mutation_index),
                        patch={'plain_summary': mutation + '。'}, invalid=True)

    def test_new_objects_verbs_and_incomplete_or_confirmed_questions_stay_rejected(self):
        passages = ('认定之后可以无损失退出', '认定选择B可无损失退出',
            '承诺选择B之后完全可逆或无损失', '不能认定之后可以A无损失退出',
            '不能认定选择B可保证无损失退出', '不能承诺选择B之后完全可逆或保证无损失',
            '不能承诺选择A之后完全可逆或无损失',
            '若B费用不可接受可以无损失退出，取决于B的退出条件，待核实',
            '若B费用不可接受能否无损失退出，取决于B的退出条件',
            '若B费用不可接受能否无损失退出，取决于B的退出条件，已核实',
            '若B费用不可接受能否无损失退出，取决于A的退出条件，待核实')
        for index, passage in enumerate(passages):
            with self.subTest(passage=passage):
                self.execute('4288-boundary-' + str(index), patch={'plain_summary': passage + '。'}, invalid=True)

    def test_a_negative_field_cannot_authorize_a_positive_in_another_field(self):
        for index, passage in enumerate(SAFE):
            with self.subTest(passage=passage):
                self.execute('4288-cross-field-' + str(index),
                    patch={'plain_summary': passage + '。', 'professional_appendix': '报名完全可逆，付款无损失。'},
                    invalid=True)


if __name__ == '__main__': unittest.main()
