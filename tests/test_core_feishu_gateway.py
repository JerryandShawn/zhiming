"""Synthetic official SDK events and real PG, with no external sends/models."""
import asyncio
import json
import unittest
import uuid

from psycopg import sql
from test_core_memory import test_dsn
from mingjing_core.adapters.feishu_gateway import FeishuGateway, build_sdk_client
from mingjing_core.adapters.delivery import OutboxService
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository


def event(ident='om_syntheticMessage', **changes):
    value={'header':{'event_type':'im.message.receive_v1','event_id':'synthetic-event'},
           'event':{'sender':{'sender_type':'user','sender_id':{'open_id':'ou_syntheticAuthor'}},
                    'message':{'message_id':ident,'chat_id':'oc_syntheticPrivate',
                               'chat_type':'p2p','message_type':'text',
                               'create_time':'1791676800000','content':json.dumps({'text':'合成问题'})}}}
    value['event']['message'].update(changes)
    return value


class SyntheticCore:
    def __init__(self,repo):
        self.repo=repo;self.memory=MemoryService(repo);self.outbox=OutboxService(repo)
        self.executions=0;self.body='Core 已验证的合成结论\n\n专业附录：仅合成依据'

    def submit(self,*,owner,subject='self',message,conversation_id,request_id,
               source_message_id=None,mode='chat',depth='standard',**kwargs):
        request={'message':message,'conversation_id':conversation_id,'source_message_id':source_message_id,
                 'mode':mode,'depth':depth,**kwargs}
        return self.repo.queue_run(owner,request_id,request,depth,subject)

    async def consult(self,**kwargs):
        row=self.submit(**kwargs)
        if row['status']=='succeeded':return row['result']
        run=self.repo.claim_run(kwargs['owner'],row['id'])
        owner=kwargs['owner'];self.executions+=1
        source=self.memory.get_source(owner,run['request']['source_message_id'])
        if source['content']!=run['request']['message']:raise EvidenceError('Original mismatch')
        versions=self.memory.snapshot(owner,run['subject'])['versions']
        self.repo.set_run_dependencies(owner,run['id'],versions,run['lease_token'])
        result={'plain_summary':'Core 已验证的合成结论','answer':self.body,
                'schema_version':'core3.0','validation':{'status':'validated','valid':True,'schema':'core3.0'},
                'meta':{'core_run':{'run_id':run['id'],'dependencies':versions}}}
        return self.repo.commit_run(owner,run['id'],versions,result,run['lease_token'])['result']

    def prepare_delivery(self,**kwargs):return self.outbox.prepare_delivery(**kwargs)
    def claim_delivery(self,**kwargs):return self.outbox.claim_delivery(**kwargs)
    def record_delivery(self,**kwargs):return self.outbox.record_delivery(**kwargs)


class FeishuGatewayPostgresTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.schema='test_feishu_'+uuid.uuid4().hex[:20]
        self.repo=PostgresRepository(test_dsn(),schema=self.schema)
        self.addCleanup(self.cleanup)
        self.repo.ensure_owner('feishu-owner');self.repo.ensure_owner('other-owner')
        self.repo.bind_channel('feishu-owner','feishu','ou_syntheticAuthor')
        self.core=SyntheticCore(self.repo);self.sent=[]
        def transport(target,content,operation):
            self.sent.append((target,content,operation))
            return 'om_syntheticReceipt'
        self.gateway=FeishuGateway(self.core,transport)

    def cleanup(self):
        with self.repo.pool.connection() as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.repo.close()

    async def test_official_typed_event_exact_payload_and_duplicate_once(self):
        from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
        typed=P2ImMessageReceiveV1(event())
        results=await asyncio.gather(self.gateway.handle(typed),self.gateway.handle(typed))
        self.assertEqual([result['status'] for result in results],['sent','sent'])
        self.assertEqual(self.core.executions,1);self.assertEqual(len(self.sent),1)
        target,body,operation=self.sent[0]
        self.assertEqual(target,'ou_syntheticAuthor');self.assertEqual(body,self.core.body)
        self.assertLessEqual(len(operation),50)
        originals=self.repo.list('feishu-owner','message')
        self.assertEqual(len(originals),1)
        self.assertEqual(originals[0]['channel'],'feishu')
        self.assertEqual(originals[0]['external_id'],'ou_syntheticAuthor')
        self.assertEqual(self.repo.list('other-owner','message'),[])
        self.assertEqual((await self.gateway.tick())['failed'],0)
        self.assertEqual(len(self.sent),1)

    async def test_accepted_then_interrupted_poll_recovers_original_queue(self):
        accepted=self.gateway.accept(event())
        self.assertEqual(self.core.executions,0);self.assertEqual(self.sent,[])
        self.assertEqual(self.repo.fetch_run('feishu-owner',accepted['run_id'])['status'],'queued')
        resumed=FeishuGateway(self.core,self.gateway.delivery.transport)
        report=await resumed.tick()
        self.assertEqual(report,{'processed':1,'failed':0})
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
        self.assertEqual(self.repo.fetch_run('feishu-owner',accepted['run_id'])['request']['message'],original)

    async def test_ambiguous_send_is_persistent_and_never_replayed(self):
        def uncertain(target,content,operation):
            self.sent.append((target,content,operation));raise TimeoutError('synthetic timeout')
        self.gateway=FeishuGateway(self.core,uncertain)
        first=await self.gateway.handle(event())
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
