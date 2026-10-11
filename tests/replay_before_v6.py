"""Capture the v5 request with synthetic long history; no model/network calls."""
import asyncio,json,sys,tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'hermes'))
from chat_agent import ChatAgent
class Index:
    def search(self,query,*args):self.query=query;return []
class Capture:
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    async def post(self,url,headers,json):self.request=json;raise RuntimeError('capture complete')
async def replay():
    messages=[{'role':'user','source':'web','turn_id':'seed-constraint','content':'我不能上夜班，晚上的时间要照顾家人。','at':'2026-01-01T09:00:00+08:00'}]
    for i in range(300):
        messages.extend([{'role':'user','source':'web','turn_id':f'u-{i}','content':f'第{i}天聊不同主题：运动、读书和旅游。','at':'2026-02-01T09:00:00+08:00'},
                         {'role':'assistant','source':'web','turn_id':f'a-{i}','content':'可以依据当时实际安排做一个小计划。','at':'2026-02-01T09:01:00+08:00'}])
    with tempfile.TemporaryDirectory() as d:
        arc=Path(d)/'archive.json';arc.write_text('{}');index=Index();client=Capture()
        agent=ChatAgent(object(),index,str(arc),lambda *a:messages,'fixture','https://fixture','fixture','')
        async def emit(e):pass
        with patch('chat_agent.httpx.AsyncClient',return_value=client):
            try:await agent.run({'id':'audit-long','session_id':'shared','message':'上次那件工作安排，后来我试了，接下来怎么选？','selection':'{}','images':'[]'},emit)
            except RuntimeError:pass
        request=client.request
        return {'run_id':'v5-long-replay','synthetic':True,'stored_messages':len(messages),
          'injected_recent_messages':len(request['messages'])-1,'retrieval_query':index.query,
          'known_constraint_in_request':'不能上夜班' in json.dumps(request,ensure_ascii=False),
          'case_state_present':'case_id' in request['system'],
          'claim':'只证明已知关键事实没有进入此离线回放请求，不证明实际模型必然忘记。'}
if __name__=='__main__':
    result=asyncio.run(replay());target=Path('private/v6-before/replay.json');target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
