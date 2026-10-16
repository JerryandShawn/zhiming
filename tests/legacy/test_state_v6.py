import concurrent.futures
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'hermes'));sys.path.insert(0,str(ROOT))
from state_store import StateStore,RevisionConflict,ScopeError,EvidenceError
from migration_state import migrate


class StateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=StateStore(self.tmp.name);self.store.ensure_owner('alice');self.store.ensure_owner('bob')

    def message(self,text,id='m1',role='user',owner='alice',subject='self',case=None,at='2026-09-01T10:00:00+08:00'):
        return self.store.import_message(owner,'web',id,role,text,at,subject,case)

    def fact(self,text,id='m1',**kwargs):
        msg=self.message(text,id)
        return self.store.put_fact('alice','self',text,[{'message_id':msg['id'],'quote':text}],**kwargs)

    def test_original_author_quote_and_version_are_required(self):
        msg=self.message('我喜欢短一点的回答')
        ref={'message_id':msg['id'],'quote':'我喜欢短一点的回答'}
        saved=self.store.put_fact('alice','self',ref['quote'],[ref])
        self.assertEqual(saved['assertion_status'],'user_asserted')
        for bad in ({**ref,'quote':'我喜欢长篇回答'},{**ref,'version':99},{**ref,'start':4}):
            with self.assertRaises(EvidenceError): self.store.put_fact('alice','self',bad['quote'],[bad])
        assistant=self.message('你已经完成了行动','ai','assistant')
        with self.assertRaises(EvidenceError): self.store.put_fact('alice','self',assistant['content'],[{'message_id':assistant['id'],'quote':assistant['content']}])

    def test_owner_subject_and_channel_isolation(self):
        self.store.bind_channel('alice','feishu','account-a')
        self.assertEqual(self.store.resolve_channel('feishu','account-a')['owner'],'alice')
        with self.assertRaises(ScopeError): self.store.bind_channel('bob','feishu','account-a')
        with self.assertRaises(ScopeError): self.store.import_message('bob','feishu','x','user','这是一条消息',channel='feishu',external_id='account-a')
        msg=self.message('我喜欢安静的环境')
        with self.assertRaises(ScopeError): self.store.put_fact('bob','self',msg['content'],[{'message_id':msg['id'],'quote':msg['content']}])
        self.store.create_subject('alice','friend','朋友')
        with self.assertRaises(ScopeError): self.store.put_fact('alice','friend',msg['content'],[{'message_id':msg['id'],'quote':msg['content']}],explicit=True)

    def test_write_ack_idempotent_and_request_mismatch(self):
        msg=self.message('我喜欢清晰的小步骤')
        revision=self.store.revision('alice')
        again=self.message('我喜欢清晰的小步骤');self.assertEqual(msg['id'],again['id'])
        self.assertEqual(self.store.revision('alice'),revision)
        ref={'message_id':msg['id'],'quote':msg['content']}
        first=self.store.put_fact('alice','self',msg['content'],[ref],idempotency_key='save-once')
        rev=self.store.revision('alice')
        self.assertEqual(self.store.put_fact('alice','self',msg['content'],[ref],idempotency_key='save-once')['id'],first['id'])
        self.assertEqual(self.store.revision('alice'),rev)
        with self.assertRaises(ValueError): self.store.put_fact('alice','self',msg['content'],[ref],kind='constraint',idempotency_key='save-once')

    def test_correction_propagates_and_old_time_can_be_read(self):
        old=self.fact('我现在走读',kind='constraint')
        newmsg=self.message('更正，我现在住校','m2',at='2026-10-01T08:00:00+08:00')
        current=self.store.revision('alice')
        new=self.store.put_fact('alice','self',newmsg['content'],[{'message_id':newmsg['id'],'quote':newmsg['content']}],kind='correction',
                                supersedes_id=old['id'],expected_revision=current,explicit=True)
        restarted=StateStore(self.tmp.name)
        self.assertEqual([x['id'] for x in restarted.snapshot('alice')['facts']],[new['id']])
        self.assertEqual([x['id'] for x in restarted.snapshot('alice',at='2026-09-15')['facts']],[old['id']])
        self.assertIn('superseded',[s['reason'] for s in restarted.snapshot('alice')['suppressed_sources']])
        with self.assertRaises(EvidenceError):
            self.store.put_fact('alice','self',old['content'],old['source_refs'],kind='constraint',idempotency_key='old-message-reimport')
        with self.assertRaises(RevisionConflict):
            self.store.put_fact('alice','self',newmsg['content'],[{'message_id':newmsg['id'],'quote':newmsg['content']}],
                                idempotency_key='stale',expected_revision=current)

    def test_old_event_cannot_replace_current_fact(self):
        old=self.fact('我现在住校',kind='constraint')
        msg=self.message('更正，我以前走读','prior',at='2026-10-02')
        with self.assertRaises(EvidenceError):
            self.store.put_fact('alice','self',msg['content'],[{'message_id':msg['id'],'quote':msg['content']}],kind='correction',
                                supersedes_id=old['id'],valid_from='2025-01-01',expected_revision=self.store.revision('alice'),explicit=True)

    def test_no_prediction_or_hypothesis_promotion(self):
        with self.assertRaises(EvidenceError): self.fact('假如我明年换工作',kind='event')
        concern=self.fact('我担心明年可能会失业','worry',kind='concern')
        self.assertEqual(concern['kind'],'concern')
        ai=self.message('你明年一定获得录取','prediction','assistant')
        saved=self.store.put_fact('alice','self',ai['content'],[{'message_id':ai['id'],'quote':ai['content']}],kind='interpretation',assertion_status='unverified_prediction')
        self.assertEqual(saved['assertion_status'],'unverified_prediction')
        self.assertEqual(self.store.profile('alice')['values'],{})

    def test_sensitive_third_party_and_profile_consent(self):
        msg=self.message('我的出生日期是1990-05-03')
        with self.assertRaises(EvidenceError): self.store.put_fact('alice','self',msg['content'],[{'message_id':msg['id'],'quote':msg['content']}],kind='profile')
        f=self.store.put_fact('alice','self',msg['content'],[{'message_id':msg['id'],'quote':msg['content']}],kind='profile',field='birth.date',value='1990-05-03',explicit=True)
        self.assertEqual(self.store.profile('alice')['values']['birth.date'],'1990-05-03')
        with self.assertRaises(EvidenceError): self.store.put_fact('alice','self',msg['content'],[{'message_id':msg['id'],'quote':msg['content']}],kind='profile',field='birth.date',value='1991-05-03',explicit=True)
        pending=self.fact('我偏好先看简短结论','pending',consent='pending')
        self.assertNotIn(pending['id'],[x['id'] for x in self.store.snapshot('alice')['facts']])

    def test_user_can_disable_automatic_memory(self):
        self.store.update_settings('alice',{'auto_save_low_sensitivity':False},self.store.revision('alice'))
        with self.assertRaises(EvidenceError): self.fact('我喜欢简洁的回答')
        saved=self.fact('我喜欢简洁的回答',explicit=True)
        self.assertEqual(saved['status'],'active')

    def test_profile_boolean_can_use_explicit_form_literal(self):
        msg=self.message('确认保存出生设置：{"time_unknown":true}','bool-profile')
        saved=self.store.put_fact('alice','self',msg['content'],[{'message_id':msg['id'],'quote':msg['content']}],
                                   kind='profile',field='birth.time_unknown',value=True,explicit=True)
        self.assertIs(saved['value'],True)
        self.assertIs(self.store.profile('alice')['values']['birth.time_unknown'],True)

    def test_profile_conflict_is_not_last_write_wins(self):
        self.fact('我喜欢蓝色','color1',field='favorite_color',value='蓝色')
        self.fact('我喜欢绿色','color2',field='favorite_color',value='绿色')
        profile=self.store.profile('alice')
        self.assertNotIn('favorite_color',profile['values'])
        self.assertIn('favorite_color',profile['conflicts'])

    def test_stop_and_delete_block_reimport_and_purge_audit(self):
        f=self.fact('我不想别人看到这段私人经历',kind='background',explicit=True)
        self.store.stop_fact('alice',f['id'],self.store.revision('alice'))
        self.assertEqual(self.store.snapshot('alice')['facts'],[])
        with self.assertRaises(EvidenceError): self.fact('我不想别人看到这段私人经历',kind='background',explicit=True,idempotency_key='reimport')
        deleted=self.store.delete_fact('alice',f['id'],self.store.revision('alice'),scope='source')
        self.assertEqual(deleted['content'],'')
        self.assertTrue(all('quote' not in r for r in deleted['source_refs']))
        self.assertEqual(self.store.get_message('alice',f['source_refs'][0]['message_id'],include_suppressed=True)['content'],'')
        with self.store.db() as c:
            audit=' '.join(str(tuple(r)) for r in c.execute('SELECT * FROM audit'))
            self.assertNotIn('私人经历',audit)
        # Restoring an old source copy cannot recover deleted raw content.
        self.assertEqual(self.message('我不想别人看到这段私人经历')['content'],'')

    def test_fact_only_delete_preserves_history_but_excludes_sources(self):
        f=self.fact('我喜欢晚间散步')
        self.store.delete_fact('alice',f['id'],self.store.revision('alice'))
        self.assertEqual(self.store.get_message('alice',f['source_refs'][0]['message_id'],True)['content'],'我喜欢晚间散步')
        with self.assertRaises(EvidenceError): self.store.get_message('alice',f['source_refs'][0]['message_id'])

    def test_delete_after_stop_also_purges_derived_case_title(self):
        f=self.fact('我喜欢安静的私人住所')
        case=self.store.create_case('alice','self','我喜欢安静的私人住所',source_refs=f['source_refs'],goal=f['content'])
        self.store.stop_fact('alice',f['id'],self.store.revision('alice'))
        self.assertEqual(self.store.snapshot('alice')['cases'][0]['source_refs'],[])
        self.store.delete_fact('alice',f['id'],self.store.revision('alice'))
        self.assertNotIn('私人住所',json.dumps(self.store.get_case('alice',case['id']),ensure_ascii=False))

    def test_concurrent_stale_writes_only_one_commits(self):
        m1=self.message('我喜欢方案A','a');m2=self.message('我喜欢方案B','b')
        revision=self.store.revision('alice')
        def write(msg):
            try:
                s=StateStore(self.tmp.name)
                return s.put_fact('alice','self',msg['content'],[{'message_id':msg['id'],'quote':msg['content']}],expected_revision=revision)['id']
            except RevisionConflict: return 'conflict'
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool: result=list(pool.map(write,[m1,m2]))
        self.assertEqual(result.count('conflict'),1)
        self.assertEqual(len(self.store.snapshot('alice')['facts']),1)

    def test_nested_write_registration_and_mutation_are_atomic(self):
        initial=self.store.revision('alice')
        with self.assertRaises(EvidenceError):
            with self.store.db(True) as c:
                self.store._revision(c,'alice',initial)
                msg=self.message('更正，我现在选择新的方案','atomic-fail')
                self.store.put_fact('alice','self','不存在的原话',[{'message_id':msg['id'],'quote':'不存在的原话'}],expected_revision=self.store.revision('alice'))
        self.assertEqual(self.store.revision('alice'),initial)
        with self.store.db() as c:self.assertIsNone(c.execute("SELECT id FROM messages WHERE source_id='atomic-fail'").fetchone())
        with self.store.db(True) as c:
            self.store._revision(c,'alice',initial)
            msg=self.message('我喜欢原子保存','atomic-ok')
            saved=self.store.put_fact('alice','self',msg['content'],[{'message_id':msg['id'],'quote':msg['content']}],expected_revision=self.store.revision('alice'))
        self.assertEqual(saved['status'],'active')

    def test_nested_read_cannot_upgrade_to_write(self):
        with self.assertRaises(RuntimeError):
            with self.store.db(): self.store.update_settings('alice',{'auto_save_low_sensitivity':False},self.store.revision('alice'))
        self.assertTrue(self.store.snapshot('alice')['settings']['auto_save_low_sensitivity'])

    def test_case_a_b_a_and_multiple_subjects(self):
        a=self.store.create_case('alice','self','报读学校A')
        b=self.store.create_case('alice','self','假期计划B')
        self.message('先讨论假期计划B','switch-b',case=b['id'])
        resolved=self.store.resolve_cases('alice','self','回到报读学校A，再看一下进展')
        self.assertEqual(resolved['case_id'],a['id'])
        self.message('回到报读学校A','switch-a',case=a['id'])
        self.assertEqual(self.store.resolve_cases('alice','self','后来我试了那个方法')['case_id'],a['id'])
        self.assertTrue(self.store.resolve_cases('alice','self','之前那个事项怎么了')['needs_clarification'])
        both=self.store.resolve_cases('alice','self','报读学校A会影响假期计划B吗')
        self.assertEqual(set(both['case_ids']),{a['id'],b['id']})
        self.store.create_subject('alice','friend','朋友')
        self.assertEqual(self.store.resolve_cases('alice','friend','后来我试了')['case_ids'],[])
        with self.assertRaises(ScopeError): self.store.resolve_cases('bob','self','继续',case_ids=[a['id']])

    def test_case_execution_requires_user_source_and_idempotence(self):
        case=self.store.create_case('alice','self','学习安排')
        ai=self.message('你已经完成了今天计划','ai','assistant',case=case['id'])
        with self.assertRaises(EvidenceError): self.store.add_case_event('alice',case['id'],'completed',ai['content'],[{'message_id':ai['id'],'quote':ai['content']}],assertion_status='assistant_interpretation')
        user=self.message('我今天完成了计划','done',case=case['id'])
        refs=[{'message_id':user['id'],'quote':user['content']}]
        first=self.store.add_case_event('alice',case['id'],'completed',user['content'],refs)
        second=self.store.add_case_event('alice',case['id'],'completed',user['content'],refs)
        self.assertEqual(first['id'],second['id'])
        self.assertEqual(len(self.store.get_case('alice',case['id'])['events']),1)
        with self.assertRaises(EvidenceError): self.store.update_case('alice',case['id'],{'decision':'我已决定退学'},refs,self.store.revision('alice'))

    def test_trace_is_minimal_and_scoped(self):
        self.store.record_trace('alice','run-1',{'revision':3,'injected_ids':['fact-1'],'status':'complete','content':'私人正文','api_key':'secret',
                                                'budget':{'input_tokens':120,'thinking':'隐藏内容'},'token_usage':{'input_tokens':120,'output_tokens':30}})
        t=self.store.get_trace('alice','run-1')['payload']
        self.assertNotIn('私人正文',json.dumps(t,ensure_ascii=False));self.assertNotIn('secret',json.dumps(t));self.assertNotIn('thinking',t['budget'])
        with self.assertRaises(ScopeError): self.store.get_trace('bob','run-1')

    def test_300_turn_restart_retains_critical_facts_and_case(self):
        critical=self.fact('我需要每天晚上九点前回家',kind='constraint')
        case=self.store.create_case('alice','self','长期学习事项')
        for i in range(300):
            self.message('合成混合话题第%d轮：%s'%(i,['天气','学习','复盘','休息'][i%4]),'long-'+str(i),case=case['id'] if i==3 else None)
        restarted=StateStore(self.tmp.name)
        snapshot=restarted.snapshot('alice',case=case['id'])
        self.assertIn(critical['id'],[x['id'] for x in snapshot['facts']])
        self.assertEqual(restarted.resolve_cases('alice','self','上次那件事继续说')['case_id'],case['id'])
        self.assertEqual(len(snapshot['facts']),1)


