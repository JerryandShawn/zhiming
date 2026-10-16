"""Both original 035 comparison repairs via PG/Core; model-only substitution."""
import hashlib
import json
from pathlib import Path
import unittest

from tests import test_core_comparison_repairs as helpers

FIXTURE = Path(__file__).parent / 'fixtures' / '035_second_comparison_decision_denials.json'


class Original035ComparisonDecisionDenials(unittest.TestCase):
    def setUp(self):
        helpers.RecordedComparisonRepairs.setUp(self)
        self.evidence = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.model = helpers.RecordedComparisonModel(self.evidence)
        self.model.case_id = self.case
        self.service.model = self.model

    tearDown = helpers.RecordedComparisonRepairs.tearDown
    consult = helpers.RecordedComparisonRepairs.consult

    def test_both_original_unsafe_drafts_require_full_repairs_three_calls_and_replay(self):
        before = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        self.assertTrue(self.evidence['synthetic_only'])
        self.assertEqual(self.evidence['source_commit'], '035f29f6c85c1229f20467c756e6920ef2c10c97')
        for sample in self.evidence['samples']:
            with self.subTest(arm=sample['arm']):
                self.model.sample = sample; start = len(self.model.calls)
                operation = '035-comparison-' + sample['arm']
                run, result = self.consult(operation)
                current = self.repo.fetch_run(self.owner, run['id'])
                self.assertEqual((current['status'], current['calls'], current['call_limit'], current['repair_used']),
                                 ('succeeded', 3, 6, True))
                self.assertEqual(self.model.calls[start:], ['intake', 'synthesis', 'repair'])
                self.assertEqual(self.service.validation_attempts[-2:], [[helpers.GUARANTEE_ISSUE], []])
                self.assertEqual(result['plain_summary'], self.model.outputs['repair']['plain_summary'])
                self.assertEqual(result['explanation'], self.model.outputs['repair']['explanation'])
                self.assertEqual(result['decision_options'], self.model.outputs['repair']['decision_options'])
                self.assertIn(helpers.GUARANTEE_ISSUE,
                    self.service._validate(self.owner, current, self.model.outputs['synthesis']))
                self.assertEqual(self.service._validate(self.owner, current, self.model.outputs['repair']), [])
                calculation = self.service._record(self.owner, run['id'], 'calculation')
                self.assertEqual(calculation['claims'], [])
                self.assertTrue(self.service.knowledge.revalidate_claims(calculation['calculation'], calculation['claims'])['eligible'])
                self.assertTrue(set(result['cited_fact_ids']) <= {f['id'] for f in self.service.memory.facts(self.owner)})
                self.assertEqual(result['cited_claim_ids'], [])
                self.assertTrue(result['validation']['valid'])
                replay_run, replay_result = self.consult(operation)
                self.assertEqual(replay_run['id'], run['id']); self.assertEqual(replay_result, result)
                self.assertEqual(len(self.model.calls) - start, 3)
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), before)


if __name__ == '__main__':
    unittest.main()
