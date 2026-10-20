"""Independent review regressions: assertions express the required behavior.

These use synthetic identities/data and never contact the configured model.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import importlib.util
import copy
from unittest.mock import patch
import httpx

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'hermes'))
from domain_context import profile_archive
from context_builder import ContextBuilder
from state_store import StateStore
from chat_agent import ChatAgent

class _Index:
    def __init__(self,docs=()):self.docs=list(docs)
    def search(self,*args):return self.docs

class _Client:
    _zhiming_offline_transport=True
    def __init__(self,replies):self.replies=iter(replies);self.requests=[]
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    async def post(self,url,headers,json):
        self.requests.append(copy.deepcopy(json));content=next(self.replies)
        class Response:
            status_code=200
            def json(self):return {'content':content}
        return Response()

def _call(name,args):return [{'type':'tool_use','id':'review-tool','name':name,'input':args}]

class IndependentStateReviewTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.state=StateStore(self.tmp.name);self.owner='review-owner';self.state.ensure_owner(self.owner)

    def test_expired_memory_cannot_reenter_through_stale_index(self):
        text='EXPIRED_TEMPORARY_CONSTRAINT_526'
        row=self.state.import_message(self.owner,'review','expired','user',text,at='2020-01-01T08:00:00+08:00')
        fact=self.state.put_fact(self.owner,'self',text,[{'message_id':row['id'],'quote':text}],
                                 valid_from='2020-01-01T08:00:00+08:00',valid_to='2020-01-02T08:00:00+08:00')
        doc={'id':'memory:'+fact['id'],'source':'memory','record_id':fact['id'],'data':fact,'text':text,
             'owner_user_id':self.owner,'subject_id':'self'}
        self.assertEqual(self.state.snapshot(self.owner)['facts'],[])
        pinned,_,_,_=ContextBuilder(self.state,_Index([doc])).build(self.owner,'self','目前有什么约束？',[])
        self.assertNotIn(text,json.dumps(pinned,ensure_ascii=False))

    def test_canonical_birth_datetime_updates_chart_input(self):
        text='请记住更正：出生时间为2012-05-03 14:20'
        row=self.state.import_message(self.owner,'review','birth','user',text)
        self.state.put_fact(self.owner,'self',text,[{'message_id':row['id'],'quote':text}],kind='profile',
                            field='birth.solar_datetime',value='2012-05-03 14:20',explicit=True)
        actual=profile_archive(self.state,self.owner,'self',{'user':{'birth':{'solar_datetime':'2012-05-03 13:18'}}})
        self.assertEqual(actual['user']['birth']['solar_datetime'],'2012-05-03 14:20')

    def test_deleted_fact_does_not_reenter_via_same_turn_assistant(self):
        text='PRIVATE_REVOKED_BACKGROUND_927'
        row=self.state.import_message(self.owner,'web','old-turn:user','user',text)
        fact=self.state.put_fact(self.owner,'self',text,[{'message_id':row['id'],'quote':text}])
        self.state.delete_fact(self.owner,fact['id'],self.state.revision(self.owner))
        history=[{'source':'web','turn_id':'old-turn','role':'user','content':text,'status':'complete'},
                 {'source':'web','turn_id':'old-turn','role':'assistant','content':'此前你提到 '+text,'status':'complete'}]
        pinned,messages,_,_=ContextBuilder(self.state,_Index()).build(self.owner,'self','继续聊聊',history)
        self.assertNotIn(text,json.dumps([pinned,messages],ensure_ascii=False))

    def agent(self,message,key='fixture',cases=None):
        archive=Path(self.tmp.name)/'archive.json';archive.write_text('{}')
        agent=ChatAgent(object(),_Index(),str(archive),lambda *a:[],key,'https://fixture','fixture','')
        agent.state_store=self.state;agent.owner_id=self.owner;agent.subject_id='self';agent.case_ids=cases;agent.legacy_owner=False
        turn={'id':'review-turn-1','message':message,'selection':'{}','images':'[]','session_id':'shared'}
        return agent,turn

    async def test_negated_choice_does_not_become_decided_event(self):
        case=self.state.create_case(self.owner,'self','学习安排')['id']
        agent,turn=self.agent('我选择不了，先等等。',key='',cases=[case])
        async def emit(event):pass
        with self.assertRaisesRegex(RuntimeError,'未配置'):await agent.run(turn,emit)
        self.assertFalse(any(e['kind']=='decided' for e in self.state.get_case(self.owner,case)['events']))

    async def test_no_write_receipt_rejects_short_saved_claim(self):
        agent,turn=self.agent('请记住我每天七点起床。')
        client=_Client([_call('final_answer',{'plain_summary':'好的，我已经记住了，以后会参考。'}),
                        _call('final_answer',{'plain_summary':'本轮还没有保存这条资料。'})])
        async def emit(event):pass
        with patch('v6_agent.httpx.AsyncClient',return_value=client):result=await agent.run(turn,emit)
        self.assertEqual(result['meta']['tool_rounds'],2)
        self.assertEqual(result['memory_changes'],[])

@unittest.skipUnless(importlib.util.find_spec('starlette') and importlib.util.find_spec('fastapi'),'API dependencies unavailable in this interpreter')
class IndependentReviewTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env=patch.dict(os.environ,{'ZHIMING_BASE':self.tmp.name,'ZHIMING_SKILL':str(ROOT/'hermes'),
                                       'HERMES_DB':'/nonexistent','MINGJING_TOKEN':'review-local-token','ZHIMING_TOKEN_OWNERS':'{}'})
        self.env.start()
        self.addCleanup(self.env.stop)
        import main
        self.m=main;self.original={k:getattr(main,k) for k in ('BASE','ARCHIVE','TOKEN','HERMES_DB','store','search_index')}
        main.BASE=self.tmp.name;main.ARCHIVE=str(Path(self.tmp.name)/'archive.json');main.TOKEN='review-local-token';main.HERMES_DB='/nonexistent'
        main.store=main.ConversationStore(self.tmp.name);main.search_index=main.SemanticIndex(self.tmp.name)
        self.state,self.tarot=main.domain_services(main.BASE);self.owner=main.PRIMARY_OWNER
        self.state.ensure_owner(self.owner);self.state.create_subject(self.owner,'other','另一人物')
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://fixture',headers={'X-Token':'review-local-token'})

    async def asyncTearDown(self):
        await self.client.aclose()
        for key,value in self.original.items():setattr(self.m,key,value)
        self.env.stop();self.tmp.cleanup()

    def fact(self,content,field=None,value=None):
        row=self.state.import_message(self.owner,'review','fact-source','user',content)
        return self.state.put_fact(self.owner,'self',content,[{'message_id':row['id'],'quote':content}],
                                   kind='profile' if field else 'preference',field=field,value=value,explicit=True)

    async def test_fresh_memory_edit_does_not_conflict_with_its_own_source_write(self):
        fact=self.fact('我喜欢上午学习。')
        revision=self.state.revision(self.owner)
        response=await self.client.patch('/api/memories/'+fact['id'],json={
            'text':'我现在更喜欢下午学习。','request_id':'review-edit','expected_revision':revision})
        self.assertEqual(response.status_code,200,response.text)

    async def test_history_index_keeps_subject_scope(self):
        self.m.store.begin('review-other-person','shared','OTHER_PERSON_PRIVATE_923',[],{'subject_id':'other'})
        self.m.store.finish('review-other-person','已收到','complete',{})
        docs=self.m.owner_catalog(self.owner)
        class Index:
            def search(self,*args):return docs
        pinned,_,_,_=ContextBuilder(self.state,Index()).build(self.owner,'self','聊聊我自己的情况',[])
        self.assertNotIn('OTHER_PERSON_PRIVATE_923',json.dumps(pinned,ensure_ascii=False))

    async def test_replayed_draw_key_rejects_different_client_options(self):
        body={'question':'我要怎样安排学习？','spread_id':'reflect3','idempotency_key':'review-draw-key'}
        first=await self.client.post('/api/tarot/draws',json=body)
        self.assertEqual(first.status_code,200,first.text)
        second=await self.client.post('/api/tarot/draws',json={**body,'spread_id':'choice5','options':{'A':'尝试','B':'暂缓'}})
        self.assertIn(second.status_code,(400,409),'同一键接受了不同牌阵：'+second.text)

    async def test_deleting_tarot_removes_linked_synthetic_timeline_copies(self):
        question='PRIVATE_TAROT_QUESTION_651'
        created=await self.client.post('/api/tarot/draws',json={'question':question,'idempotency_key':'review-private-draw'})
        self.assertEqual(created.status_code,200,created.text)
        draw=created.json()['draw'];self.tarot.reveal(self.owner,draw['id'])
        reading=self.tarot.begin_reading(self.owner,draw['id'],model='offline',prompt_version='test',context_snapshot={},idempotency_key='review-private-reading')['reading']
        ident='tarot-reading-'+reading['id']
        # Mirrors domain_api.reading.execute's durable main-timeline entry.
        self.m.store.begin(ident,'shared','请解读这次已冻结的塔罗牌阵。问题：'+question,[],{})
        self.m.store.finish(ident,'PRIVATE_INTERPRETATION_651','complete',{'meta':{'draw_id':draw['id']}})
        response=await self.client.delete('/api/tarot/draws/'+draw['id'])
        self.assertEqual(response.status_code,200,response.text)
        remaining=json.dumps(self.m.all_history(self.owner),ensure_ascii=False)
        self.assertNotIn(question,remaining)
        self.assertNotIn('PRIVATE_INTERPRETATION_651',remaining)

if __name__=='__main__':unittest.main()
