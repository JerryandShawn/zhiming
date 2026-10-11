"""Actual FastAPI/ChatAgent paths with mocked provider; not an online model eval."""
import asyncio,copy,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import httpx
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'hermes'))
from state_store import StateStore,RevisionConflict
from context_builder import ContextBuilder,ContextOverflow
from domain_context import profile_archive
from test_agent_v5 import FakeClient,call,Index

class VerticalTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();os.environ['ZHIMING_BASE']=self.temp.name;os.environ['ZHIMING_SKILL']=str(ROOT/'hermes');os.environ['HERMES_DB']='/nonexistent'
        import main
        self.m=main;main.BASE=self.temp.name;main.ARCHIVE=str(Path(self.temp.name)/'archive.json');main.TOKEN='fixture-only';main.HERMES_DB='/nonexistent';main.KIMI_KEY='fixture'
        main.store=main.ConversationStore(self.temp.name);main.search_index=main.SemanticIndex(self.temp.name)
        self.state,self.tarot=main.domain_services(main.BASE);self.state.ensure_owner(main.PRIMARY_OWNER)
        self.owner=main.PRIMARY_OWNER
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://fixture',headers={'X-Token':'fixture-only'})
    async def asyncTearDown(self):
        await self.client.aclose();self.temp.cleanup()
    def fact(self,text='我不能上夜班',field=None,value=None):
        row=self.state.import_message(self.owner,'web','original-0001:user','user',text)
        return self.state.put_fact(self.owner,'self',text,[{'message_id':row['id'],'quote':text}],kind='constraint' if not field else 'profile',field=field,value=value,explicit=True)
    async def test_memory_edit_stop_and_source_delete_real_routes(self):
        fact=self.fact();rev=self.state.revision(self.owner)
        r=await self.client.patch('/api/memories/'+fact['id'],json={'text':'我现在只能白天工作','expected_revision':rev,'request_id':'edit0001'})
        self.assertEqual(r.status_code,200,r.text);new=r.json();self.assertEqual(new['write_status'] if 'write_status' in new else new['status'],'active')
        bad=await self.client.patch('/api/memories/'+new['id'],json={'text':'另一更正','expected_revision':rev});self.assertEqual(bad.status_code,409)
        source=await self.client.get('/api/memories/'+new['id']+'/source');self.assertIn('我现在只能白天工作',source.text)
        r=await self.client.delete('/api/memories/'+new['id'],params={'scope':'source','expected_revision':self.state.revision(self.owner)});self.assertEqual(r.status_code,200,r.text)
        self.assertFalse((await self.client.get('/api/memories/'+new['id']+'/source')).json()['source_available'])
        self.assertNotIn('我现在只能白天工作',json.dumps(self.state.snapshot(self.owner),ensure_ascii=False))
    async def test_cases_current_revision_and_events_distinguish_execution(self):
        ca=(await self.client.post('/api/cases',json={'title':'课程选择','goal':'留出休息时间','request_id':'case0001'})).json()
        rev=self.state.revision(self.owner)
        r=await self.client.patch('/api/cases/'+ca['id'],json={'changes':{'title':'周末课程','goal':'先询问费用'},'expected_revision':rev});self.assertEqual(r.status_code,200,r.text)
        r=await self.client.post('/api/cases/'+ca['id']+'/events',json={'kind':'decided','content':'我决定先暂缓报名','request_id':'event0001','expected_revision':self.state.revision(self.owner)});self.assertEqual(r.status_code,200,r.text)
        events=self.state.get_case(self.owner,ca['id'])['events'];self.assertEqual([e['kind'] for e in events],['decided'])
    async def draw(self,source='auto'):
        r=await self.client.post('/api/tarot/draws',json={'question':'我怎样安排周末时间？','draw_source':source,'idempotency_key':'drawing0001'})
        self.assertEqual(r.status_code,200,r.text);return r.json()['draw']
    async def test_draw_reload_idempotency_privacy_and_unconfigured_model(self):
        draw=await self.draw();replay=await self.draw();self.assertEqual(draw['id'],replay['id']);self.assertNotIn('card_id',draw['cards'][0])
        r=await self.client.post('/api/tarot/draws/'+draw['id']+'/reveal',json={});self.assertEqual(r.status_code,200,r.text)
        self.m.KIMI_KEY=''
        previous_model=self.m.KIMI_MODEL;self.m.KIMI_MODEL='';self.addCleanup(setattr,self.m,'KIMI_MODEL',previous_model)
        r=await self.client.post('/api/tarot/draws/'+draw['id']+'/readings',json={'request_id':'reading0001'});self.assertIn('AI 解读未配置',r.text)
        versions=(await self.client.get('/api/tarot/draws/'+draw['id']+'/readings')).json();self.assertEqual(versions[0]['status'],'failed');self.assertEqual(versions[0]['request_id'],'reading0001')
        self.assertEqual((await self.client.get('/api/tarot/draws/'+draw['id'])).json()['cards'],r.json() if False else self.tarot.get(self.owner,draw['id'])['cards'])
        deleted=await self.client.delete('/api/tarot/draws/'+draw['id']);self.assertEqual(deleted.status_code,200,deleted.text)
        self.assertEqual((await self.client.get('/api/tarot/draws/'+draw['id'])).status_code,404)
        self.assertEqual((await self.client.post('/api/tarot/draws',json={'question':draw['question'],'idempotency_key':'drawing0001'})).status_code,400)
    async def test_two_account_and_two_subject_isolation(self):
        draw=await self.draw();self.state.ensure_owner('second')
        with patch.dict(os.environ,{'ZHIMING_TOKEN_OWNERS':json.dumps({'second-fixture':'second'})}):
            r=await self.client.get('/api/tarot/draws/'+draw['id'],headers={'X-Token':'second-fixture'});self.assertEqual(r.status_code,404)
            r=await self.client.get('/api/history',headers={'X-Token':'second-fixture'});self.assertEqual(r.json(),[])
            self.assertEqual((await self.client.get('/api/archive',headers={'X-Token':'second-fixture'})).status_code,403)
        self.state.create_subject(self.owner,'friend','朋友')
        self.m.store.begin('friend0001','shared','第三人的敏感秘密',[],{'subject_id':'friend'});self.m.store.finish('friend0001','解释','complete',{})
        self.assertNotIn('第三人的敏感秘密',json.dumps(self.m.owner_catalog(self.owner),ensure_ascii=False))
    async def test_chat_actual_context_and_failed_fact_candidate(self):
        fact=self.fact();fake=FakeClient([call('remember_fact',{'quote':'我有三栋房子','category':'背景'}),call('final_answer',{'plain_summary':'你之前提过不能上夜班，可以先比较白天的安排。','evidence':[{'ref':'fact:'+fact['id'],'claim':'工作约束来自已登记原话'}]})])
        with patch('v6_agent.httpx.AsyncClient',return_value=fake),patch.object(self.m.search_index,'search',return_value=[]):
            r=await self.client.post('/api/chat',json={'message':'之前的工作安排还记得吗？','request_id':'v6chat0001'})
        self.assertIn('不能上夜班',fake.requests[0]['system']);self.assertIn('不能上夜班',r.text)
        self.assertTrue(fake.requests[1]['messages'][-1]['content'][0]['is_error']);self.assertEqual(len(self.state.list_facts(self.owner)),1)
        result=self.m.store.get_turn('v6chat0001');self.assertEqual(result['status'],'complete')
    async def test_tarot_wrong_card_blocked_then_repair_same_draw(self):
        draw=await self.draw();draw=self.tarot.reveal(self.owner,draw['id'])
        good={'plain_summary':'可以先留出一小段休息时间，再核对其他安排。','reality_context':[],'card_interpretations':[{'position':c['position'],'card_id':c['card_id'],'orientation':c['orientation'],'theme':'这张牌的象征主题','interpretation':'可以作为核对安排的一个问题。','question':'这一步是否可行？'} for c in draw['cards']],'tarot_synthesis':['主题可能侧重不同，不能当成现实已发生。']}
        bad=copy.deepcopy(good);bad['card_interpretations'][0]['card_id']='fake-card'
        fake=FakeClient([call('final_answer',bad),call('final_answer',good)])
        with patch('v6_agent.httpx.AsyncClient',return_value=fake),patch.object(self.m.search_index,'search',return_value=[]):
            r=await self.client.post('/api/tarot/draws/'+draw['id']+'/readings',json={'request_id':'reading-good-0001'})
        self.assertIn('result',r.text);self.assertTrue(fake.requests[1]['messages'][-1]['content'][0]['is_error'])
        self.assertEqual(self.tarot.get(self.owner,draw['id'])['cards'],draw['cards']);self.assertEqual(self.tarot.list_readings(self.owner,draw['id'])[0]['status'],'success')
    async def test_deletion_purges_tarot_derived_snapshots(self):
        fact=self.fact();draw=await self.draw();self.assertIn(fact['id'],draw['context_snapshot']['fact_ids'])
        r=await self.client.delete('/api/memories/'+fact['id'],params={'expected_revision':self.state.revision(self.owner),'scope':'fact'});self.assertEqual(r.status_code,200,r.text)
        restored=self.tarot.get(self.owner,draw['id']);self.assertTrue(restored['context_revoked']);self.assertNotIn(fact['id'],str(restored['context_snapshot']))
    async def test_natural_stop_refreshes_context_and_confirms_actual_receipt(self):
        fact=self.fact();fake=FakeClient([call('retire_memory',{'fact_id':fact['id'],'operation':'stop','quote':'以后别再用这个前提'}),call('final_answer',{'plain_summary':'这条前提已停止使用。'})])
        with patch('v6_agent.httpx.AsyncClient',return_value=fake),patch.object(self.m.search_index,'search',return_value=[]):
            r=await self.client.post('/api/chat',json={'message':'以后别再用这个前提','request_id':'stopchat0001'})
        self.assertIn('result',r.text);self.assertEqual(self.state.get_fact(self.owner,fact['id'])['status'],'stopped')
        self.assertNotIn('我不能上夜班',fake.requests[1]['system']);self.assertNotIn('我不能上夜班',str(fake.requests[1]['messages']))
    async def test_fact_delete_can_later_upgrade_to_source_delete(self):
        fact=self.fact();row=fact['source_refs'][0]['message_id']
        self.state.delete_fact(self.owner,fact['id'],self.state.revision(self.owner),'fact')
        self.assertTrue(self.state.get_message(self.owner,row,include_suppressed=True)['content'])
        r=await self.client.delete('/api/memories/'+fact['id'],params={'scope':'source','expected_revision':self.state.revision(self.owner)})
        self.assertEqual(r.status_code,200,r.text);self.assertFalse(self.state.get_message(self.owner,row,include_suppressed=True)['content'])