class MigrationTests(unittest.TestCase):
    def fixture(self,base):
        base.mkdir()
        with sqlite3.connect(base/'web.db') as c:
            c.executescript('CREATE TABLE turns(id,session_id,message,answer,created_at,updated_at);CREATE TABLE memories(id,text,quote,category,source_turn,created_at,status,supersedes);')
            c.execute('INSERT INTO turns VALUES(?,?,?,?,?,?)',('old','shared','我以前走读','AI预测我未来发财','2026-09-01','2026-09-01'))
            c.execute('INSERT INTO turns VALUES(?,?,?,?,?,?)',('new','shared','更正，我现在住校','','2026-10-01','2026-10-01'))
            c.execute('INSERT INTO memories VALUES(?,?,?,?,?,?,?,?)',('hidden','我以前走读','我以前走读','背景','old','2026-09-01','hidden',None))
            c.execute('INSERT INTO memories VALUES(?,?,?,?,?,?,?,?)',('active','更正，我现在住校','更正，我现在住校','更正','new','2026-10-01','active','hidden'))
            c.execute('INSERT INTO memories VALUES(?,?,?,?,?,?,?,?)',('edited','AI替我补充的事实','没有原话','背景','new','2026-10-01','active',None))
        c.close()
        (base/'archive.json').write_text(json.dumps({'user':{'name':'旧档案名'},'conversation_state':{'summary':'助手总结用户已经完成行动'}},ensure_ascii=False),encoding='utf-8')

    def test_dry_run_idempotence_and_no_legacy_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)/'source';dest=Path(tmp)/'destination';self.fixture(base)
            before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in base.iterdir()}
            dry=migrate(base,dest,'alice');self.assertTrue(dry['dry_run']);self.assertFalse(dest.exists())
            first=migrate(base,dest,'alice',dry_run=False)
            store=StateStore(dest);facts=store.list_facts('alice');ids={f['id'] for f in facts}
            self.assertEqual(len([f for f in facts if f['assertion_status']=='user_asserted']),1)
            self.assertNotIn('我以前走读',[f['content'] for f in facts])
            self.assertTrue(all(f['assertion_status']=='legacy_unverified' for f in facts if f['id']!=next(x['id'] for x in facts if x['assertion_status']=='user_asserted')))
            self.assertEqual(store.profile('alice')['values'],{})
            second=migrate(base,dest,'alice',dry_run=False)
            self.assertEqual(ids,{f['id'] for f in store.list_facts('alice')})
            self.assertGreater(second['already_mapped'],0)
            self.assertEqual(before,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in base.iterdir()})

    def test_deletion_survives_rerun_from_old_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)/'source';dest=Path(tmp)/'destination';self.fixture(base)
            migrate(base,dest,'alice',dry_run=False);store=StateStore(dest)
            fact=next(f for f in store.list_facts('alice') if f['assertion_status']=='user_asserted')
            store.delete_fact('alice',fact['id'],store.revision('alice'),scope='source')
            migrate(base,dest,'alice',dry_run=False)
            self.assertEqual(store.get_fact('alice',fact['id'])['content'],'')
            self.assertNotIn(fact['id'],[f['id'] for f in store.snapshot('alice')['facts']])

    def test_later_legacy_delete_is_replayed_before_reimport(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)/'source';dest=Path(tmp)/'destination';self.fixture(base)
            migrate(base,dest,'alice',dry_run=False);store=StateStore(dest)
            fact=next(f for f in store.list_facts('alice') if f['assertion_status']=='user_asserted')
            c=sqlite3.connect(base/'web.db')
            try:
                c.execute("UPDATE memories SET status='deleted' WHERE id='active'");c.commit()
            finally: c.close()
            migrate(base,dest,'alice',dry_run=False)
            self.assertEqual(store.get_fact('alice',fact['id'])['content'],'')
            self.assertEqual(store.get_fact('alice',fact['id'])['status'],'deleted')


if __name__=='__main__': unittest.main(verbosity=2)
