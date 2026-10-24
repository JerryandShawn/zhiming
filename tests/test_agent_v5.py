import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'hermes'))
from chat_agent import ChatAgent
from test_guidance_v5 import fixtures,DATE

class Index:
    def search(self,*a):return []

class FakeClient:
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

def call(name,args,ident='tool-1'):return [{'type':'tool_use','id':ident,'name':name,'input':args}]

class AgentTests(unittest.IsolatedAsyncioTestCase):
    async def run_agent(self,message,replies,charts):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'archive.json';p.write_text('{}')
            client=FakeClient(replies);events=[]
            async def emit(event):events.append(event)
            agent=ChatAgent(object(),Index(),str(p),lambda *a:[],'fixture','https://fixture','fixture','')
            turn={'message':message,'selection':json.dumps({'date':DATE}),'images':'[]','session_id':'shared','id':'test'}
            with patch('chat_agent.httpx.AsyncClient',return_value=client),patch('chat_agent.bundle',return_value=charts):
                result=await agent.run(turn,emit)
            return result,client.requests,events

    async def test_bad_chart_field_returns_tool_error_then_repairs(self):
        args,refs,calculated=fixtures();bad=copy.deepcopy(args)
        bad['synthesis'][0]['contributions'][0]['evidence'][0]['value']='fake'
        result,requests,events=await self.run_agent('请看三盘', [call('final_answer',bad),call('final_answer',args)],calculated[DATE])
        self.assertEqual(result['meta']['tool_rounds'],2)
        self.assertTrue(requests[1]['messages'][-1]['content'][0]['is_error'])
        self.assertEqual(result['evidence'][0]['data']['value'],'示例bazi')
        self.assertNotIn('position',result['evidence'][0]['data'])

    async def test_context_review_accepts_short_quote_and_releases_chart_contract(self):
        args,refs,calculated=fixtures();args['synthesis']=[];args['professional_appendix']='';args['evidence']=[]
        result,requests,events=await self.run_agent('救命！请帮我看星盘',[
            call('prioritize_urgent_support',{'quote':'救命','reason':'用户表达需要当下安全支持'}),call('final_answer',args)],calculated[DATE])
        self.assertEqual(result['meta']['workflow']['mode'],'urgent_support')
        self.assertEqual(result['meta']['chart_dates'],[]);self.assertEqual(result['meta']['chart_status'],{})
        self.assertFalse(result['synthesis'])

    async def test_user_declines_memory_write(self):
        args,refs,calculated=fixtures();args['synthesis']=[];args['professional_appendix']='';args['evidence']=[]
        result,requests,events=await self.run_agent('我喜欢看书，但不要保存记忆',[
            call('remember_fact',{'quote':'我喜欢看书','category':'偏好'}),call('final_answer',args)],{})
        self.assertTrue(requests[1]['messages'][-1]['content'][0]['is_error'])
        self.assertEqual(result['memory_changes'],[])

if __name__=='__main__':unittest.main(verbosity=2)
