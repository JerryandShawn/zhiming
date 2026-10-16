"""Full synthetic comparison outputs through real Core/PG; model-only replay."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from mingjing_core.domain.consultation import InvalidAnswer
from tests import test_core_comparison_repairs as helpers


FIXTURE = Path(__file__).parent / 'fixtures' / '9c_comparison_negated_lists.json'
GUARANTEE_ISSUE = helpers.GUARANTEE_ISSUE


class ComparisonNegatedListRegression(unittest.TestCase):
    # Reuse the real comparison fixture's authorized profile, two confirmed
    # facts, isolated PG schema, selected case and 123 original history rows.
    # No service/calculation/knowledge methods are replaced.
    def setUp(self):
        helpers.RecordedComparisonRepairs.setUp(self)
        self.evidence = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.model = helpers.RecordedComparisonModel(self.evidence)
        self.model.case_id = self.case
        self.service.model = self.model

    tearDown = helpers.RecordedComparisonRepairs.tearDown
    consult = helpers.RecordedComparisonRepairs.consult

    def bind(self, value):
        if isinstance(value, dict): return {key: self.bind(item) for key, item in value.items()}
        if isinstance(value, list): return [self.bind(item) for item in value]
        if isinstance(value, str):
            for old, new in self.model.mapping.items(): value = value.replace(old, new)
        return value

    def test_full_original_synthesis_commits_two_calls_and_repair_validates(self):
        before = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        self.assertTrue(self.evidence['synthetic_only'])
        self.assertEqual(self.evidence['source_commit'], '9c46f7e3aa1f988dc7318d5ff597de2fab4925c0')
        self.assertEqual(self.evidence['original_calls'], 3)
        self.assertEqual(self.evidence['samples'][0]['original_validation_issues'],
            [[GUARANTEE_ISSUE], [GUARANTEE_ISSUE]])
        run, result = self.consult('original-negated-list')
        current = self.repo.fetch_run(self.owner, run['id'])
        self.assertEqual((current['status'], current['calls'], current['repair_used']), ('succeeded', 2, False))
        self.assertEqual(self.model.calls, ['intake', 'synthesis'])
        self.assertEqual(self.service.validation_attempts, [[]])
        self.assertEqual(result['plain_summary'], self.model.outputs['synthesis']['plain_summary'])
        self.assertEqual(result['explanation'], self.model.outputs['synthesis']['explanation'])
        self.assertEqual(result['decision_options'], self.model.outputs['synthesis']['decision_options'])
        self.assertTrue(result['validation']['valid'])
        self.assertEqual(len(result['cited_fact_ids']), 2)
        self.assertEqual(result['cited_claim_ids'], [])
        self.assertEqual(self.service._record(self.owner, run['id'], 'calculation')['claims'], [])
        original_repair = self.bind(deepcopy(self.evidence['samples'][0]['outputs']['repair']))
        self.assertEqual(self.service._validate(self.owner, current, original_repair), [])
        self.assertEqual(self.service.execute(self.owner, run['id']), result)
        replay, same = self.consult('original-negated-list')
        self.assertEqual(replay['id'], run['id']); self.assertEqual(same, result)
        self.assertEqual(len(self.model.calls), 2)
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), before)

    def test_only_adjacent_list_terms_inherit_the_local_denial(self):
        passages = ('不能视为零成本、无损失或完全可逆。',
            '不能据此认定B低成本、无风险或完全可逆。',
            '不能视为无风险或完全可逆。',
            '不能据此认定A低成本、无风险或完全可逆。',
            '不能视为“零成本、无损失或完全可逆”。',
            '不能认定B“低成本”、无风险或完全可逆。',
            '不能宣称任何零成本、无风险或完全可逆。')
        for index, passage in enumerate(passages):
            with self.subTest(passage=passage):
                self.model.final_patch = passage
                before = len(self.model.calls)
                run, result = self.consult('adjacent-list-' + str(index))
                current = self.repo.fetch_run(self.owner, run['id'])
                self.assertEqual((current['status'], current['calls'], current['repair_used']), ('succeeded', 2, False))
                self.assertTrue(result['validation']['valid'])
                self.assertEqual(self.model.calls[before:], ['intake', 'synthesis'])

    def test_direct_promises_double_denials_and_nonadjacent_objects_still_fail(self):
        passages = ('B零成本、无损失或完全可逆。', 'B低成本、无风险或完全可逆。',
            '不能视为零成本，但无损失或完全可逆。',
            '不能视为零成本、无损失。报名完全可逆。',
            '不是不能视为零成本、无损失或完全可逆。',
            '并非不能据此认定B低成本、无风险或完全可逆。',
            '不可能不能认定A低成本、无风险或完全可逆。',
            '不能视为零成本、或保证无损失。',
            '不能据此认定B低成本、无风险或保证完全可逆。',
            '不能据此认定B低成本，但实际上B完全可逆。',
            '不能认定B现在低成本、无风险或完全可逆。',
            '不能认定某个方案低成本、无风险或完全可逆。',
            '不能视为零成本、无损失；当前报名完全可逆。',
            '不能视为低成本、无风险，不过当前安排无损失。',
            '不再宣称任何零成本、无风险或完全可逆。实际安排完全可逆。')
        for index, passage in enumerate(passages):
            with self.subTest(passage=passage):
                self.model.final_patch = passage
                before = len(self.model.calls)
                operation = 'unsafe-list-' + str(index)
                with self.assertRaises(InvalidAnswer): self.consult(operation)
                with self.repo.connection() as connection:
                    row = connection.execute(helpers.sql.SQL('SELECT id FROM {} WHERE owner=%s AND operation_id=%s').format(
                        self.repo.table('core_runs')), (self.owner, operation)).fetchone()
                current = self.repo.fetch_run(self.owner, row['id'])
                self.assertEqual((current['status'], current['calls'], current['repair_used']), ('failed', 3, True))
                self.assertIsNone(current['result'])
                self.assertEqual(self.model.calls[before:], ['intake', 'synthesis', 'repair'])
                final = self.service._record(self.owner, current['id'], 'model:repair')
                self.assertEqual(self.service._validate(self.owner, current, final), [GUARANTEE_ISSUE])


if __name__ == '__main__': unittest.main()
