"""Channel regressions through the real service, runtime, sources and PG."""
import asyncio
from contextlib import closing
from datetime import datetime,timezone,timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import unittest
import uuid
from psycopg import sql
from psycopg.types.json import Jsonb

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.adapters.channels.hermes import HermesChannelAdapter,render_channel,validated_payload
from mingjing_core.adapters.channels.reports import CoreReportAdapter
from mingjing_core.adapters.core_report_worker import CoreReportWorker
from mingjing_core.domain.contracts import ScopeError,EvidenceError,RevisionConflict


class FixtureModel:
    """Only the provider response is synthetic; the service is unmodified."""
    def __init__(self):self.requests=[]
    def generate(self,*,system,payload,schema,purpose):
        self.requests.append({'purpose':purpose,'payload':payload})
        data=payload.get('reference_data',{})
        if purpose=='intake':
            mode='report' if data.get('requested_mode')=='scheduled_report' else 'tarot' if '塔罗' in data.get('message','') else 'conversation'
            matched=re.search(r'20\d\d-\d\d-\d\d',data.get('message',''))
            output={'plan':{'mode':mode,'topic':'study','systems':['tarot'] if mode=='tarot' else [],'target_date':matched.group(0) if matched else data['today'],'time_scale':'daily','decision':False,'rationale':'本地合成','missing_inputs':[]},'proposals':[],'retire_fact_ids':[]}
        elif purpose.startswith('specialist:'):
            output={'system':purpose.split(':')[1],'claim_ids':[c['claim_id'] for c in data['claims']],'discussion':'象征仅提供反思角度。','uncertainties':[]}
        else:
            facts=data.get('facts',[]);claims=data.get('claims',[])
            output={'plain_summary':'先核对现实安排，再做一个小行动。','explanation':'现有信息仅用于这次讨论。','actions':['先确认可用时间。'],'follow_up':'执行后核对实际反馈。','professional_appendix':'象征仅作条件性反思，不是事件概率。' if claims else '',
                    'cited_fact_ids':[f['id'] for f in facts],'cited_claim_ids':[c['claim_id'] for c in claims],'decision_options':[],'caveats':[]}
        return {'output':output,'usage':{},'model':'local-fixture-only'}


