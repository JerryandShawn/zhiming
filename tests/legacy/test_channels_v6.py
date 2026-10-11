import json,sqlite3,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'hermes'))
from state_store import StateStore,ScopeError,EvidenceError,RevisionConflict
from context_query import ChannelContext
from context_builder import ContextBuilder
from report_store import store,store_structured
from archive_store import read_json


class ChannelIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.db=self.base/'hermes.db';self.state=StateStore(self.base)
        for owner,external in [('alice','ou_alice'),('bob','ou_bob')]:
            self.state.ensure_owner(owner);self.state.bind_channel(owner,'feishu',external);self.state.bind_channel(owner,'report','daily-'+owner)
        c=sqlite3.connect(self.db)
        try:
            c.executescript('CREATE TABLE sessions(id TEXT,source TEXT,user_id TEXT,chat_id TEXT,chat_type TEXT);CREATE TABLE messages(id TEXT,session_id TEXT,role TEXT,content TEXT,timestamp REAL,active INTEGER);')
            c.executemany('INSERT INTO sessions VALUES(?,?,?,?,?)',[('s-a','feishu','ou_alice','oc_alice','dm'),('s-b','feishu','ou_bob','oc_bob','dm'),('s-g','feishu','ou_alice','oc_group','group'),('s-other','telegram','ou_alice','oc_other','dm')])
            c.executemany('INSERT INTO messages VALUES(?,?,?,?,?,?)',[
                ('a1','s-a','user','请记住，我喜欢简洁的回答',1790800000,1),
                ('a2','s-a','user','更正，我喜欢详细的回答',1790800100,1),
                ('a3','s-a','assistant','我预测你明年会成功',1790800200,1),
                ('a4','s-a','user','我喜欢旧的无效信息',1790800200,0),
                ('b1','s-b','user','请记住，我喜欢蓝色衣服',1790800000,1),
                ('g1','s-g','user','请记住，我喜欢群聊内容',1790800000,1),
                ('other1','s-other','user','请记住，我喜欢另一个渠道',1790800000,1)])
            c.commit()
        finally:c.close()
        self.bridge=ChannelContext(self.base,self.db)

    def test_unbound_or_spoofed_channel_rejected(self):
        with self.assertRaises(ScopeError):self.bridge.prepare('继续','feishu','unbound')
        with self.assertRaises(ScopeError):self.bridge.prepare('继续',None,None)
        for mid,quote in [('b1','我喜欢蓝色衣服'),('a3','我预测你明年会成功'),('a4','我喜欢旧的无效信息'),('g1','我喜欢群聊内容'),('other1','我喜欢另一个渠道')]:
            with self.assertRaises(EvidenceError):self.bridge.remember_hermes(mid,quote,'feishu','ou_alice')
        self.assertEqual(self.state.list_facts('alice'),[])

    def test_web_hermes_report_share_correction_and_owner_scope(self):
        original=self.bridge.remember_hermes('a1','我喜欢简洁的回答','feishu','ou_alice')
        self.assertEqual(original['write_status'],'saved')
        saved=self.bridge.remember_hermes('a2','更正，我喜欢详细的回答','feishu','ou_alice','更正',original['id'],expected_revision=self.state.revision('alice'))
        retry=self.bridge.remember_hermes('a2','更正，我喜欢详细的回答','feishu','ou_alice','更正',original['id'],expected_revision=0)
        self.assertEqual(retry['id'],saved['id'])
        for channel,external in [('feishu','ou_alice'),('report','daily-alice')]:
            prepared=self.bridge.prepare('根据我的偏好安排今天的计划',channel,external)
            facts=prepared['context']['effective_facts']
            self.assertEqual([f['id'] for f in facts],[saved['id']])
            self.assertEqual(prepared['revision'],self.state.revision('alice'))
            self.assertNotIn('我喜欢简洁的回答',json.dumps(prepared['messages'],ensure_ascii=False))
        website=ContextBuilder(self.state).build('alice','self','安排学习计划',[])[0]
        self.assertEqual([f['id'] for f in website['effective_facts']],[saved['id']])
        bob=self.bridge.prepare('我的偏好是什么','report','daily-bob')
        self.assertEqual(bob['context']['effective_facts'],[])
        self.assertNotIn('详细的回答',json.dumps(bob,ensure_ascii=False))

    def test_sync_is_source_scoped_and_idempotent(self):
        self.assertEqual(self.bridge.sync_hermes('feishu','ou_alice'),3)
        revision=self.state.revision('alice')
        self.bridge.sync_hermes('feishu','ou_alice')
        self.assertEqual(self.state.revision('alice'),revision)
        history=self.bridge.history('alice','self')
        self.assertEqual(len(history),3)
        text=json.dumps(history,ensure_ascii=False)
        for excluded in ('蓝色衣服','群聊内容','另一个渠道','无效信息'):self.assertNotIn(excluded,text)

    def test_chat_binding_requires_single_real_author(self):
        self.state.bind_channel('alice','feishu','oc_alice')
        saved=self.bridge.remember_hermes('a1','我喜欢简洁的回答','feishu','oc_alice',binding_kind='chat')
        self.assertEqual(saved['owner_user_id'],'alice')
        c=sqlite3.connect(self.db)
        try:
            c.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',('s-ambiguous','feishu','another-user','oc_alice','dm'))
            c.execute('INSERT INTO messages VALUES(?,?,?,?,?,?)',('ambiguous','s-ambiguous','user','另一个人的内容',1790800400,1));c.commit()
        finally:c.close()
        with self.assertRaises(ScopeError):self.bridge.sync_hermes('feishu','oc_alice',binding_kind='chat')
        with self.assertRaises(ScopeError):self.bridge.remember_hermes('a1','我喜欢简洁的回答','feishu','oc_alice',binding_kind='chat')

    def profile_fact(self,text,field,value,supersedes=None):
        row=self.state.import_message('alice','web','profile-'+str(self.state.revision('alice'))+':user','user',text)
        return self.state.put_fact('alice','self',text,[{'message_id':row['id'],'quote':text}],kind='profile',field=field,value=value,
                                   explicit=True,supersedes_id=supersedes,expected_revision=self.state.revision('alice') if supersedes else None)

    def test_chart_profile_uses_current_explicit_fact(self):
        old=self.profile_fact('请记住，我的出生时间是1990-05-03 13:18','birth.solar_datetime','1990-05-03 13:18')
        self.profile_fact('更正，我的出生时间是1990-05-03 14:18','birth.solar_datetime','1990-05-03 14:18',old['id'])
        with patch('chart_context.bundle',return_value={'bazi':{'status':'missing'}}) as compute:
            result=self.bridge.prepare('三盘看今日计划','report','daily-alice',with_charts=True,date='2026-10-10')
        self.assertEqual(compute.call_args.args[0]['user']['birth']['solar_datetime'],'1990-05-03 14:18')
        self.assertEqual(result['archive']['state_revision'],result['revision'])

    def test_report_run_revision_and_owner_gates(self):
        report_path=self.base/'archive.json';prepared=self.bridge.prepare('三盘联动晨报','report','daily-alice')
        with patch('guidance.validate_document',return_value='有效结构已校验；以现实行动为准。'*40):
            store_structured(report_path,'2026-10-10','晨报',{'fixture':True},state=self.state,owner='alice',run_id=prepared['run_id'])
        record=read_json(report_path)['reports'][0]
        self.assertEqual(record['owner_user_id'],'alice');self.assertEqual(record['state_revision'],prepared['revision'])
        self.assertTrue(record['validation']['chart_fields_checked']);self.assertTrue(record['validation']['state_revision_checked'])
        with self.assertRaises(ScopeError):
            store_structured(report_path,'2026-10-10','晨报',{},state=self.state,owner='bob',run_id=prepared['run_id'])
        bob=self.bridge.prepare('三盘联动晨报','report','daily-bob')
        with patch('guidance.validate_document',return_value='另一用户的有效结构报告。'*40):
            with self.assertRaises(ScopeError):store_structured(report_path,'2026-10-10','晨报',{},state=self.state,owner='bob',run_id=bob['run_id'])
        self.assertEqual(read_json(report_path)['reports'][0],record)

    def test_stale_report_rejected_before_validation_and_during_commit(self):
        prepared=self.bridge.prepare('三盘联动晨报','report','daily-alice')
        self.bridge.remember_hermes('a1','我喜欢简洁的回答','feishu','ou_alice')
        with patch('guidance.validate_document') as validate:
            with self.assertRaises(RevisionConflict):store_structured(self.base/'archive.json','2026-10-10','晨报',{},state=self.state,owner='alice',run_id=prepared['run_id'])
            validate.assert_not_called()
        fresh=self.bridge.prepare('三盘联动晨报','report','daily-alice')
        def concurrent_change(*args):
            self.state.import_message('alice','web','during-validation:user','user','更正，今天的安排变了')
            return '校验期间发生新的用户更正。'*40
        with patch('guidance.validate_document',side_effect=concurrent_change):
            with self.assertRaises(RevisionConflict):store_structured(self.base/'archive.json','2026-10-10','晨报',{},state=self.state,owner='alice',run_id=fresh['run_id'])
        self.assertFalse((self.base/'archive.json').exists())

    def test_new_reports_cannot_bypass_structured_or_identity_gate(self):
        with self.assertRaises(ValueError):store(self.base/'archive.json','2026-10-10','晨报','纯文本报告'*100)
        with self.assertRaises(ScopeError):store_structured(self.base/'archive.json','2026-10-10','晨报',{'fake':True})


if __name__=='__main__':unittest.main(verbosity=2)
