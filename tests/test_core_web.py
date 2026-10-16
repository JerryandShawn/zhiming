"""Production routes over real PostgreSQL and the real LangGraph business service."""
import json
import os
from pathlib import Path
import sys
import unittest
import uuid
from unittest.mock import patch
from psycopg import sql
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).parent))
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.adapters.web import create_app
from test_core_memory import test_dsn
from test_core_pg_channels import FixtureModel


class MemoryModel(FixtureModel):
    def generate(self,**kwargs):
        result=super().generate(**kwargs)
        if kwargs['purpose']=='intake':
            text=kwargs['payload']['reference_data']['message']
            if '喜欢' in text:
                result['output']['proposals']=[{'quote':text,'category':'偏好'}]
        return result


class CoreWeb(unittest.TestCase):
    def setUp(self):
        self.schema='test_web_'+uuid.uuid4().hex[:16]
        self.repo=PostgresRepository(test_dsn(),schema=self.schema,max_size=4)
        self.model=MemoryModel();self.service=ConsultationService(self.repo,model=self.model)
        self.environ=patch.dict(os.environ,{'MINGJING_TOKEN':'synthetic-token','MINGJING_OWNER_ID':'alpha','ZHIMING_TOKEN_OWNERS':'{"synthetic-beta":"beta"}'})
        self.environ.start()
        self.client=TestClient(create_app(self.service));self.client.__enter__()
        self.headers={'X-Token':'synthetic-token'}
    def tearDown(self):
        self.client.__exit__(None,None,None);self.environ.stop()
        with self.repo.pool.connection() as c:c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.repo.close()
    def get(self,path,**kwargs):return self.client.get(path,headers=self.headers,**kwargs)
    def post(self,path,value):return self.client.post(path,json=value,headers=self.headers)

    def test_auth_health_and_no_sqlite_authority(self):
        self.assertEqual(self.client.get('/api/health').status_code,401)
        health=self.get('/api/health').json()
        self.assertEqual((health['context_version'],health['database'],health['runtime']),('core3.0','postgresql','langgraph'))

    def test_chat_memory_sse_replay_and_foreign_operation(self):
        request={'request_id':'memory-e2e','message':'我喜欢安静学习','depth':'fast'}
        first=self.post('/api/chat',request)
        self.assertEqual(first.status_code,200,first.text)
        self.assertIn('"type": "result"',first.text)
        self.assertIn('[DONE]',first.text)
        self.assertEqual(len(self.model.requests),2)
        final=self.get('/api/chat/memory-e2e').json()
        self.assertEqual(final['status'],'complete')
        self.assertEqual(final['meta']['memory_receipts'][0]['write_status'],'saved')
        self.assertEqual(self.get('/api/memories').json()[0]['content'],'我喜欢安静学习')
        again=self.post('/api/chat',request)
        self.assertIn('"type": "result"',again.text)
        self.assertEqual(len(self.model.requests),2)
        conflict=self.post('/api/chat',dict(request,message='另一个问题'))
        self.assertEqual(conflict.status_code,409,conflict.text)
        foreign=self.client.get('/api/chat/memory-e2e',headers={'X-Token':'synthetic-beta'})
        self.assertEqual(foreign.status_code,404)

    def test_refusal_no_fact_and_manual_correction_source_delete(self):
        self.post('/api/chat',{'request_id':'reject','message':'不要存储这条信息。我喜欢晚上慢跑。','depth':'fast'})
        self.assertEqual(self.get('/api/memories').json(),[])
        self.post('/api/chat',{'request_id':'save','message':'我喜欢晨间阅读','depth':'fast'})
        fact=self.get('/api/memories').json()[0]
        response=self.client.patch('/api/memories/'+fact['id'],headers=self.headers,json={'request_id':'correction','text':'我喜欢傍晚阅读','expected_revision':fact['revision']})
        self.assertEqual(response.status_code,200,response.text)
        current=next(f for f in self.get('/api/memories').json() if f['status']=='active')
        response=self.client.delete('/api/memories/'+current['id'],headers=self.headers,params={'scope':'source','expected_revision':current['revision']})
        self.assertEqual(response.status_code,200,response.text)
        self.assertFalse(any(f['status']=='active' for f in self.get('/api/memories').json()))

    def test_cases_tarot_fingerprint_reading_replay(self):
        ca=self.post('/api/cases',{'request_id':'case1','title':'学习安排','goal':'确认时间'}).json()
        payload={'idempotency_key':'draw1','question':'怎样安排学习？','case_id':ca['id'],'spread_id':'reflect3','draw_source':'auto'}
        draw=self.post('/api/tarot/draws',payload).json()['draw']
        self.assertEqual(len(draw['cards']),3)
        for position in range(1,4): self.post('/api/tarot/draws/'+draw['id']+'/reveal',{'position':position,'request_id':'reveal'+str(position)})
        reading={'request_id':'reading1','depth':'fast'}
        response=self.post('/api/tarot/draws/'+draw['id']+'/readings',reading)
        self.assertIn('"type": "result"',response.text,response.text)
        versions=self.get('/api/tarot/draws/'+draw['id']+'/readings').json()
        self.assertEqual(versions[0]['status'],'success')
        count=len(self.model.requests)
        self.post('/api/tarot/draws/'+draw['id']+'/readings',reading)
        self.assertEqual(len(self.model.requests),count)

    def test_explicit_profile_confirmation_and_finite_input(self):
        snap=self.get('/api/state').json()
        profile={'gender':'女','birth':{'solar_datetime':'1998-03-12 08:15','timezone_offset':8,'precision':'exact','location':{'lng':116.4,'lat':39.9}}}
        response=self.post('/api/subjects/self/profile/confirm',{'request_id':'profile','expected_revision':snap['revision'],'confirmed':True,'profile':profile})
        self.assertEqual(response.status_code,200,response.text)
        effective=self.get('/api/subjects/self/profile').json()['effective']
        self.assertEqual(effective['gender'],'女')
        self.assertEqual(effective['birth.timezone_offset'],8)


if __name__=='__main__':unittest.main()
