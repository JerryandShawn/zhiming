"""One real chat message can retain more than one scoped case association."""
import json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import httpx
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'hermes'))
from test_agent_v5 import FakeClient,call

class MultipleCaseChatTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();os.environ['ZHIMING_BASE']=self.temp.name;os.environ['ZHIMING_SKILL']=str(ROOT/'hermes');os.environ['HERMES_DB']='/nonexistent'
        import main
        self.m=main;main.BASE=self.temp.name;main.ARCHIVE=str(Path(self.temp.name)/'archive.json');main.TOKEN='fixture';main.KIMI_KEY='fixture';main.HERMES_DB='/nonexistent'
        main.store=main.ConversationStore(self.temp.name);main.search_index=main.SemanticIndex(self.temp.name)
        self.state,_=main.domain_services(main.BASE);self.owner=main.PRIMARY_OWNER;self.state.ensure_owner(self.owner)
        self.a=self.state.create_case(self.owner,'self','学习安排');self.b=self.state.create_case(self.owner,'self','工作安排')
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://fixture',headers={'X-Token':'fixture'})
    async def asyncTearDown(self):
        await self.client.aclose();self.temp.cleanup()
    async def test_explicit_multi_case_message_and_event_target_survive_restart(self):
        quote='我决定工作安排先暂缓'
        fake=FakeClient([call('record_case_event',{'kind':'decided','quote':quote,'case_id':self.b['id']}),call('final_answer',{'plain_summary':'这两个安排已关联到本次讨论，工作决定已记录。'})])
        with patch('v6_agent.httpx.AsyncClient',return_value=fake),patch.object(self.m.search_index,'search',return_value=[]):
            r=await self.client.post('/api/chat',json={'message':quote+'，也讨论学习安排','case_ids':[self.a['id'],self.b['id']], 'request_id':'multi-case-chat'})
        self.assertIn('result',r.text)
        with self.state.db() as c:row=c.execute("SELECT cases FROM messages WHERE owner=? AND source='web' AND source_id='multi-case-chat:user'",(self.owner,)).fetchone()
        self.assertEqual(json.loads(row[0]),[self.a['id'],self.b['id']])
        self.assertEqual(self.state.get_case(self.owner,self.a['id'])['events'],[])
        self.assertEqual(self.state.get_case(self.owner,self.b['id'])['events'][0]['kind'],'decided')
        self.assertEqual(len(self.state.list_cases(self.owner)),2)
        selection=json.loads(self.m.store.get_turn('multi-case-chat')['selection']);self.assertEqual(selection['case_ids'],[self.a['id'],self.b['id']])
        self.assertIn(self.a['id'],fake.requests[0]['system']);self.assertIn(self.b['id'],fake.requests[0]['system'])
    async def test_natural_multi_case_title_association_and_invalid_ids(self):
        fake=FakeClient([call('final_answer',{'plain_summary':'可以分别核对这两个安排。'})])
        with patch('v6_agent.httpx.AsyncClient',return_value=fake),patch.object(self.m.search_index,'search',return_value=[]):
            r=await self.client.post('/api/chat',json={'message':'同时讨论学习安排和工作安排','request_id':'multi-case-natural'})
        self.assertIn('result',r.text)
        with self.state.db() as c:row=c.execute("SELECT cases FROM messages WHERE source_id='multi-case-natural:user'").fetchone()
        self.assertEqual(set(json.loads(row[0])),{self.a['id'],self.b['id']})
        invalid=await self.client.post('/api/chat',json={'message':'继续','case_ids':'not-a-list'})
        self.assertEqual(invalid.status_code,400)
        missing=await self.client.post('/api/chat',json={'message':'继续','case_ids':['another-owner-case']})
        self.assertEqual(missing.status_code,404)

if __name__=='__main__':unittest.main()
