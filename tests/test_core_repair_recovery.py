"""One logical repair, real PG/Core/LangGraph, real provider parser, fake HTTP only."""
import asyncio
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
import uuid

import httpx
from psycopg import sql

from mingjing_core.adapters.model import ConfiguredModel
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.domain.consultation import FinalAnswer, SpecialistAnswer, InvalidAnswer, ModelUnavailable
from mingjing_core.domain.contracts import BudgetExceeded, EvidenceError
from mingjing_core.repositories.postgres import PostgresRepository
from tests.test_core_memory import test_dsn
from tools.evaluate_core_provider import consult_with_recovery


class CoreRepairRecovery(unittest.TestCase):
    def setUp(self):
        self.schema='test_repair_recovery_'+uuid.uuid4().hex[:16]
        self.repo=PostgresRepository(test_dsn(),schema=self.schema)
        self.repo.ensure_owner('fictional')
        self.service=ConsultationService(self.repo,model=ConfiguredModel(key='synthetic-test-only',base='https://synthetic.invalid/v1',model='synthetic'))
        self.requests=[];self.repairs=[]
        self.behavior=['success']
        self.decision=False
        real_client=httpx.Client
        transport=httpx.MockTransport(self.respond)
        self.provider_patch=patch('mingjing_core.adapters.model.httpx.Client',side_effect=lambda *args,**kwargs:real_client(transport=transport))
        self.provider_patch.start()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.provider_patch.stop()
        with self.repo.transaction() as connection:
            rows=connection.execute(sql.SQL('SELECT id,retry_epoch FROM {}').format(self.repo.table('core_runs'))).fetchall()
        for row in rows:
            for epoch in range(row['retry_epoch']+1):self.service.runtime.purge(row['id'],epoch)
        self.assertTrue(self.schema.startswith('test_repair_recovery_'))
        with self.repo.transaction() as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.repo.close()

    @staticmethod
    def answer(*,invalid=False,decision=False):
        output={'plain_summary':'先写一个学习目标。','explanation':'从小行动开始，再核对实际条件。',
                'actions':['写下一条学习目标。'],'decision_options':[],
                'cited_fact_ids':['invented-synthetic-fact'] if invalid else [],'cited_claim_ids':[]}
        if decision:
            output.update(plain_summary='课程A报名零风险，而且完全可逆。' if invalid else '先核实两项课程的费用与退出条件，再比较白天安排。',
                          explanation='费用与退出条件尚未确认，不能承诺零风险或完全可逆。',
                          actions=['向课程方索取费用与退出条款。'],cited_fact_ids=[],decision_options=[
                              {'option':'A：核实后报名白天课程','benefit':'可以安排白天学习。','cost':'费用待确认。','risk':'退出规则待确认。','reversibility':'退款与退出条件待核实。','first_step':'索取书面费用与退出条款。'},
                              {'option':'B：暂缓报名并核实替代安排','benefit':'保留核实信息的时间。','cost':'暂缓期间学习进度可能受影响。','risk':'名额与后续安排待确认。','reversibility':'是否能后续报名待确认。','first_step':'询问下一期白天课程安排。'}])
        return output

    def respond(self,request):
        body=json.loads(request.content);schema=body['tools'][0]['input_schema']
        payload=json.loads(body['messages'][0]['content'][0]['text'])
        phase='repair' if 'errors' in payload else 'intake' if schema.get('title')=='Intake' else 'synthesis_or_review'
        self.requests.append(phase)
        if phase=='intake':
            output={'plan':{'target_date':'2026-10-11','systems':[],'mode':'decision' if self.decision else 'conversation','decision':self.decision},'proposals':[]}
        elif phase=='repair':
            self.repairs.append(deepcopy(payload))
            behavior=self.behavior.pop(0) if len(self.behavior)>1 else self.behavior[0]
            if behavior=='network':raise httpx.ReadTimeout('PRIVATE_SYNTHETIC_PROVIDER_BODY',request=request)
            if behavior=='unknown_crash':raise RuntimeError('PRIVATE_SYNTHETIC_PROVIDER_BODY')
            if behavior=='zero_tool':
                return httpx.Response(200,json={'content':[],'stop_reason':'end_turn','usage':{'input_tokens':11,'output_tokens':7}})
            if behavior=='http401':return httpx.Response(401,text='PRIVATE_SYNTHETIC_PROVIDER_BODY')
            if behavior=='http503':return httpx.Response(503,text='PRIVATE_SYNTHETIC_PROVIDER_BODY')
            if behavior=='max_tokens':return httpx.Response(200,json={'content':[],'stop_reason':'max_tokens','usage':{'input_tokens':11,'output_tokens':7}})
            output={'invalid_field':'PRIVATE_SYNTHETIC_PROVIDER_BODY'} if behavior=='bad_contract' else self.answer(invalid=behavior=='bad_semantics',decision=self.decision)
        else:output=self.answer(invalid=True,decision=self.decision)
        return httpx.Response(200,json={'content':[{'type':'tool_use','name':'submit','input':output}],
                                       'stop_reason':'tool_use','usage':{'input_tokens':11,'output_tokens':7}})

    def consult(self,request_id='repair-business',depth='standard'):
        message='合成课程选择：A是白天课程，B是暂缓核实；两者费用与退出条件未知。请比较两条路径。' if self.decision else '合成学习练习，请给一个小行动。'
        return asyncio.run(self.service.consult(owner='fictional',message=message,request_id=request_id,depth=depth))

    def current(self,request_id='repair-business'):
        with self.repo.transaction('fictional') as connection:
            row=connection.execute(sql.SQL('SELECT id FROM {} WHERE owner=%s AND operation_id=%s').format(self.repo.table('core_runs')),('fictional',request_id)).fetchone()
        return self.repo.fetch_run('fictional',row['id'])

    def retry(self,run):
        prepared=self.repo.prepare_retry('fictional',run['id'])
        if prepared['purge_checkpoint']:self.service.runtime.purge(run['id'],run['retry_epoch'])
        return self.service.execute('fictional',run['id'])

    def diagnostics(self,run):
        return sorted((row for row in self.repo.list('fictional','model_call') if row.get('run_id')==run['id']),key=lambda row:row.get('call_index',0))

    def repair_diagnostics(self,run):
        return [row for row in self.diagnostics(run) if row.get('repair_identity')]

    def test_zero_tool_same_repair_round_recovers_through_real_evaluation_helper(self):
        self.decision=True;self.behavior=['zero_tool','success'];attempts=[]
        result=asyncio.run(consult_with_recovery(self.service,attempts,owner='fictional',message='合成课程选择：A是白天课程，B是暂缓核实；两者费用与退出条件未知。请比较两条路径。',request_id='repair-business',depth='standard'))
        run=self.current();repair=self.repair_diagnostics(run)
        self.assertEqual((run['status'],run['calls'],run['call_limit'],run['attempts'],run['retry_epoch']),('succeeded',4,6,2,0))
        self.assertEqual([row['calls'] for row in attempts],[3,4]);self.assertEqual(len({row['run_id'] for row in attempts}),1)
        self.assertEqual([row['repair_outcome'] for row in repair],['transient_failure','succeeded'])
        self.assertEqual([row['call_index'] for row in repair],[3,4]);self.assertEqual(repair[0]['tool_count'],0)
        self.assertEqual(len({row['repair_identity'] for row in repair}),1)
        self.assertEqual(self.repairs[0],self.repairs[1]);self.assertEqual(len(self.requests),run['calls'])
        self.assertIn('不能承诺完全可逆或无损失','；'.join(self.repairs[0]['errors']))
        self.assertIn('零风险',self.repairs[0]['previous']['plain_summary'])
        self.assertEqual(len(result['decision_options']),2)
        self.assertTrue(result['validation']['valid']);self.assertTrue(run['repair_used'])
        before=len(self.requests);replay=self.consult()
        self.assertEqual(replay,result);self.assertEqual(len(self.requests),before)

    def test_network_retry_keeps_identity_usage_and_cumulative_calls(self):
        self.behavior=['network','success']
        with self.assertRaises(ModelUnavailable):self.consult()
        failed=self.current();self.assertEqual(failed['calls'],3)
        result=self.retry(failed);run=self.current();rows=self.repair_diagnostics(run)
        self.assertEqual((run['status'],run['calls'],run['call_limit']),('succeeded',4,6))
        self.assertEqual(rows[0]['reason'],'network');self.assertFalse(rows[0]['usage_known'])
        self.assertEqual(rows[1]['usage'],{'input_tokens':11,'output_tokens':7})
        self.assertNotIn('PRIVATE_SYNTHETIC_PROVIDER_BODY',json.dumps(rows))
        self.assertEqual(result['meta']['core_run']['run_id'],failed['id'])

    def test_http503_retries_only_the_same_round_and_preserves_safe_failure_metadata(self):
        self.behavior=['http503','success'];attempts=[]
        result=asyncio.run(consult_with_recovery(self.service,attempts,owner='fictional',message='合成学习练习，请给一个小行动。',request_id='repair-business',depth='standard'))
        run=self.current();rows=self.repair_diagnostics(run)
        self.assertEqual((run['calls'],run['call_limit']),(4,6));self.assertTrue(result['validation']['valid'])
        self.assertEqual(rows[0]['provider_http_status'],503);self.assertEqual(rows[0]['repair_outcome'],'transient_failure')
        self.assertEqual(len({r['repair_identity'] for r in rows}),1)
        self.assertNotIn('PRIVATE_SYNTHETIC_PROVIDER_BODY',json.dumps(rows))

    def test_repeated_transient_failure_stops_at_global_standard_and_deep_caps(self):
        for depth,limit in [('standard',6),('deep',10)]:
            with self.subTest(depth=depth):
                self.behavior=['zero_tool'];key='repair-cap-'+depth;before=len(self.requests)
                with self.assertRaises(ModelUnavailable):self.consult(key,depth)
                current=self.current(key)
                while current['calls']<limit:
                    with self.assertRaises(ModelUnavailable):self.retry(current)
                    current=self.current(key)
                self.assertEqual(current['calls'],limit);self.assertEqual(current['call_limit'],limit)
                self.assertEqual(len(self.requests)-before,limit)
                self.assertEqual(len({r['repair_identity'] for r in self.repair_diagnostics(current)}),1)
                with self.assertRaises(BudgetExceeded):self.repo.prepare_retry('fictional',current['id'])
                self.assertEqual(self.current(key)['calls'],limit);self.assertIsNone(current['result'])

    def test_fast_cap_cannot_be_reset_to_make_room_for_a_repair(self):
        with self.assertRaises(BudgetExceeded):self.consult(depth='fast')
        run=self.current();self.assertEqual((run['calls'],run['call_limit'],run['repair_used']),(2,2,False))
        with self.assertRaises(BudgetExceeded):self.repo.prepare_retry('fictional',run['id'])
        self.assertEqual(len(self.requests),2)

    def test_contract_invalid_or_auth_failure_cannot_open_a_second_repair_attempt(self):
        for behavior,error in [('bad_contract',InvalidAnswer),('http401',ModelUnavailable),('max_tokens',ModelUnavailable)]:
            with self.subTest(behavior=behavior):
                self.behavior=[behavior];key='repair-terminal-'+behavior;before=len(self.requests)
                with self.assertRaises(error):self.consult(key)
                run=self.current(key)
                with self.assertRaises(BudgetExceeded):self.retry(run)
                self.assertEqual(self.current(key)['calls'],3);self.assertEqual(len(self.requests)-before,3)
                row=self.repair_diagnostics(run)[0]
                self.assertIn(row['repair_outcome'],('contract_failure','terminal_failure'))
                self.assertIsNone(self.current(key)['result'])

    def test_successful_but_semantically_invalid_repair_is_not_a_new_round(self):
        self.behavior=['bad_semantics']
        with self.assertRaises(InvalidAnswer):self.consult()
        failed=self.current();before=len(self.requests)
        with self.assertRaises(InvalidAnswer):self.retry(failed)
        self.assertEqual(self.current()['calls'],3);self.assertEqual(len(self.requests),before)
        self.assertEqual(self.repair_diagnostics(failed)[0]['repair_outcome'],'succeeded')
        resumed=self.repo.prepare_retry('fictional',failed['id'])['run'];claimed=self.repo.claim_run('fictional',resumed['id'])
        old=self.repair_diagnostics(claimed)[0]
        with self.assertRaises(BudgetExceeded):self.repo.charge_run('fictional',claimed['id'],'another-repair',claimed['lease_token'],repair=True,repair_identity=old['repair_identity'],purpose='repair')

    def test_unknown_crash_started_ledger_fails_closed_on_resume(self):
        self.behavior=['unknown_crash']
        with self.assertRaises(RuntimeError):self.consult()
        failed=self.current();row=self.repair_diagnostics(failed)[0]
        self.assertEqual((row['status'],row['repair_outcome']),('started','unknown'))
        self.assertEqual(row['call_index'],3);self.assertNotIn('PRIVATE_SYNTHETIC_PROVIDER_BODY',json.dumps(row))
        self.behavior=['success']
        with self.assertRaises(BudgetExceeded):self.retry(failed)
        self.assertEqual(self.current()['calls'],3);self.assertEqual(len(self.requests),3)

    def test_changed_dependencies_create_a_new_epoch_without_reopening_repair(self):
        self.behavior=['network']
        with self.assertRaises(ModelUnavailable):self.consult()
        failed=self.current()
        source=self.service.memory.receive('fictional','self','请记住：我不能上夜班。',source_id='new-explicit-synthetic-source')
        fact=self.service.memory.save_fact('fictional','self',source['id'],'我不能上夜班','constraint')
        self.assertEqual(fact['write_status'],'saved')
        with self.assertRaises(BudgetExceeded):self.retry(failed)
        current=self.current();self.assertEqual(current['retry_epoch'],1)
        self.assertEqual(current['call_limit'],6);self.assertEqual(len(self.repairs),1);self.assertIsNone(current['result'])
        self.assertFalse(self.repo.list('fictional','report'))

    def test_changed_payload_schema_or_purpose_cannot_retry_the_original_repair(self):
        self.behavior=['network']
        with self.assertRaises(ModelUnavailable):self.consult()
        failed=self.current();self.repo.prepare_retry('fictional',failed['id']);claimed=self.repo.claim_run('fictional',failed['id'])
        original=self.repairs[0];variants=[]
        changed=deepcopy(original);changed['instruction']+=' 合成的新指令。'
        variants.append(('repair',changed,FinalAnswer));variants.append(('repair_second',original,FinalAnswer));variants.append(('repair',original,SpecialistAnswer))
        for purpose,payload,contract in variants:
            with self.subTest(purpose=purpose,contract=contract.__name__):
                with self.assertRaises(BudgetExceeded):self.service._call('fictional',claimed,claimed['lease_token'],purpose,deepcopy(payload),contract,repair=True)
                self.assertEqual(self.current()['calls'],3);self.assertEqual(len(self.requests),3)

    def test_legacy_unidentified_repair_charge_and_idempotent_charge_intent_are_fail_closed(self):
        run=self.service.submit(owner='fictional',message='合成原业务',request_id='legacy-repair',depth='standard')
        claimed=self.repo.claim_run('fictional',run['id'])
        self.repo.charge_run('fictional',run['id'],'legacy-charge',claimed['lease_token'],repair=True)
        with self.assertRaises(BudgetExceeded):self.repo.charge_run('fictional',run['id'],'new-repair',claimed['lease_token'],repair=True,repair_identity='a'*64,purpose='repair')
        self.assertEqual(self.repo.fetch_run('fictional',run['id'])['calls'],1)
        other=self.service.submit(owner='fictional',message='合成另外业务',request_id='identified-repair',depth='standard')
        self.repo.fail_run('fictional',run['id'],'synthetic-end',claimed['lease_token'])
        other=self.repo.claim_run('fictional',other['id']);token=other['lease_token']
        first=self.repo.charge_run('fictional',other['id'],'identified-charge',token,repair=True,repair_identity='a'*64,purpose='repair')
        repeat=self.repo.charge_run('fictional',other['id'],'identified-charge',token,repair=True,repair_identity='a'*64,purpose='repair')
        self.assertEqual(first['calls'],repeat['calls'])
        with self.assertRaises(EvidenceError):self.repo.charge_run('fictional',other['id'],'identified-charge',token,repair=True,repair_identity='b'*64,purpose='repair')


if __name__=='__main__':unittest.main()
