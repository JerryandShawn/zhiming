"""Synthetic official SDK events and real PG, with no external sends/models."""
import asyncio
import json
import unittest
import uuid
from datetime import UTC, datetime, timedelta

from psycopg import sql
from test_core_memory import test_dsn as core_test_dsn
from mingjing_core.adapters.feishu_gateway import FeishuGateway, build_sdk_client
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock


def event(ident='om_syntheticMessage', **changes):
    value={'header':{'event_type':'im.message.receive_v1','event_id':'synthetic-event'},
           'event':{'sender':{'sender_type':'user','sender_id':{'open_id':'ou_syntheticAuthor'}},
                    'message':{'message_id':ident,'chat_id':'oc_syntheticPrivate',
                               'chat_type':'p2p','message_type':'text',
                               'create_time':'1791676800000','content':json.dumps({'text':'合成问题'})}}}
    value['event']['message'].update(changes)
    return value


class SyntheticProvider:
    """The provider is synthetic; all contracts and business effects are real."""
    def __init__(self):self.requests=[]

    def generate(self,*,system,payload,schema,purpose):
        self.requests.append({'purpose':purpose,'payload':payload})
        data=payload['reference_data']
        if purpose=='intake':
            output={'plan':{'mode':'conversation','topic':'general','systems':[],
                'target_date':data['today'],'time_scale':'daily','decision':False,
                'rationale':'本地合成对话','missing_inputs':[]},
                'proposals':[],'retire_fact_ids':[],'attachment_observations':[]}
        else:
            output={'plain_summary':'Core 已验证的合成结论','explanation':'仅使用本轮有效资料。',
                'actions':[],'decision_options':[],'follow_up':'','professional_appendix':'',
                'cited_fact_ids':[fact['id'] for fact in data.get('facts',[])],
                'cited_claim_ids':[claim['claim_id'] for claim in data.get('claims',[])],
                'caveats':[]}
        return {'output':output,'usage':{},'model':'synthetic-feishu-provider'}


class ObservedCore(ConsultationService):
    """Observe executions/results without replacing any service operation."""
    def __init__(self,repo):
        super().__init__(repo,model=SyntheticProvider())
        self.executions=0;self.body=None

    def execute(self,owner,run_id,emit=None):
        self.executions+=1
        result=super().execute(owner,run_id,emit)
        self.body=result['answer']
        return result


class FeishuGatewayPostgresTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.previous_clock=get_clock();self.clock=FrozenClock(datetime(2026,10,17,12,tzinfo=UTC))
        set_clock(self.clock);self.addCleanup(set_clock,self.previous_clock)
        self.schema='test_feishu_'+uuid.uuid4().hex[:20]
        self.repo=PostgresRepository(core_test_dsn(),schema=self.schema)
        self.addCleanup(self.cleanup)
        self.repo.ensure_owner('feishu-owner');self.repo.ensure_owner('other-owner')
        self.repo.bind_channel('feishu-owner','feishu','ou_syntheticAuthor')
        self.core=ObservedCore(self.repo);self.sent=[]
        def transport(target,content,operation):
            self.sent.append((target,content,operation))
            return 'om_syntheticReceipt'
        self.gateway=FeishuGateway(self.core,transport)

    async def run_external_worker(self,accepted: dict,*,gateway: FeishuGateway | None=None,advance: bool=True) -> dict:
        gateway=gateway or self.gateway
        if advance:self.clock.advance(timedelta(milliseconds=2500))
        gateway.ingress.flush_due()
        item=self.repo.get('feishu-owner','request',accepted['inbound_id'])
        run=self.repo.fetch_run('feishu-owner',item['run_id'])
        if run['status']=='queued':self.core.execute('feishu-owner',run['id'])
        return await gateway.process('feishu-owner',accepted['inbound_id'])

    def cleanup(self):
        if hasattr(self,'core'):
            with self.repo.transaction() as connection:
                rows=connection.execute(sql.SQL('SELECT id,retry_epoch FROM {}').format(self.repo.table('core_runs'))).fetchall()
            for row in rows:
                for epoch in range(row['retry_epoch']+1):self.core.runtime.purge(row['id'],epoch)
        self.assertTrue(self.schema.startswith('test_feishu_'))
        with self.repo.pool.connection() as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.repo.close()

    async def test_official_typed_event_exact_payload_and_duplicate_once(self):
        from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
        typed=P2ImMessageReceiveV1(event())
        buffered=await asyncio.gather(self.gateway.handle(typed),self.gateway.handle(typed))
        self.assertEqual([result['status'] for result in buffered],['buffering','buffering'])
        self.assertEqual(self.core.executions,0);self.assertEqual(self.sent,[])
        first=await self.run_external_worker(buffered[0])
        results=[first,await self.gateway.handle(typed)]
        self.assertEqual([result['status'] for result in results],['sent','sent'])
        self.assertEqual(self.core.executions,1);self.assertEqual(len(self.sent),1)
        target,body,operation=self.sent[0]
        self.assertEqual(target,'ou_syntheticAuthor');self.assertEqual(body,self.core.body)
        self.assertLessEqual(len(operation),50)
        originals=[row for row in self.repo.list('feishu-owner','message') if row.get('role')=='user']
        self.assertEqual(len(originals),1)
        self.assertEqual(originals[0]['channel'],'feishu')
        self.assertEqual(originals[0]['external_id'],'ou_syntheticAuthor')
        self.assertEqual([request['purpose'] for request in self.core.model.requests],['intake','synthesis'])
        run=self.repo.fetch_run('feishu-owner',results[0]['run_id'])
        self.assertEqual(run['result']['answer'],body)
        self.assertEqual(run['calls'],2)
        self.assertEqual(self.repo.list('other-owner','message'),[])
        self.assertEqual((await self.gateway.tick())['failed'],0)
        self.assertEqual(len(self.sent),1)

    async def test_accepted_then_interrupted_poll_recovers_original_queue(self):
        accepted=self.gateway.accept(event())
        self.assertEqual(self.core.executions,0);self.assertEqual(self.sent,[])
        self.assertIsNone(accepted['run_id']);self.assertEqual(self.repo.queued_runs(),[])
        resumed=FeishuGateway(self.core,self.gateway.delivery.transport)
        self.clock.advance(timedelta(milliseconds=2500))
        report=await resumed.tick()
        self.assertEqual(report,{'processed':1,'failed':0})
        self.assertEqual(self.core.executions,0);self.assertEqual(self.sent,[])
        await self.run_external_worker(accepted,gateway=resumed,advance=False)
        self.assertEqual(self.core.executions,1);self.assertEqual(len(self.sent),1)

    async def test_unknown_bot_group_and_nontext_cannot_enter_core(self):
        unknown=event();unknown['event']['sender']['sender_id']['open_id']='ou_unknownAuthor'
        with self.assertRaises(ScopeError):self.gateway.accept(unknown)
        bot=event();bot['event']['sender']['sender_type']='app'
        for ignored in [bot,event(chat_type='group'),event(message_type='image')]:
            self.assertEqual(self.gateway.accept(ignored)['status'],'ignored')
        self.assertEqual(self.repo.list('feishu-owner','message'),[])
        self.assertEqual(self.repo.queued_runs(),[]);self.assertEqual(self.sent,[])

    async def test_same_event_id_cannot_replace_text_or_author(self):
        self.gateway.accept(event())
        with self.assertRaises(EvidenceError):self.gateway.accept(event(content=json.dumps({'text':'伪造替换问题'})))
        self.assertEqual(len(self.repo.list('feishu-owner','message')),1)
        self.assertEqual(self.core.executions,0)

    async def test_literal_original_preserves_surrounding_whitespace(self):
        original='  合成原话\n '
        accepted=self.gateway.accept(event(content=json.dumps({'text':original})))
        source=self.repo.list('feishu-owner','message')[0]
        self.assertEqual(source['content'],original)
        self.clock.advance(timedelta(milliseconds=2500));self.gateway.ingress.flush_due()
        item=self.repo.get('feishu-owner','request',accepted['inbound_id'])
        self.assertEqual(self.repo.fetch_run('feishu-owner',item['run_id'])['request']['message'],original)

    async def test_ambiguous_send_is_persistent_and_never_replayed(self):
        def uncertain(target,content,operation):
            self.sent.append((target,content,operation));raise TimeoutError('synthetic timeout')
        self.gateway=FeishuGateway(self.core,uncertain)
        first=await self.run_external_worker(await self.gateway.handle(event()))
        self.assertEqual(first['status'],'uncertain')
        duplicate=await self.gateway.handle(event())
        self.assertEqual(duplicate['status'],'uncertain')
        await FeishuGateway(self.core,uncertain).tick()
        self.assertEqual(len(self.sent),1);self.assertEqual(self.core.executions,1)

    async def test_deleted_original_cannot_reenter_or_be_sent(self):
        accepted=self.gateway.accept(event())
        source=self.repo.list('feishu-owner','message')[0]
        self.repo.delete('feishu-owner','message',source['id'],expected_revision=source['revision'])
        self.repo.invalidate_derived('feishu-owner',[],[source['id']])
        with self.assertRaises(EvidenceError):self.gateway.accept(event())
        with self.assertRaises(EvidenceError):await self.gateway.process('feishu-owner',accepted['inbound_id'])
        self.assertEqual(self.sent,[]);self.assertEqual(self.core.executions,0)

    async def test_official_sdk_receiver_constructs_without_network(self):
        client=build_sdk_client(lambda event:None,app_id='cli_synthetic',app_secret='synthetic-only-not-real')
        self.assertIsNotNone(client._event_handler)
        self.assertEqual(self.core.executions,0);self.assertEqual(self.sent,[])


if __name__=='__main__':unittest.main()
