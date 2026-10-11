import json,sys,tempfile,unittest
from contextlib import closing
from pathlib import Path
from datetime import datetime,timedelta
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'hermes'))
from conversation_store import ConversationStore
from report_pipeline import Pipeline,scheduled,TZ,DeliveryRejected
from archive_store import atomic_write,read_json

class ConversationTests(unittest.TestCase):
    def test_migration_idempotence_and_audit(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);atomic_write(p/'webchat.json',[{'role':'assistant','content':'独立旧回答','at':'2026-09-28T09:00:00'}, {'role':'user','content':'旧问题'},{'role':'assistant','content':'旧答案'}])
            s=ConversationStore(d);self.assertEqual(len(s.history()),3)
            self.assertEqual(len(ConversationStore(d).history()),3)
            t,fresh=s.begin('testing-0001','shared','请记住我喜欢简洁的回答',[],{});self.assertTrue(fresh)
            self.assertFalse(s.begin('testing-0001','shared','请记住我喜欢简洁的回答',[],{})[1])
            with self.assertRaises(ValueError):s.begin('testing-0001','shared','不同问题',[],{})
            with self.assertRaises(ValueError):s.remember(t['id'],'我今年18岁')
            m=s.remember(t['id'],'我喜欢简洁的回答','偏好');self.assertEqual(len(s.memories()),1)
            s.edit_memory(m['id'],text='我喜欢具体的依据');self.assertEqual(len(s.audit(m['id'])),1)
            s.edit_memory(m['id'],status='hidden');self.assertEqual(s.memories(),[])
            self.assertEqual(read_json(p/'archive.json')['conversation_state']['user_facts'],[])
            s.recover_interrupted();self.assertEqual(s.get_turn(t['id'])['status'],'interrupted')
            s.finish(t['id'],'完整回答','complete',{});s.reconcile();s.reconcile()
            self.assertEqual(len(read_json(p/'archive.json')['daily_log'][0]['questions']),1)

    def test_image_normalization(self):
        import io,base64
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            s=ConversationStore(d);b=io.BytesIO();Image.new('RGB',(20,20),'red').save(b,format='PNG')
            ids=s.save_images(['data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()])
            self.assertEqual(s.image_block(ids[0])['source']['media_type'],'image/jpeg')
            self.assertTrue(s.image_path(ids[0]).is_file())
            with self.assertRaises(ValueError):s.image_path('../archive.json')
            with self.assertRaises(ValueError):s.save_images(['data:image/svg+xml;base64,AA=='])

class PipelineTests(unittest.TestCase):
    def build(self,d):
        atomic_write(Path(d)/'report-pipeline.json',{'enabled':True,'jobs':[{'kind':'daily','id':'job-daily','target':'oc_fake'}]})
        return Pipeline(d,Path(d)/'cron')

    def test_schedule_and_no_early_or_duplicate_delivery(self):
        now=datetime(2026,9,29,6,45,tzinfo=TZ)
        with tempfile.TemporaryDirectory() as d:
            p=self.build(d);p.seed(now);ident='2026-09-29-daily';p.update(ident,status='ready',content='完整报告'*100)
            sent=[];send=lambda target,text,uid:sent.append(uid) or 'message-1'
            p.deliver(now,send);self.assertEqual(sent,[])
            p.deliver(now.replace(hour=7,minute=0),send);p.deliver(now.replace(hour=7,minute=1),send)
            self.assertEqual(len(sent),1)
            self.assertEqual(next(r for r in p.rows() if r['id']==ident)['status'],'sent')
        self.assertIsNone(scheduled('weekly',now.date()))
        self.assertIsNone(scheduled('quarterly',now.date()))

    def test_ambiguous_retry_uses_same_uuid_and_stops_before_one_hour(self):
        now=datetime(2026,9,29,7,tzinfo=TZ)
        with tempfile.TemporaryDirectory() as d:
            p=self.build(d);p.seed(now);ident='2026-09-29-daily';p.update(ident,status='ready',content='报告'*200)
            ids=[]
            def timeout(target,text,uid):ids.append(uid);raise TimeoutError()
            p.deliver(now,timeout);p.deliver(now+timedelta(minutes=3),timeout)
            self.assertEqual(ids[0],ids[1])
            p.deliver(now+timedelta(minutes=51),timeout);self.assertEqual(len(ids),2)
            self.assertEqual(next(r for r in p.rows() if r['id']==ident)['status'],'uncertain')
            with self.assertRaises(ValueError):p.retry(ident)

    def test_rejection_after_timeout_keeps_ambiguity(self):
        now=datetime(2026,9,29,7,tzinfo=TZ)
        with tempfile.TemporaryDirectory() as d:
            p=self.build(d);p.seed(now);ident='2026-09-29-daily';p.update(ident,status='ready',content='报告'*200)
            def timeout(*args):raise TimeoutError()
            def reject(*args):raise DeliveryRejected('duplicate')
            p.deliver(now,timeout);p.deliver(now+timedelta(minutes=3),reject)
            row=next(r for r in p.rows() if r['id']==ident);self.assertEqual(row['status'],'retrying');self.assertEqual(row['first_send'],now.timestamp())

    def test_compensator_ignores_incomplete_outputs(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as d:
            p=self.build(d);folder=Path(d)/'cron/output/job-daily';folder.mkdir(parents=True)
            content='完整的报告正文与实际依据'*30
            (folder/'2026-09-29_06-45-00.md').write_text('## Prompt\n不要收录这段\n## Response\n'+content,encoding='utf-8')
            with closing(sqlite3.connect(Path(d)/'cron/executions.db')) as c,c:
                c.execute('CREATE TABLE executions(job_id,status,started_at,finished_at,claimed_at)')
                c.execute('INSERT INTO executions VALUES(?,?,?,?,?)',('job-daily','running','2026-09-29T06:45:00+08:00',None,'2026-09-29T06:45:00+08:00'))
            p.recover();self.assertFalse((Path(d)/'archive.json').exists())
            with closing(sqlite3.connect(Path(d)/'cron/executions.db')) as c,c:c.execute("UPDATE executions SET status='completed',finished_at='2026-09-29T06:49:00+08:00'")
            p.recover();p.recover();reports=read_json(Path(d)/'archive.json')['reports']
            self.assertEqual(len(reports),1);self.assertEqual(reports[0]['content'],content)

    def test_rejected_does_not_become_unknown_delivery(self):
        now=datetime(2026,9,29,7,tzinfo=TZ)
        with tempfile.TemporaryDirectory() as d:
            p=self.build(d);p.seed(now);ident='2026-09-29-daily';p.update(ident,status='ready',content='报告'*200)
            def reject(*args):raise DeliveryRejected('invalid permissions')
            for i in range(5):p.deliver(now+timedelta(minutes=3*i),reject)
            row=next(r for r in p.rows() if r['id']==ident);self.assertEqual(row['status'],'delivery_failed');self.assertEqual(row['first_send'],0)

if __name__=='__main__':unittest.main(verbosity=2)
