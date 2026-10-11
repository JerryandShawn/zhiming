"""Real PG/service and isolated calculators; only model responses are synthetic."""
import json
import unittest

from mingjing_core.application.consultation import ConsultationService
from tests import test_core_compatibility as helpers


class CoreMethodLimitsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): helpers.CoreCompatibilityTests.setUpClass.__func__(cls)
    setUp = helpers.CoreCompatibilityTests.setUp
    tearDown = helpers.CoreCompatibilityTests.tearDown
    consult = helpers.CoreCompatibilityTests.consult
    run_by_request = helpers.CoreCompatibilityTests.run_by_request

    def configure(self, system, scale):
        self.provider = helpers.CompatibilityProvider()
        self.provider.plan_patch = {'systems': [system], 'topic': 'study', 'time_scale': scale}
        self.provider.final_patch = {'caveats': []}
        self.service = ConsultationService(self.repo, model=self.provider)

    def profile(self):
        values = [('gender', '女'), ('birth.solar_datetime', '2000-01-01 08:00'),
                  ('birth.location.lng', 116.4), ('birth.location.lat', 39.9),
                  ('birth.timezone_offset', 8), ('birth.precision', 'exact'), ('birth.time_unknown', False)]
        for index, (field, value) in enumerate(values):
            quote = '合成测试，请保存 ' + field + '=' + str(value)
            source = self.service.memory.receive('alice', content=quote, source_id='method-profile-' + str(index))
            receipt = self.service.memory.save_fact('alice', 'self', source['id'], quote, 'profile', field=field, value=value)
            self.assertEqual(receipt['write_status'], 'saved')

    def test_actual_yearly_astro_rule_gap_survives_model_omitting_all_caveats(self):
        self.configure('astro', 'yearly'); self.profile()
        result = self.consult(message='请依据西方星盘讨论2026-10-11所属年度的学习反思范围。',
                              request_id='actual-astro-year-gap', depth='standard', selection={'systems': ['astro']})
        run = self.run_by_request('actual-astro-year-gap')
        calculation = self.service._record('alice', run['id'], 'calculation')
        self.assertTrue(calculation['calculation']['artifacts'], 'An actual calculator result is required; missing dependency is not a rule gap')
        self.assertFalse(calculation['calculation']['errors'])
        self.assertFalse(calculation['claims']); self.assertTrue(calculation['gaps'])
        self.assertEqual(result['caveats'], [])
        self.assertTrue(any(gap['status'] == 'RULE_GAP' and gap['system'] == 'astro' for gap in result['coverage_gaps']))
        self.assertIn('尚无已发布解释规则', result['coverage_gaps'][0]['reason'])
        self.assertNotIn('artifact_id', result['coverage_gaps'][0])
        self.assertEqual(result['calculation_errors'], [])
        self.assertEqual(result['calculation_fallbacks'], [])
        self.assertEqual(run['status'], 'succeeded'); self.assertEqual(run['calls'], 2)

    def test_missing_birth_parameters_return_public_error_without_raw_entities_or_quotes(self):
        self.configure('bazi', 'daily')
        marker = 'SYNTHETIC_PRIVATE_SOURCE_NOT_METHOD_DIAGNOSTIC_912'
        source = self.service.memory.receive('alice', content=marker, source_id='private-marker')
        self.service.memory.save_fact('alice', 'self', source['id'], marker, 'background')
        result = self.consult(message='请依据八字讨论2026-10-11的学习反思范围。',
                              request_id='missing-chart-input', depth='standard', selection={'systems': ['bazi']})
        self.assertEqual(result['caveats'], [])
        self.assertTrue(result['calculation_errors'])
        self.assertEqual(result['calculation_errors'][0]['code'], 'MISSING_INPUT')
        self.assertIn('已确认的出生参数', result['calculation_errors'][0]['reason'])
        projection = {'gaps': result['coverage_gaps'], 'errors': result['calculation_errors'], 'fallback': result['calculation_fallbacks']}
        self.assertNotIn(marker, json.dumps(projection))
        for field in ('owner_user_id', 'subject_id', 'branch_id', 'artifact_id', 'source_refs', 'input', 'values'):
            self.assertNotIn('"' + field + '"', json.dumps(projection))
        self.assertEqual(result['coverage'][0]['status'], 'unavailable')

    def test_actual_daily_astro_keeps_claims_and_actual_empty_fallback_separate_from_caveats(self):
        self.configure('astro', 'daily'); self.profile()
        result = self.consult(message='请依据西方星盘讨论2026-10-11的学习反思范围。',
                              request_id='actual-astro-daily', depth='standard', selection={'systems': ['astro']})
        run = self.run_by_request('actual-astro-daily')
        calculation = self.service._record('alice', run['id'], 'calculation')['calculation']
        self.assertTrue(calculation['artifacts']); self.assertFalse(calculation['errors'])
        self.assertTrue(result['cited_claim_ids'])
        self.assertIn('前提与局限', result['professional_appendix'])
        profiles = list(calculation['profiles'].values())
        self.assertEqual(profiles[0]['actual_method']['ephemeris'], ['Moshier'])
        self.assertEqual(profiles[0]['fallback'], [])
        self.assertEqual(result['calculation_fallbacks'], [])
        self.assertEqual(result['caveats'], [])
        self.assertEqual(run['calls'], 3)


if __name__ == '__main__': unittest.main()
