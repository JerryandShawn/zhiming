"""Comparison recovery uses real PG/LangGraph; only its provider is replaced."""
import json
import os
import unittest
from unittest.mock import patch
from psycopg import sql

from mingjing_core.adapters.model import ConfiguredModel
from mingjing_core.domain.consultation import ModelUnavailable, InvalidAnswer
from tests import test_core_model_diagnostics as diagnostics
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


if __name__ == '__main__': unittest.main()
