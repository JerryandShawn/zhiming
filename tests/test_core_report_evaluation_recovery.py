"""Real PG/Core/report manifests; only provider HTTP responses are synthetic."""
import asyncio
import json
import unittest
from unittest.mock import patch
import uuid

import httpx
from psycopg import sql

from mingjing_core.adapters.channels.reports import CoreReportAdapter
from mingjing_core.adapters.model import ConfiguredModel
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.domain.consultation import InvalidAnswer, ModelUnavailable
from mingjing_core.repositories.postgres import PostgresRepository
from tests.test_core_memory import test_dsn
from tools.evaluate_core_provider import report_with_recovery


class ReportEvaluationRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.schema='test_report_evaluation_'+uuid.uuid4().hex[:16]
        self.repo=PostgresRepository(test_dsn(),schema=self.schema)
        self.repo.ensure_owner('synthetic')
        self.external='synthetic-report-evaluation'
        self.repo.bind_channel('synthetic','report',self.external,binding_kind='task')
        self.service=ConsultationService(self.repo,model=ConfiguredModel(
            key='synthetic-test-only',base='https://synthetic.invalid/v1',model='synthetic'))
        self.adapter=CoreReportAdapter('.',service=self.service)
        self.behavior=[];self.requests=[];self.bad_reference=False
        real_client=httpx.Client
        transport=httpx.MockTransport(self.respond)
        self.provider_patch=patch('mingjing_core.adapters.model.httpx.Client',
            side_effect=lambda *args,**kwargs:real_client(transport=transport))
        self.provider_patch.start();self.addCleanup(self.cleanup)

    def cleanup(self):
        self.provider_patch.stop()
        with self.repo.transaction() as connection:
            runs=connection.execute(sql.SQL('SELECT id,retry_epoch FROM {}').format(self.repo.table('core_runs'))).fetchall()
        for run in runs:
            for epoch in range(run['retry_epoch']+1):self.service.runtime.purge(run['id'],epoch)
        self.assertTrue(self.schema.startswith('test_report_evaluation_'))
        with self.repo.transaction() as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.repo.close()

    def respond(self,request):
        body=json.loads(request.content);schema=body['tools'][0]['input_schema']
        payload=json.loads(body['messages'][0]['content'][0]['text'])
        phase='repair' if 'errors' in payload else 'intake' if schema.get('title')=='Intake' else 'synthesis'
        self.requests.append(phase)
        behavior=self.behavior.pop(0) if self.behavior else 'success'
        if behavior=='network':raise httpx.ReadTimeout('PRIVATE_SYNTHETIC_PROVIDER_BODY',request=request)
        if behavior.startswith('http'):return httpx.Response(int(behavior[4:]),text='PRIVATE_SYNTHETIC_PROVIDER_BODY')
        if behavior=='json':return httpx.Response(200,text='PRIVATE_SYNTHETIC_PROVIDER_BODY')
        if behavior=='tool_input':
            return httpx.Response(200,json={'content':[{'type':'tool_use','name':'submit','input':'PRIVATE_SYNTHETIC_PROVIDER_BODY'}]})
        if behavior in ('zero_tool','max_tokens'):
            return httpx.Response(200,json={'content':[],'stop_reason':'max_tokens' if behavior=='max_tokens' else 'end_turn',
                                           'usage':{'input_tokens':11,'output_tokens':0}})
        if phase=='intake':
            output={'plan':{'mode':'report','topic':'study','systems':[],'target_date':'2026-10-12',
                'time_scale':'daily','decision':False,'rationale':'合成报告测试','missing_inputs':[]},
                'proposals':[],'retire_fact_ids':[],'attachment_observations':[]}
        else:
            output={'plain_summary':'先核对可用的白天时间。','explanation':'执行小行动后再核对实际反馈。',
                'actions':['写下一条学习目标。'],'decision_options':[],
                'cited_fact_ids':['invented-synthetic-fact'] if self.bad_reference else [],'cited_claim_ids':[]}
        return httpx.Response(200,json={'content':[{'type':'tool_use','name':'submit','input':output}],
            'stop_reason':'tool_use','usage':{'input_tokens':11,'output_tokens':7}})

    def prepare(self,attempts,*,day='2026-10-12',depth='standard',max_recoveries=2,operation_id=None):
        return asyncio.run(report_with_recovery(self.adapter,attempts,external_id=self.external,
            kind='daily',day=day,depth=depth,max_recoveries=max_recoveries,operation_id=operation_id))

    def run_for(self,operation=None):
        operation=operation or 'report:'+self.external+':daily:2026-10-12'
        with self.repo.transaction('synthetic') as connection:
            row=connection.execute(sql.SQL('SELECT id FROM {} WHERE owner=%s AND operation_id=%s').format(
                self.repo.table('core_runs')),('synthetic',operation)).fetchone()
        return self.repo.fetch_run('synthetic',row['id'])

    def charges(self,run):
        return sorted((row for row in self.repo.list('synthetic','model_call') if row.get('run_id')==run['id']),
                      key=lambda row:row['created_at'])

    def assert_no_manifest_or_delivery(self):
        self.assertEqual(self.repo.list('synthetic','report'),[])
        self.assertEqual(self.service.outbox.status('synthetic')['rows'],[])

    def test_two_zero_submit_attempts_then_same_operation_manifest_with_four_calls(self):
        self.behavior=['zero_tool','zero_tool'];attempts=[]
        result=self.prepare(attempts);run=self.run_for();charges=self.charges(run)
        self.assertEqual((run['status'],run['calls'],run['call_limit'],run['attempts']),('succeeded',4,6,3))
        self.assertEqual(self.requests,['intake','intake','intake','synthesis'])
        self.assertEqual([row['calls'] for row in attempts],[1,2,4])
        self.assertEqual([row['status'] for row in attempts],['failed','failed','succeeded'])
        self.assertEqual([row.get('reason') for row in attempts[:2]],['tool_count','tool_count'])
        self.assertEqual([row.get('tool_count') for row in attempts[:2]],[0,0])
        self.assertEqual({row['run_id'] for row in attempts},{run['id']})
        self.assertEqual({row['operation_id'] for row in attempts},{run['operation_id']})
        self.assertEqual(len(charges),4);self.assertEqual(len({row['id'] for row in charges}),4)
        with self.repo.transaction('synthetic') as connection:
            count=connection.execute(sql.SQL('SELECT count(*) AS n FROM {} WHERE owner=%s AND run_id=%s').format(
                self.repo.table('core_model_charges')),('synthetic',run['id'])).fetchone()['n']
        self.assertEqual(count,4)
        self.assertEqual([row['status'] for row in charges],['failed','failed','succeeded','succeeded'])
        self.assertTrue(result['validation']['valid'])
        manifest=self.repo.get('synthetic','report',result['report']['business_id'])
        self.assertEqual(result['report']['date'],'2026-10-12')
        self.assertEqual(manifest['run_id'],run['id']);self.assertEqual(manifest['content'],result['answer'])
        self.assertEqual(len(self.repo.list('synthetic','report')),1)
        self.assertEqual(self.service.outbox.status('synthetic')['rows'],[])
        count=len(self.requests);replayed=self.prepare([])
        self.assertEqual(replayed,result);self.assertEqual(len(self.requests),count)
        self.assertEqual(len(self.repo.list('synthetic','report')),1)

    def test_exhausted_fast_budget_stops_without_manifest_or_delivery(self):
        self.behavior=['zero_tool']*4;attempts=[]
        with self.assertRaises(ModelUnavailable):self.prepare(attempts,depth='fast')
        run=self.run_for()
        self.assertEqual((run['status'],run['calls'],run['call_limit'],run['attempts']),('failed',2,2,2))
        self.assertEqual([row['calls'] for row in attempts],[1,2])
        self.assertEqual(len(self.requests),2);self.assertIsNone(run['result']);self.assert_no_manifest_or_delivery()

    def test_at_most_two_recoveries_even_with_remaining_standard_budget(self):
        self.behavior=['zero_tool']*4;attempts=[]
        with self.assertRaises(ModelUnavailable):self.prepare(attempts)
        run=self.run_for()
        self.assertEqual((run['status'],run['calls'],run['call_limit'],run['attempts']),('failed',3,6,3))
        self.assertEqual([row['calls'] for row in attempts],[1,2,3]);self.assertEqual(len(self.requests),3)
        self.assert_no_manifest_or_delivery()

    def test_transient_network_parser_and_http_failures_can_recover_same_explicit_operation(self):
        for behavior in ('network','json','tool_input','http429','http503'):
            with self.subTest(behavior=behavior):
                operation='synthetic-report-'+behavior;self.behavior=[behavior];attempts=[]
                before=len(self.requests);result=self.prepare(attempts,operation_id=operation)
                run=self.run_for(operation)
                self.assertEqual((run['status'],run['calls'],run['call_limit']),('succeeded',3,6))
                self.assertEqual(len(self.requests)-before,3)
                self.assertEqual([row['calls'] for row in attempts],[1,3])
                self.assertEqual({row['operation_id'] for row in attempts},{operation})
                self.assertEqual(result['report']['run_id'],run['id'])
                self.assertNotIn('PRIVATE_SYNTHETIC_PROVIDER_BODY',json.dumps(attempts))

    def test_authentication_and_max_tokens_failure_are_never_retried(self):
        for behavior in ('http401','http403','max_tokens'):
            with self.subTest(behavior=behavior):
                operation='synthetic-terminal-'+behavior;self.behavior=[behavior];attempts=[]
                before=len(self.requests)
                with self.assertRaises(ModelUnavailable):self.prepare(attempts,operation_id=operation)
                run=self.run_for(operation)
                self.assertEqual((run['status'],run['calls'],run['attempts']),('failed',1,1))
                self.assertEqual(len(self.requests)-before,1);self.assertEqual(len(attempts),1)
                self.assert_no_manifest_or_delivery()

    def test_reference_failure_keeps_diagnostics_but_never_starts_technical_recovery(self):
        self.bad_reference=True;attempts=[]
        with self.assertRaises(InvalidAnswer):self.prepare(attempts)
        run=self.run_for()
        self.assertEqual((run['status'],run['calls'],run['call_limit'],run['attempts']),('failed',3,6,1))
        self.assertEqual(self.requests,['intake','synthesis','repair'])
        self.assertEqual(len(attempts),1);self.assertEqual(attempts[0]['error_code'],'REFERENCE_ERROR')
        self.assert_no_manifest_or_delivery()

    def test_invalid_recovery_bound_makes_no_provider_or_business_run(self):
        for bound in (-1,3,True):
            with self.subTest(bound=bound):
                with self.assertRaises(ValueError):self.prepare([],max_recoveries=bound)
        self.assertEqual(self.requests,[])
        with self.repo.transaction('synthetic') as connection:
            count=connection.execute(sql.SQL('SELECT count(*) AS n FROM {}').format(self.repo.table('core_runs'))).fetchone()['n']
        self.assertEqual(count,0);self.assert_no_manifest_or_delivery()


if __name__=='__main__':unittest.main()