class LongContextTests(unittest.TestCase):
    def test_300_mixed_rounds_restart_constraints_and_unknowns(self):
        from conversation_store import ConversationStore
        from domain_context import register_history
        with tempfile.TemporaryDirectory() as d:
            state=StateStore(d);state.ensure_owner('owner');store=ConversationStore(d)
            first='我不能上夜班，晚上要照顾家人。'
            row=state.import_message('owner','web','long-first:user','user',first)
            fact=state.put_fact('owner','self',first,[{'message_id':row['id'],'quote':first}],kind='constraint')
            for i in range(300):
                msg=['学习计划','周末散步','课程费用','与朋友聊天'][i%4]+str(i)
                turn,_=store.begin('long-turn-'+str(i),'shared',msg,[],{});store.finish(turn['id'],'这是旧助手解释，不代表事情发生了。','complete',{})
            register_history(state,'owner','self',store.history(limit=10000))
            state=StateStore(d);pinned,messages,refs,meta=ContextBuilder(state,Index()).build('owner','self','上次工作安排，接下来怎么选？',store.history(limit=10000))
            self.assertIn(first,json.dumps(pinned,ensure_ascii=False));self.assertIn(fact['id'],meta['injected_ids']);self.assertLessEqual(len(messages),50)
            self.assertEqual(len(state.list_facts('owner')),1)
            unknown=ContextBuilder(state,Index()).build('owner','self','我账户里有多少钱？',store.history(limit=10000))[0]
            self.assertNotIn('账户余额',json.dumps(unknown,ensure_ascii=False))
            with self.assertRaises(ContextOverflow):ContextBuilder(state,Index(),limit=100).build('owner','self','问候',[])
    def test_corrected_birth_uses_canonical_fields_and_delete_blocks_legacy(self):
        with tempfile.TemporaryDirectory() as d:
            s=StateStore(d);s.ensure_owner('o');text='请记住出生时间 1991-04-02 08:30'
            row=s.import_message('o','web','birth','user',text);f=s.put_fact('o','self',text,[{'message_id':row['id'],'quote':text}],kind='profile',field='birth.solar_datetime',value='1991-04-02 08:30',explicit=True)
            legacy={'user':{'birth':{'solar_datetime':'1990-01-01 01:00'}}};self.assertEqual(profile_archive(s,'o',legacy=legacy)['user']['birth']['solar_datetime'],'1991-04-02 08:30')
            s.delete_fact('o',f['id'],s.revision('o'));self.assertFalse(profile_archive(s,'o',legacy=legacy)['user'].get('birth',{}).get('solar_datetime'))

if __name__=='__main__':unittest.main(verbosity=2)
