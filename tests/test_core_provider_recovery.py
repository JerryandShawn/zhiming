"""Real service/PG recovery for the provider evaluation; only model replaced."""
import asyncio
import unittest

from mingjing_core.domain.consultation import ModelUnavailable, InvalidAnswer
from tests import test_core_model_diagnostics as diagnostics
from tools.evaluate_core_provider import consult_with_recovery


class EvaluationRecoveryTests(unittest.TestCase):
    cleanup = diagnostics.FailureDiagnosticPostgresTests.cleanup
    charges = diagnostics.FailureDiagnosticPostgresTests.charges

    def setUp(self):
        diagnostics.FailureDiagnosticPostgresTests.setUp(self)

    def evaluate(self, attempts):
        return asyncio.run(consult_with_recovery(self.service, attempts, owner='alpha',
            message='合成普通问答，请给一个小行动。',request_id='same-evaluation-operation',depth='standard'))

    def test_network_recovery_reuses_run_and_cumulative_budget(self):
        calls=[]
        def model(**kwargs):
            calls.append(kwargs['purpose'])
            if len(calls)==1:
                raise ModelUnavailable('合成网络失败',reason='network')
            if kwargs['purpose']=='intake':
                output={'plan':{'target_date':'2026-10-11','systems':[]},'proposals':[]}
            else:
                output={'plain_summary':'先做一个小行动。','actions':['写下当前目标。'],
                        'decision_options':[],'cited_fact_ids':[],'cited_claim_ids':[]}
            return {'output':output,'usage':{'input_tokens':1,'output_tokens':1},'model':'synthetic'}
        self.provider.generate=model
        attempts=[];result=self.evaluate(attempts)
        run=self.repo.fetch_run('alpha',result['meta']['core_run']['run_id'])
        self.assertEqual((run['status'],run['calls'],run['call_limit'],run['attempts']),('succeeded',3,6,2))
        self.assertEqual([a['calls'] for a in attempts],[1,3])
        self.assertEqual({a['run_id'] for a in attempts},{run['id']})
        self.assertEqual({a['operation_id'] for a in attempts},{'same-evaluation-operation'})
        self.assertEqual(len(self.charges(run['id'])),3)

    def test_authentication_failure_is_not_retried(self):
        calls=[]
        def model(**kwargs):
            calls.append(kwargs['purpose'])
            raise ModelUnavailable('合成认证失败',reason='http',provider_http_status=401)
        self.provider.generate=model
        attempts=[]
        with self.assertRaises(ModelUnavailable):self.evaluate(attempts)
        self.assertEqual(len(calls),1)
        self.assertEqual(attempts[0]['calls'],1)
        self.assertEqual(attempts[0]['provider_http_status'],401)

    def test_two_distinct_transient_failures_keep_one_run_and_all_charges(self):
        calls=[]
        def model(**kwargs):
            calls.append(kwargs['purpose'])
            if len(calls)<=2:
                raise ModelUnavailable('合成技术失败',reason='network' if len(calls)==1 else 'tool_count',tool_count=0)
            output=({'plan':{'target_date':'2026-10-11','systems':[]},'proposals':[]}
                    if kwargs['purpose']=='intake' else {'plain_summary':'先写下目标。','actions':['写下目标。'],
                        'decision_options':[],'cited_fact_ids':[],'cited_claim_ids':[]})
            return {'output':output,'usage':{'input_tokens':1,'output_tokens':1},'model':'synthetic'}
        self.provider.generate=model
        attempts=[];result=self.evaluate(attempts)
        run=self.repo.fetch_run('alpha',result['meta']['core_run']['run_id'])
        self.assertEqual((run['status'],run['calls'],run['call_limit'],run['attempts']),('succeeded',4,6,3))
        self.assertEqual([a['calls'] for a in attempts],[1,2,4])
        self.assertEqual([a['status'] for a in attempts],['failed','failed','succeeded'])
        self.assertEqual({a['run_id'] for a in attempts},{run['id']})
        self.assertEqual({a['operation_id'] for a in attempts},{'same-evaluation-operation'})
        self.assertEqual(len(self.charges(run['id'])),4)

    def test_repeated_transient_failure_stops_at_two_recoveries(self):
        calls=[]
        def model(**kwargs):
            calls.append(kwargs['purpose']);raise ModelUnavailable('合成网络失败',reason='network')
        self.provider.generate=model
        attempts=[]
        with self.assertRaises(ModelUnavailable):self.evaluate(attempts)
        self.assertEqual(len(calls),3)
        self.assertEqual([a['calls'] for a in attempts],[1,2,3])
        run=self.repo.fetch_run('alpha',attempts[0]['run_id'])
        self.assertEqual((run['status'],run['calls'],run['call_limit'],run['attempts']),('failed',3,6,3))
        self.assertIsNone(run['result'])
        self.assertEqual(len(self.charges(run['id'])),3)

    def test_fast_budget_can_stop_before_the_recovery_bound(self):
        calls=[]
        def model(**kwargs):
            calls.append(kwargs['purpose']);raise ModelUnavailable('合成网络失败',reason='network')
        self.provider.generate=model
        attempts=[]
        with self.assertRaises(ModelUnavailable):
            asyncio.run(consult_with_recovery(self.service,attempts,owner='alpha',message='合成问题',
                        request_id='fast-same-operation',depth='fast'))
        self.assertEqual(len(calls),2)
        run=self.repo.fetch_run('alpha',attempts[0]['run_id'])
        self.assertEqual((run['status'],run['calls'],run['call_limit']),('failed',2,2))
        self.assertEqual([a['calls'] for a in attempts],[1,2])

    def test_invalid_contract_is_not_retried_or_hidden(self):
        calls=[]
        def model(**kwargs):
            calls.append(kwargs['purpose'])
            return {'output':{'invalid':'synthetic'},'usage':{'input_tokens':1,'output_tokens':1}}
        self.provider.generate=model
        attempts=[]
        with self.assertRaises(InvalidAnswer):self.evaluate(attempts)
        self.assertEqual(len(calls),1)
        self.assertEqual(attempts,[])


if __name__=='__main__':unittest.main()
