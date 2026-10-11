"""Exercise the real HTTPX transport and response parser without provider calls."""
import json
import unittest
from unittest.mock import patch
import uuid

import httpx
from psycopg import sql

from mingjing_core.adapters.model import ConfiguredModel
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.domain.contracts import LeaseConflict
from mingjing_core.domain.consultation import InvalidAnswer, ModelFailureReason, ModelUnavailable
from mingjing_core.repositories.postgres import PostgresRepository
from tests.test_core_memory import test_dsn


class ConfiguredModelDiagnosticsTests(unittest.TestCase):
    private = 'PRIVATE_PROVIDER_BODY_AND_KEY_2839'

    def call(self, response=None, *, error=None, purpose='intake'):
        requests = []

        def handler(request):
            requests.append(request)
            if error is not None:
                raise error(self.private, request=request)
            return response

        client = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(client.close)
        with patch('mingjing_core.adapters.model.httpx.Client', return_value=client):
            model = ConfiguredModel(key=self.private, base='https://synthetic.invalid/v1', model='synthetic-k3')
            try:
                result = model.generate(system='synthetic instructions', payload={'question':'synthetic question'},
                                        schema={'type':'object'}, purpose=purpose)
            except ModelUnavailable as exc:
                return exc, requests
        return result, requests

    def assert_safe(self, exc, reason, requests):
        self.assertIsInstance(exc, ModelUnavailable)
        self.assertEqual(exc.reason, reason.value)
        self.assertEqual(exc.safe_diagnostic()['failure_code'], 'MODEL_' + reason.value.upper())
        self.assertEqual(len(requests), 1)
        self.assertIsNone(exc.__cause__)
        self.assertIsNone(exc.__context__)
        self.assertNotIn(self.private, str(exc))
        self.assertNotIn(self.private, json.dumps(exc.safe_diagnostic()))

    def test_success_preserves_output_usage_and_thinking_compatible_tool_choice(self):
        usage = {'input_tokens':23, 'output_tokens':17, 'provider_extension':{'opaque':1}}
        response = httpx.Response(200, json={'content':[{'type':'tool_use', 'name':'submit', 'input':{'valid':True}}],
                                           'usage':usage, 'stop_reason':'tool_use'})
        for purpose, limit in (('intake',6000), ('synthesis',14000), ('review',14000), ('repair',14000)):
            with self.subTest(purpose=purpose):
                result, requests = self.call(response, purpose=purpose)
                self.assertEqual(result['output'], {'valid':True})
                self.assertEqual(result['usage'], usage)
                self.assertEqual(result['model'], 'synthetic-k3')
                self.assertEqual(len(requests), 1)
                body = json.loads(requests[0].content)
                self.assertEqual(body['tool_choice'], {'type':'auto', 'disable_parallel_tool_use':True})
                self.assertEqual(body['thinking'], {'type':'enabled', 'budget_tokens':1024})
                self.assertEqual(body['max_tokens'], limit)

    def test_http_failure_never_parses_private_response_body_or_headers(self):
        for status in (401,429,500):
            with self.subTest(status=status):
                exc, requests = self.call(httpx.Response(status, text=self.private, headers={'x-private':self.private}))
                self.assert_safe(exc, ModelFailureReason.HTTP, requests)
                self.assertEqual(exc.safe_diagnostic()['provider_http_status'], status)
                self.assertFalse(exc.usage_known)
                self.assertEqual(exc.usage, {})

    def test_network_failure_has_no_raw_error_chain_and_never_retries(self):
        for error in (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError):
            with self.subTest(error=error.__name__):
                exc, requests = self.call(error=error)
                self.assert_safe(exc, ModelFailureReason.NETWORK, requests)
                self.assertFalse(exc.usage_known)
                self.assertNotIn('provider_http_status', exc.safe_diagnostic())

    def test_invalid_json_and_response_shapes_have_safe_json_diagnostic(self):
        responses = (httpx.Response(200, text=self.private),
                     httpx.Response(200, json=[self.private]),
                     httpx.Response(200, json={'content':self.private}),
                     httpx.Response(200, json={'content':[self.private]}))
        for response in responses:
            with self.subTest(response=response):
                exc, requests = self.call(response)
                self.assert_safe(exc, ModelFailureReason.JSON, requests)
                self.assertFalse(exc.usage_known)

    def test_max_tokens_failure_retains_known_usage_without_private_extensions(self):
        response = httpx.Response(200, json={'content':[{'type':'thinking','thinking':self.private}],
            'stop_reason':'max_tokens', 'usage':{'input_tokens':30, 'output_tokens':0,
                'cache_read_input_tokens':4, 'provider_extension':self.private}})
        exc, requests = self.call(response)
        self.assert_safe(exc, ModelFailureReason.MAX_TOKENS, requests)
        self.assertTrue(exc.usage_known)
        self.assertEqual(exc.usage, {'input_tokens':30, 'output_tokens':0, 'cache_read_input_tokens':4})
        self.assertEqual(exc.safe_diagnostic()['stop_reason'], 'max_tokens')

    def test_parseable_bad_content_keeps_authoritative_token_counts_only(self):
        exc, requests = self.call(httpx.Response(200, json={'content':self.private,
            'usage':{'input_tokens':21,'output_tokens':8,'private':self.private}}))
        self.assert_safe(exc, ModelFailureReason.JSON, requests)
        self.assertTrue(exc.usage_known)
        self.assertEqual(exc.usage, {'input_tokens':21,'output_tokens':8})

    def test_nonunique_tool_and_invalid_input_are_distinct_without_private_input(self):
        tool = {'type':'tool_use','name':'submit','input':{'private':self.private}}
        for count in (0,2):
            with self.subTest(count=count):
                exc, requests = self.call(httpx.Response(200, json={'content':[tool]*count,
                    'stop_reason':self.private, 'usage':{'input_tokens':4}}))
                self.assert_safe(exc, ModelFailureReason.TOOL_COUNT, requests)
                self.assertEqual(exc.safe_diagnostic()['tool_count'], count)
                self.assertEqual(exc.safe_diagnostic()['stop_reason'], 'unknown')
        exc, requests = self.call(httpx.Response(200, json={'content':[{'type':'tool_use','name':'submit','input':self.private}],
            'usage':{'input_tokens':True, 'output_tokens':-1, 'cache_creation_input_tokens':0,
                     'cache_read_input_tokens':{'private':self.private}}}))
        self.assert_safe(exc, ModelFailureReason.TOOL_INPUT, requests)
        self.assertEqual(exc.usage, {'cache_creation_input_tokens':0})
        self.assertTrue(exc.usage_known)

    def test_missing_configuration_never_makes_request_and_legacy_exception_is_compatible(self):
        with patch('mingjing_core.adapters.model.httpx.Client') as client:
            with self.assertRaises(ModelUnavailable) as raised:
                ConfiguredModel(key='').generate(system='', payload={}, schema={}, purpose='intake')
        client.assert_not_called()
        self.assertEqual(raised.exception.reason, 'configuration')
        self.assertFalse(raised.exception.usage_known)
        exc = ModelUnavailable('existing safe message')
        self.assertEqual(str(exc), 'existing safe message')
        self.assertEqual(exc.safe_diagnostic()['reason'], 'unknown')