class CorePGChannels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn=os.environ.get('CORE_TEST_DSN')
        if not cls.dsn:
            settings=ROOT.parent/'dev-environment.json'
            if settings.is_file():cls.dsn=json.loads(settings.read_text())['dsn']
        if not cls.dsn:raise unittest.SkipTest('requires disposable PostgreSQL')

    def setUp(self):
        self.schema='test_channel_'+uuid.uuid4().hex[:16]
        self.repo=PostgresRepository(self.dsn,schema=self.schema)
        for owner,target in [('alice','ou_alice'),('bob','ou_bob')]:
            self.repo.ensure_owner(owner);self.repo.bind_channel(owner,'feishu',target)
        self.repo.bind_channel('alice','report','daily-alice',binding_kind='task')
        self.model=FixtureModel();self.service=ConsultationService(self.repo,model=self.model)
        self.temporary=tempfile.TemporaryDirectory();self.raw=Path(self.temporary.name)/'originals.db'
        with closing(sqlite3.connect(self.raw)) as c,c:
            c.executescript('CREATE TABLE sessions(id TEXT,source TEXT,user_id TEXT,chat_id TEXT,chat_type TEXT);CREATE TABLE messages(id TEXT,session_id TEXT,role TEXT,content TEXT,timestamp REAL,active INTEGER);')
            c.executemany('INSERT INTO sessions VALUES(?,?,?,?,?)',[('s-alice','feishu','ou_alice','oc_alice','dm'),('s-bob','feishu','ou_bob','oc_bob','dm'),('s-group','feishu','ou_alice','oc_group','group')])
            c.executemany('INSERT INTO messages VALUES(?,?,?,?,?,?)',[('alice-old','s-alice','user','原来的学习安排。',1791660000,1),('alice-now','s-alice','user','今天先核对学习时间。',1791660001,1),('alice-assistant','s-alice','assistant','未经确认的助手预测。',1791660002,1),('inactive','s-alice','user','已撤回内容。',1791660003,0),('bob-now','s-bob','user','Bob 的秘密。',1791660004,1),('group-now','s-group','user','群聊内容。',1791660005,1)])
        self.hermes=HermesChannelAdapter('.',service=self.service,hermes_db=self.raw)
        self.reports=CoreReportAdapter('.',service=self.service)

    def tearDown(self):
        assert self.schema.startswith('test_channel_')
        with self.repo.transaction() as c:c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.repo.close();self.temporary.cleanup()

    def test_verified_originals_only_and_no_hermes_database_mutation(self):
        before=hashlib.sha256(self.raw.read_bytes()).hexdigest()
        with self.assertRaises(ScopeError):self.hermes.identity('feishu','unknown')
        for message in ('bob-now','group-now','inactive','alice-assistant','missing'):
            with self.assertRaises(EvidenceError):asyncio.run(self.hermes.consult(channel='feishu',external_id='ou_alice',message_id=message))
        self.assertEqual(self.hermes.sync('feishu','ou_alice'),{'imported':2,'skipped':0})
        self.hermes.sync('feishu','ou_alice')
        self.assertEqual(len(self.repo.list('alice','message')),2)
        self.assertEqual(hashlib.sha256(self.raw.read_bytes()).hexdigest(),before)

    def test_real_core_channel_result_has_exact_origin_and_no_second_model(self):
        result=asyncio.run(self.hermes.consult(channel='feishu',external_id='ou_alice',message_id='alice-now',depth='fast'))
        self.assertEqual(render_channel(result),result['answer'])
        self.assertEqual([r['purpose'] for r in self.model.requests],['intake','synthesis'])
        run=self.repo.fetch_run('alice',result['meta']['core_run']['run_id'])
        source=self.service.memory.get_source('alice',run['request']['source_message_id'])
        self.assertEqual(source['channel'],'feishu');self.assertEqual(source['source_id'],'alice-now:user')
        self.assertEqual(len(self.repo.list('alice','message')),2)
        replay=asyncio.run(self.hermes.consult(channel='feishu',external_id='ou_alice',message_id='alice-now',depth='fast'))
        self.assertEqual(replay,result);self.assertEqual(len(self.model.requests),2)

    def test_shared_saved_fact_read_by_report_and_subject_isolation(self):
        source=self.service.memory.receive('alice',content='请记住，我不能上夜班。',source_id='original-constraint')
        receipt=self.service.memory.apply_proposal('alice',source['id'],{'quote':'我不能上夜班','category':'约束'},operation_id='save-constraint')
        self.assertEqual(receipt['write_status'],'saved')
        result=asyncio.run(self.reports.prepare(external_id='daily-alice',kind='daily',day='2026-10-11',depth='fast'))
        self.assertIn('不能上夜班',json.dumps(self.model.requests[-1]['payload'],ensure_ascii=False))
        manifest=self.repo.get('alice','report',result['report']['business_id'])
        self.assertEqual(manifest['run_id'],result['meta']['core_run']['run_id'])
        self.assertEqual(manifest['content'],result['answer'])
        self.assertEqual(manifest['deliver_at'][-6:],'+08:00')
        self.assertEqual(self.repo.list('bob','report'),[])

    def test_tarot_same_real_service_uses_saved_draw_and_rule_claims(self):
        case=self.service.memory.create_case('alice','self','学习安排',operation_id='case-1')
        draw=self.service.tarot.create_draw('alice',subject_id='self',case_id=case['id'],question='如何安排学习？',idempotency_key='tarot-core-1')['draw']
        draw=self.service.tarot.reveal('alice',draw['id'])
        result=asyncio.run(self.service.consult(owner='alice',message='请解释这次塔罗的反思角度。',request_id='tarot-core-reading',draw_id=draw['id'],depth='fast'))
        self.assertEqual(result['meta']['draw_id'],draw['id'])
        self.assertTrue(result['cited_claim_ids'])
        self.assertEqual(self.service.tarot.get('alice',draw['id'])['cards'],draw['cards'])
        self.assertEqual(result['meta']['core_run']['calls'],2)

    def test_reading_resume_keeps_version_and_only_accepts_its_persisted_result(self):
        case=self.service.memory.create_case('alice','self','合成恢复事项',operation_id='case-recover')
        draw=self.service.tarot.create_draw('alice',subject_id='self',case_id=case['id'],question='怎样核对学习安排？',idempotency_key='reading-recovery-draw')['draw']
        draw=self.service.tarot.reveal('alice',draw['id'])
        reading=self.service.tarot.begin_reading('alice',draw['id'],model='local-fixture-only',prompt_version='core3.0',context_snapshot={},idempotency_key='same-reading')['reading']
        self.service.tarot.finish_reading('alice',reading['id'],error='local synthetic interruption')
        run=self.service.submit(owner='alice',message='请核对这次塔罗。',request_id='reading:same-reading',draw_id=draw['id'],reading_id=reading['id'],depth='fast')
        resumed=self.service.tarot.resume_reading('alice',reading['id'],run['id']);self.assertEqual(resumed['version'],1)
        result=self.service.execute('alice',run['id'])
        forged=dict(result,answer='没有通过Core保存的二次解释')
        with self.assertRaises(ValueError):self.service.tarot.finish_reading('alice',reading['id'],result=forged,validation=result['validation'])
        completed=self.service.tarot.finish_reading('alice',reading['id'],result=result,validation=result['validation'])
        self.assertEqual(completed['status'],'success');self.assertEqual(completed['version'],1)
        self.assertEqual(completed['execution_snapshot']['run_id'],run['id'])
        self.assertEqual(len(self.service.tarot.list_readings('alice',draw['id'])),1)

    def test_unvalidated_payload_or_forged_report_manifest_rejected(self):
        with self.assertRaises(EvidenceError):validated_payload({'answer':'自由模型正文'})
        result=asyncio.run(self.reports.prepare(external_id='daily-alice',kind='daily',day='2026-10-11',depth='fast'))
        result['report']['business_id']='invented-report'
        with self.assertRaises(ScopeError):asyncio.run(self.reports.prepare_delivery(external_id='daily-alice',result=result,channel='feishu',target='ou_alice'))

    def configure_worker(self):
        with self.repo.transaction('alice') as conn:
            conn.execute(sql.SQL('UPDATE {} SET settings=%s WHERE id=%s').format(self.repo.table('core_owners')),(Jsonb({'report_pipeline':{'enabled':True,'jobs':[{'id':'daily-alice','kind':'daily','target':'ou_alice','channel':'feishu'}]}}),'alice'))

    def test_worker_original_schedule_and_persisted_authority(self):
        self.configure_worker();calls=[]
        worker=CoreReportWorker(self.service,lambda target,text,ident:calls.append((target,text,ident)) or 'local-receipt-1')
        at=datetime(2026,10,11,6,44,tzinfo=timezone(timedelta(hours=8)))
        self.assertEqual(asyncio.run(worker.tick('alice',at))['prepared'],0)
        self.assertEqual(self.model.requests,[])
        prepared=asyncio.run(worker.tick('alice',at+timedelta(minutes=1)))
        self.assertEqual(prepared['prepared'],1);self.assertEqual(calls,[])
        count=len(self.model.requests)
        self.assertEqual(asyncio.run(worker.tick('alice',at+timedelta(minutes=16)))['sent'],1)
        manifest=self.repo.list('alice','report')[0]
        self.assertEqual(calls[0][1],manifest['content']);self.assertEqual(calls[0][0],'ou_alice')
        self.assertLessEqual(len(calls[0][2]),50)
        asyncio.run(worker.tick('alice',at+timedelta(minutes=17)))
        self.assertEqual(len(calls),1);self.assertEqual(len(self.model.requests),count)

    def test_worker_unknown_delivery_waits_for_receipt(self):
        self.configure_worker();calls=[]
        def timeout(target,text,ident):calls.append(ident);raise TimeoutError('local synthetic timeout')
        worker=CoreReportWorker(self.service,timeout)
        at=datetime(2026,10,11,7,tzinfo=timezone(timedelta(hours=8)))
        asyncio.run(worker.tick('alice',at));count=len(self.model.requests)
        row=self.service.outbox.status('alice')['rows'][0];self.assertEqual(row['status'],'uncertain')
        asyncio.run(worker.tick('alice',at+timedelta(minutes=10)))
        self.assertEqual(len(calls),1);self.assertEqual(len(self.model.requests),count)
        self.service.reconcile_delivery(owner='alice',outbox_id=row['id'],delivered=True,message_id='verified-local-receipt',evidence_ref='synthetic receipt record')
        asyncio.run(worker.tick('alice',at+timedelta(minutes=20)))
        self.assertEqual(len(calls),1)

    def legacy_delivery(self,status,due,*,attempts=0,proof=None,business=None):
        ident=uuid.uuid4().hex
        business=business or 'report:daily-alice:daily:2026-10-11'
        with self.repo.transaction('alice') as conn:
            conn.execute(sql.SQL('INSERT INTO {}(id,owner,subject,business_id,channel,target,run_id,payload,dependencies,status,attempts,due,reconciliation) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)').format(self.repo.table('delivery_outbox')),
                         (ident,'alice','self',business,'feishu','ou_alice','legacy:'+ident,Jsonb({}),Jsonb({}),status,attempts,due,Jsonb(proof or {'verification':'legacy_'+status})))
        return ident

    def test_legacy_sent_guard_is_not_truncated_by_the_status_page(self):
        self.configure_worker();calls=[]
        at=datetime(2026,10,11,7,tzinfo=timezone(timedelta(hours=8)))
        ident=self.legacy_delivery('sent',at)
        for index in range(121):self.legacy_delivery('sent',at+timedelta(days=1,minutes=index),business='later-report:'+str(index))
        self.assertNotIn(ident,[row['id'] for row in self.service.outbox.status('alice')['rows']])
        worker=CoreReportWorker(self.service,lambda *args:calls.append(args) or 'synthetic-message')
        self.assertEqual(asyncio.run(worker.tick('alice',at))['prepared'],0)
        self.assertEqual(self.model.requests,[]);self.assertEqual(calls,[])

    def test_legacy_unsent_is_rebuilt_by_core_but_keeps_original_due(self):
        self.configure_worker();calls=[]
        at=datetime(2026,10,11,6,45,tzinfo=timezone(timedelta(hours=8)))
        original_due=at+timedelta(minutes=17)
        ident=self.legacy_delivery('stale',original_due)
        worker=CoreReportWorker(self.service,lambda *args:calls.append(args) or 'synthetic-message')
        self.assertEqual(asyncio.run(worker.tick('alice',at))['prepared'],1)
        row=self.service.outbox.business_status('alice','report:daily-alice:daily:2026-10-11')[0]
        self.assertEqual(row['id'],ident);self.assertEqual(datetime.fromisoformat(row['due']),original_due)
        self.assertEqual(row['status'],'pending');self.assertEqual(row['reconciliation'],{})
        self.assertFalse(row['run_id'].startswith('legacy:'))
        self.assertEqual(asyncio.run(worker.tick('alice',at+timedelta(minutes=15)))['sent'],0)
        self.assertEqual(asyncio.run(worker.tick('alice',original_due))['sent'],1)
        self.assertEqual(len(calls),1)

    def test_legacy_unknown_requires_proof_before_new_validated_run(self):
        self.configure_worker();calls=[]
        at=datetime(2026,10,11,7,tzinfo=timezone(timedelta(hours=8)))
        ident=self.legacy_delivery('uncertain',at,attempts=1)
        worker=CoreReportWorker(self.service,lambda *args:calls.append(args) or 'synthetic-message')
        self.assertEqual(asyncio.run(worker.tick('alice',at))['prepared'],0)
        self.assertEqual(self.model.requests,[]);self.assertEqual(calls,[])
        self.service.reconcile_delivery(owner='alice',outbox_id=ident,delivered=False,evidence_ref='synthetic audited non-delivery')
        result=asyncio.run(worker.tick('alice',at+timedelta(minutes=1)))
        self.assertEqual(result['prepared'],1);self.assertEqual(result['sent'],1)
        row=self.service.outbox.business_status('alice','report:daily-alice:daily:2026-10-11')[0]
        self.assertEqual(row['attempts'],2);self.assertEqual(row['reconciliation']['delivered'],False)
        self.assertEqual(len(calls),1)

    def test_report_worker_does_not_claim_disabled_jobs_or_chat_outbox(self):
        self.configure_worker();calls=[]
        at=datetime(2026,10,11,7,tzinfo=timezone(timedelta(hours=8)))
        report=asyncio.run(self.reports.prepare(external_id='daily-alice',kind='daily',day='2026-10-11',depth='fast'))
        pending=asyncio.run(self.reports.prepare_delivery(external_id='daily-alice',result=report,channel='feishu',target='ou_alice'))
        chat=asyncio.run(self.service.consult(owner='alice',message='合成普通聊天。',request_id='chat-pending-fixture',depth='fast'))
        chat_pending=self.service.prepare_delivery(owner='alice',run_id=chat['meta']['core_run']['run_id'],business_id='feishu:message:synthetic-chat',channel='feishu',target='ou_alice',due=at)
        with self.repo.transaction('alice') as conn:
            config=self.repo.assert_scope('alice')['settings'];config['report_pipeline']['jobs'][0]['enabled']=False
            conn.execute(sql.SQL('UPDATE {} SET settings=%s WHERE id=%s').format(self.repo.table('core_owners')),(Jsonb(config),'alice'))
        count=len(self.model.requests)
        worker=CoreReportWorker(self.service,lambda *args:calls.append(args) or 'synthetic-receipt')
        result=asyncio.run(worker.tick('alice',at))
        self.assertEqual(result['prepared'],0);self.assertEqual(result['sent'],0)
        self.assertEqual(calls,[]);self.assertEqual(len(self.model.requests),count)
        rows={row['id']:row for row in self.service.outbox.status('alice')['rows']}
        self.assertEqual(rows[pending['id']]['status'],'pending');self.assertEqual(rows[chat_pending['id']]['status'],'pending')

    def test_active_report_delivery_is_not_starved_by_status_page_limit(self):
        self.configure_worker();calls=[]
        at=datetime(2026,10,11,7,tzinfo=timezone(timedelta(hours=8)))
        result=asyncio.run(self.reports.prepare(external_id='daily-alice',kind='daily',day='2026-10-11',depth='fast'))
        pending=asyncio.run(self.reports.prepare_delivery(external_id='daily-alice',result=result,channel='feishu',target='ou_alice'))
        for index in range(121):self.legacy_delivery('sent',at+timedelta(days=1,minutes=index),business='later-business:'+str(index))
        self.assertNotIn(pending['id'],[row['id'] for row in self.service.outbox.status('alice')['rows']])
        count=len(self.model.requests)
        worker=CoreReportWorker(self.service,lambda *args:calls.append(args) or 'synthetic-receipt')
        self.assertEqual(asyncio.run(worker.tick('alice',at))['sent'],1)
        self.assertEqual(len(calls),1);self.assertEqual(len(self.model.requests),count)
        self.assertEqual(self.service.outbox.business_status('alice',result['report']['business_id'])[0]['status'],'sent')


if __name__=='__main__':unittest.main()
