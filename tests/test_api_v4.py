import asyncio,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import httpx
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'hermes'))

class APITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();os.environ['ZHIMING_BASE']=self.temp.name;os.environ['ZHIMING_SKILL']=str(ROOT/'hermes');os.environ['HERMES_DB']='/nonexistent';os.environ['MINGJING_TOKEN']='fixture-only'
        import main
        self.app=main
        main.BASE=self.temp.name;main.ARCHIVE=str(Path(self.temp.name)/'archive.json');main.TOKEN='fixture-only';main.HERMES_DB='/nonexistent'
        main.store=main.ConversationStore(self.temp.name);main.search_index=main.SemanticIndex(self.temp.name)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://fixture',headers={'X-Token':'fixture-only'})

    async def asyncTearDown(self):
        await self.client.aclose();self.temp.cleanup()

    async def test_cancel_persists_and_requires_auth(self):
        event=asyncio.Event()
        class SlowAgent:
            def __init__(self,*a):pass
            async def run(self,turn,emit):event.set();await asyncio.Event().wait()
        with patch.object(self.app,'ChatAgent',SlowAgent):
            task=asyncio.create_task(self.client.post('/api/chat',json={'message':'测试停止','request_id':'cancel-test-001'}))
            await asyncio.wait_for(event.wait(),2)
            denied=await self.client.post('/api/chat/cancel-test-001/cancel',headers={'X-Token':'invalid'})
            self.assertEqual(denied.status_code,401)
            self.assertEqual((await self.client.post('/api/chat/cancel-test-001/cancel')).status_code,200)
            response=await asyncio.wait_for(task,2);self.assertIn('已停止',response.text)
            row=(await self.client.get('/api/chat/cancel-test-001')).json();self.assertEqual(row['status'],'cancelled')
            self.assertEqual(self.app.store.get_turn('cancel-test-001')['message'],'测试停止')

    async def test_complete_request_replay_is_idempotent(self):
        self.app.store.begin('replay-test-001','shared','完整问题',[],{})
        self.app.store.finish('replay-test-001','已经完成的回答','complete',{'answer':'已经完成的回答','evidence':[]})
        r=await self.client.post('/api/chat',json={'message':'完整问题','request_id':'replay-test-001'})
        self.assertIn('已经完成的回答',r.text);self.assertEqual(len(self.app.store.history()),2)
        denied=await self.client.get('/api/history?token=fixture-only',headers={'X-Token':''});self.assertEqual(denied.status_code,401)

    async def test_pagination_keeps_messages_with_identical_timestamps(self):
        for i in range(3):
            ident='pagination-000'+str(i);self.app.store.begin(ident,'shared','问题'+str(i),[],{});self.app.store.finish(ident,'回答'+str(i),'complete',{})
        seen=[];before=''
        for _ in range(6):
            rows=(await self.client.get('/api/history',params={'limit':1,'before':before})).json()
            self.assertEqual(len(rows),1);seen.append((rows[0]['turn_id'],rows[0]['role']));before=rows[0]['cursor']
        self.assertEqual(len(set(seen)),6)

if __name__=='__main__':unittest.main(verbosity=2)