class FailureProvider:
    """Only the external model is substituted; every service/PG effect is real."""
    def __init__(self):
        self.calls = 0
        self.during_call = None

    def generate(self, **kwargs):
        self.calls += 1
        if self.during_call:
            self.during_call()
        known = self.calls == 1
        raise ModelUnavailable('合成模型服务暂不可用', reason='max_tokens' if known else 'network',
            usage={'input_tokens':19,'output_tokens':7,'private_extension':'PRIVATE_DIAGNOSTIC_693'} if known else None,
            provider_http_status=200 if known else None, latency_seconds=0.02)


class FailureDiagnosticPostgresTests(unittest.TestCase):
    def setUp(self):
        self.schema = 'test_model_failure_' + uuid.uuid4().hex[:16]
        self.repo = PostgresRepository(test_dsn(), schema=self.schema)
        self.addCleanup(self.cleanup)
        self.repo.ensure_owner('alpha')
        self.repo.ensure_owner('beta')
        self.provider = FailureProvider()
        self.service = ConsultationService(self.repo, model=self.provider)

    def cleanup(self):
        if hasattr(self, 'service'):
            with self.repo.transaction() as connection:
                runs = connection.execute(sql.SQL('SELECT id,retry_epoch FROM {}').format(self.repo.table('core_runs'))).fetchall()
            for run in runs:
                for epoch in range(run['retry_epoch'] + 1):
                    self.service.runtime.purge(run['id'], epoch)
        self.assertTrue(self.schema.startswith('test_model_failure_'))
        with self.repo.transaction() as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.repo.close()

    def charges(self, run_id):
        with self.repo.transaction('alpha') as connection:
            return connection.execute(sql.SQL('SELECT operation_id FROM {} WHERE owner=%s AND run_id=%s').format(
                self.repo.table('core_model_charges')), ('alpha',run_id)).fetchall()

    def test_failure_metadata_retains_scope_known_and_unknown_usage_and_cumulative_budget(self):
        run = self.service.submit(owner='alpha', message='合成学习问题', request_id='failure-retry', depth='standard')
        with self.assertRaises(ModelUnavailable):
            self.service.execute('alpha', run['id'])
        failed = self.repo.fetch_run('alpha', run['id'])
        self.assertEqual((failed['status'], failed['calls'], failed['attempts']), ('failed',1,1))
        first = self.repo.list('alpha','model_call')[0]
        self.assertEqual((first['owner_user_id'], first['subject_id'], first['status']), ('alpha','self','failed'))
        self.assertEqual(first['code'], 'MODEL_UNAVAILABLE')
        self.assertEqual(first['failure_code'], 'MODEL_MAX_TOKENS')
        self.assertTrue(first['usage_known'])
        self.assertEqual(first['usage'], {'input_tokens':19,'output_tokens':7})
        self.assertEqual(self.repo.list('beta','model_call'), [])
        with self.assertRaises(LeaseConflict):
            self.service.execute('alpha', run['id'])
        self.assertEqual(self.provider.calls, 1)
        self.repo.prepare_retry('alpha', run['id'])
        with self.assertRaises(ModelUnavailable):
            self.service.execute('alpha', run['id'])
        retry = self.repo.fetch_run('alpha', run['id'])
        self.assertEqual((retry['status'], retry['calls'], retry['attempts']), ('failed',2,2))
        self.assertEqual(self.provider.calls, 2)
        records = self.repo.list('alpha','model_call')
        self.assertEqual(len(records), 2)
        unknown = next(record for record in records if record['reason']=='network')
        self.assertFalse(unknown['usage_known'])
        self.assertEqual(unknown['usage'], {})
        self.assertNotIn('input_tokens', unknown)
        self.assertNotIn('PRIVATE_DIAGNOSTIC_693', json.dumps(records))
        self.assertEqual(len({row['operation_id'] for row in self.charges(run['id'])}), 2)
        malformed = self.service.submit(owner='alpha', message='合成无效契约', request_id='bad-contract', depth='standard')
        with patch.object(self.provider, 'generate', return_value={'output':{'invalid':'PRIVATE_CONTRACT_694'},
            'usage':{'input_tokens':9,'output_tokens':0,'provider_extension':'PRIVATE_USAGE_695'},
            'model':'synthetic', 'latency_seconds':0.01}):
            with self.assertRaises(InvalidAnswer):
                self.service.execute('alpha', malformed['id'])
        parse_failure = next(record for record in self.repo.list('alpha','model_call') if record['run_id']==malformed['id'])
        self.assertEqual(parse_failure['failure_code'], 'MODEL_OUTPUT_CONTRACT')
        self.assertEqual(parse_failure['usage'], {'input_tokens':9,'output_tokens':0})
        self.assertTrue(parse_failure['usage_known'])
        self.assertNotIn('PRIVATE_', json.dumps(parse_failure))
        self.assertEqual(self.repo.fetch_run('alpha',malformed['id'])['calls'], 1)

    def test_cancel_revoke_or_expire_before_failure_return_prevents_late_diagnostics_but_keeps_charge(self):
        for action in ('cancel','revoke','expire'):
            with self.subTest(action=action):
                source = self.service.memory.receive('alpha', content='我喜欢合成晨间学习', source_id=action)
                fact = self.service.memory.save_fact('alpha','self',source['id'],source['content'],'preference')
                run = self.service.submit(owner='alpha', message=source['content'], source_message_id=source['id'],
                                          request_id='late-failure-'+action, depth='standard')

                def invalidate():
                    active = self.repo.fetch_run('alpha',run['id'])
                    if action=='cancel':
                        self.repo.fail_run('alpha',run['id'],'SYNTHETIC_CANCEL',active['lease_token'],status='cancelled')
                    elif action=='revoke':
                        self.service.memory.retire_fact('alpha',fact['id'],expected_revision=fact['revision'],scope='source')
                    else:
                        with self.repo.transaction('alpha') as connection:
                            connection.execute(sql.SQL("UPDATE {} SET lease_until=now()-interval '1 second' WHERE owner=%s AND id=%s").format(
                                self.repo.table('core_runs')), ('alpha',run['id']))

                self.provider.during_call = invalidate
                with self.assertRaises(LeaseConflict):
                    self.service.execute('alpha',run['id'])
                current = self.repo.fetch_run('alpha',run['id'])
                self.assertEqual(current['calls'], 1)
                self.assertEqual(len(self.charges(run['id'])), 1)
                self.assertEqual(current['status'], {'cancel':'cancelled','revoke':'revoked','expire':'running'}[action])
                self.assertFalse(any(record.get('run_id')==run['id'] for record in self.repo.list('alpha','model_call')))
                self.assertFalse(any(record.get('run_id')==run['id'] for record in self.repo.list('alpha','runtime_step')))


if __name__ == '__main__':
    unittest.main()
