"""Comparison recovery uses real PG/LangGraph; only its provider is replaced."""
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from psycopg import sql

from mingjing_core.adapters.model import ConfiguredModel
from mingjing_core.domain.consultation import ModelUnavailable, InvalidAnswer
from tests import test_core_model_diagnostics as diagnostics
from tests import test_core_comparison_repairs as recorded_helpers
from tests.test_core_memory import test_dsn
from tools import compare_core_providers as comparison


def answer_for(kwargs):
    data = kwargs['payload']['reference_data']
    if kwargs['purpose'] == 'intake':
        return {'plan': {'target_date': '2026-10-11', 'systems': []}, 'proposals': []}
    return {'plain_summary': '先核对现实条件。', 'actions': ['询问书面条件。'],
            'decision_options': [], 'cited_fact_ids': [f['id'] for f in data.get('facts', [])],
            'cited_claim_ids': []}


class ComparisonRecoveryTests(unittest.TestCase):
    cleanup = diagnostics.FailureDiagnosticPostgresTests.cleanup
    charges = diagnostics.FailureDiagnosticPostgresTests.charges

    def setUp(self):
        diagnostics.FailureDiagnosticPostgresTests.setUp(self)

    def execute(self, attempts, depth='standard'):
        run = self.service.submit(owner='alpha', message='合成普通问答，请给一个小行动。',
                                  request_id='same-comparison-operation', depth=depth)
        return comparison.execute_core_with_recovery(self.service, 'alpha', run['id'], None, attempts)

    def test_http_429_recovery_keeps_failed_attempt_and_original_budget(self):
        purposes = []
        def provider(**kwargs):
            purposes.append(kwargs['purpose'])
            if len(purposes) == 1:
                raise ModelUnavailable('PRIVATE_PROVIDER_TEXT', reason='http', provider_http_status=429)
            return {'output': answer_for(kwargs), 'usage': {}, 'model': 'synthetic'}
        self.provider.generate = provider
        attempts = []
        with patch.object(comparison.time, 'sleep') as sleep:
            result = self.execute(attempts)
        sleep.assert_called_once_with(5)
        run = self.repo.fetch_run('alpha', result['meta']['core_run']['run_id'])
        self.assertEqual((run['status'], run['calls'], run['call_limit'], run['attempts']), ('succeeded', 3, 6, 2))
        self.assertEqual([a['calls'] for a in attempts], [1, 3])
        self.assertEqual({a['run_id'] for a in attempts}, {run['id']})
        self.assertEqual({a['operation_id'] for a in attempts}, {'same-comparison-operation'})
        self.assertEqual(attempts[0]['provider_http_status'], 429)
        self.assertNotIn('PRIVATE_PROVIDER_TEXT', json.dumps(attempts))
        self.assertEqual(len(self.charges(run['id'])), 3)

    def test_repeated_transient_failure_stops_at_two_recoveries(self):
        def provider(**kwargs):
            raise ModelUnavailable('PRIVATE_PROVIDER_TEXT', reason='network')
        self.provider.generate = provider
        attempts = []
        with self.assertRaises(ModelUnavailable): self.execute(attempts)
        run = self.repo.fetch_run('alpha', attempts[0]['run_id'])
        self.assertEqual((run['status'], run['calls'], run['call_limit'], run['attempts']), ('failed', 3, 6, 3))
        self.assertEqual([a['calls'] for a in attempts], [1, 2, 3])
        self.assertEqual({a['run_id'] for a in attempts}, {run['id']})
        self.assertEqual(len(self.charges(run['id'])), 3)
        self.assertIsNone(run['result'])

    def test_fast_budget_stops_before_recovery_bound(self):
        def provider(**kwargs):
            raise ModelUnavailable('synthetic', reason='network')
        self.provider.generate = provider
        attempts = []
        with self.assertRaises(ModelUnavailable): self.execute(attempts, depth='fast')
        run = self.repo.fetch_run('alpha', attempts[0]['run_id'])
        self.assertEqual((run['calls'], run['call_limit'], run['attempts']), (2, 2, 2))
        self.assertEqual([a['calls'] for a in attempts], [1, 2])

    def test_non_transient_failures_do_not_recover(self):
        for reason, status in (('configuration', None), ('http', 401), ('http', 403), ('http', 600), ('max_tokens', None)):
            with self.subTest(reason=reason, status=status):
                def provider(**kwargs):
                    raise ModelUnavailable('PRIVATE_PROVIDER_TEXT', reason=reason, provider_http_status=status)
                self.provider.generate = provider
                run = self.service.submit(owner='alpha', message='合成问题', request_id='terminal-'+reason+str(status))
                attempts = []
                with self.assertRaises(ModelUnavailable):
                    comparison.execute_core_with_recovery(self.service, 'alpha', run['id'], None, attempts)
                self.assertEqual(self.repo.fetch_run('alpha', run['id'])['calls'], 1)
                self.assertEqual(len(attempts), 1)

    def test_reference_failure_gets_no_technical_recovery(self):
        def provider(**kwargs):
            output = answer_for(kwargs)
            if kwargs['purpose'] != 'intake': output['plain_summary'] = '付款无损失。'
            return {'output': output, 'usage': {}, 'model': 'synthetic'}
        self.provider.generate = provider
        attempts = []
        with self.assertRaises(InvalidAnswer): self.execute(attempts)
        self.assertEqual(attempts, [])
        with self.repo.transaction('alpha') as connection:
            run = connection.execute(sql.SQL('SELECT id,calls FROM {} WHERE owner=%s AND operation_id=%s').format(
                self.repo.table('core_runs')), ('alpha', 'same-comparison-operation')).fetchone()
        self.assertEqual(run['calls'], 3)

    def test_real_comparison_observer_persists_only_safe_provider_failure(self):
        def provider(model, **kwargs):
            raise ModelUnavailable('PRIVATE_PROVIDER_TEXT', reason='http', provider_http_status=403,
                                   latency_seconds=0.1)
        with patch.dict(os.environ, {'CORE_COMPARE_PREFLIGHT_DSN': test_dsn()}), patch.object(ConfiguredModel, 'generate', provider):
            result = comparison.core_worker('new_single_specialist', 'decision', 'CORE_COMPARE_PREFLIGHT_DSN')
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['provider_calls'], 1)
        self.assertEqual(result['durable_budget'], {'calls': 1, 'limit': 6})
        self.assertEqual(result['calls'][0]['reason'], 'http')
        self.assertEqual(result['calls'][0]['provider_http_status'], 403)
        self.assertEqual(result['technical_attempts'][0]['provider_http_status'], 403)
        self.assertNotIn('PRIVATE_PROVIDER_TEXT', json.dumps(result))

    def test_original_single_tarot_specialist_recovers_without_hiding_physical_attempts(self):
        evidence = json.loads((Path(__file__).parent / 'fixtures' / '5908_comparison_denials.json').read_text(encoding='utf-8'))
        recorded = recorded_helpers.RecordedComparisonModel(evidence)
        failed = False
        def provider(model, **kwargs):
            nonlocal failed
            if kwargs['purpose'] == 'intake':
                recorded.case_id = kwargs['payload']['reference_data']['case_ids'][0]
            if kwargs['purpose'] == 'specialist:tarot' and not failed:
                failed = True
                raise ModelUnavailable('PRIVATE_PROVIDER_TEXT', reason='network')
            return recorded.generate(**kwargs)
        with patch.dict(os.environ, {'CORE_COMPARE_PREFLIGHT_DSN': test_dsn()}), patch.object(ConfiguredModel, 'generate', provider):
            result = comparison.core_worker('new_single_specialist', 'tarot', 'CORE_COMPARE_PREFLIGHT_DSN')
        self.assertEqual(result['status'], 'validated')
        self.assertTrue(result['validation']['valid'])
        self.assertEqual(result['provider_calls'], 5)
        self.assertEqual(result['durable_budget'], {'calls': 5, 'limit': 6})
        self.assertEqual(result['specialist_provider_calls'], 2)
        self.assertEqual(result['successful_specialist_provider_calls'], 1)
        self.assertEqual(result['completed_specialist_systems'], ['tarot'])
        self.assertEqual((result['review_provider_calls'], result['successful_review_provider_calls']), (0, 0))
        self.assertEqual(result['repair_provider_calls'], 1)
        self.assertEqual([a['calls'] for a in result['technical_attempts']], [2, 5])
        self.assertEqual({a['operation_id'] for a in result['technical_attempts']}, {'fixed-target'})
        self.assertEqual(len({a['run_id'] for a in result['technical_attempts']}), 1)
        self.assertEqual(result['calls'][1]['error_code'], 'MODEL_UNAVAILABLE')
        self.assertEqual(result['validation_attempts'][0]['issues'], [recorded_helpers.GUARANTEE_ISSUE])
        self.assertEqual(result['validation_attempts'][1]['issues'], [])
        self.assertTrue(result['fixed_cards_unchanged'])
        self.assertNotIn('PRIVATE_PROVIDER_TEXT', json.dumps(result))

    def test_deep_actual_three_calculators_review_recovery_keeps_eight_calls(self):
        failed = False
        def provider(model, **kwargs):
            nonlocal failed
            data = kwargs['payload']['reference_data']; purpose = kwargs['purpose']
            if purpose == 'review' and not failed:
                failed = True
                raise ModelUnavailable('PRIVATE_PROVIDER_TEXT', reason='network')
            if purpose == 'intake':
                output = {'plan': {'mode': 'tarot', 'topic': 'study', 'systems': ['bazi', 'ziwei', 'astro', 'tarot'],
                    'target_date': '2026-10-11', 'time_scale': 'natal', 'decision': True,
                    'rationale': '合成实际三盘恢复预检', 'missing_inputs': []},
                    'proposals': [], 'retire_fact_ids': [], 'attachment_observations': []}
            elif purpose.startswith('specialist:'):
                output = {'system': purpose.split(':')[1], 'claim_ids': [c['claim_id'] for c in data['claims']],
                          'discussion': '仅在发布规则内提供独立的条件反思。', 'uncertainties': []}
            else:
                output = {'plain_summary': '先核对实际班次和费用，再选择可逆的小行动。', 'explanation': '象征仅供讨论。',
                    'actions': ['先核实白班要求。'],
                    'decision_options': [{'option': label, 'benefit': '核实后才能判断白班条件', 'cost': '实际费用未知',
                        'risk': '班次条件待核实', 'reversibility': '先询问，再承诺', 'first_step': '核实书面班次与费用'}
                        for label in ('核实A', '核实B')], 'follow_up': '按现实反馈复盘。',
                    'professional_appendix': '仅按已验证字段与规则解释，象征不能证明现实结局。',
                    'cited_fact_ids': [f['id'] for f in data.get('facts', [])],
                    'cited_claim_ids': [c['claim_id'] for c in data.get('claims', [])], 'caveats': []}
            return {'output': output, 'usage': {'input_tokens': 7, 'output_tokens': 11},
                    'latency_seconds': 0, 'model': 'synthetic-preflight'}
        with patch.dict(os.environ, {'CORE_COMPARE_PREFLIGHT_DSN': test_dsn()}), patch.object(ConfiguredModel, 'generate', provider):
            result = comparison.core_worker('new_controlled_multi_specialists', 'tarot', 'CORE_COMPARE_PREFLIGHT_DSN')
        self.assertEqual(result['status'], 'validated')
        self.assertTrue(result['validation']['valid'])
        self.assertEqual(result['provider_calls'], 8)
        self.assertEqual(result['durable_budget'], {'calls': 8, 'limit': 10})
        self.assertEqual((result['specialist_provider_calls'], result['successful_specialist_provider_calls']), (4, 4))
        self.assertEqual(result['completed_specialist_systems'], ['astro', 'bazi', 'tarot', 'ziwei'])
        self.assertEqual((result['review_provider_calls'], result['successful_review_provider_calls']), (2, 1))
        self.assertEqual(result['repair_provider_calls'], 0)
        self.assertEqual([a['calls'] for a in result['technical_attempts']], [7, 8])
        self.assertEqual({a['operation_id'] for a in result['technical_attempts']}, {'fixed-target'})
        self.assertEqual(len({a['run_id'] for a in result['technical_attempts']}), 1)
        self.assertEqual([c['purpose'] for c in result['calls']][-2:], ['review', 'review'])
        self.assertEqual(result['calls'][-2]['error_code'], 'MODEL_UNAVAILABLE')
        self.assertEqual(result['validation_attempts'][0]['issues'], [])
        self.assertTrue(result['fixed_cards_unchanged'])
        self.assertNotIn('PRIVATE_PROVIDER_TEXT', json.dumps(result))


if __name__ == '__main__': unittest.main()
