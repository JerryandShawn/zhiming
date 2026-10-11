"""Real PostgreSQL tests with disposable schemas and synthetic data only."""
import json
import os
import sys
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from psycopg import sql
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import BudgetExceeded, EvidenceError, LeaseConflict, RevisionConflict, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository


def test_dsn():
    configured=os.environ.get('CORE_TEST_DSN') or os.environ.get('ZHIMING_TEST_DSN')
    fixture=ROOT.parent/'dev-environment.json'
    if configured:return configured
    if fixture.is_file():return json.loads(fixture.read_text(encoding='utf-8'))['dsn']
    raise unittest.SkipTest('Real PostgreSQL DSN is required; no SQLite stand-in')


class MemoryPostgresTests(unittest.TestCase):
    def setUp(self):
        self.schema='test_memory_'+uuid.uuid4().hex[:20]
        self.repo=PostgresRepository(test_dsn(),schema=self.schema)
        self.addCleanup(self.cleanup)
        self.repo.ensure_owner('alpha');self.repo.ensure_owner('beta')
        self.memory=MemoryService(self.repo)

    def cleanup(self):
        with self.repo.pool.connection() as c:c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.repo.close()

    def source(self,text,key=None,subject='self',cases=None):
        return self.memory.receive('alpha',subject,text,source_id=key or uuid.uuid4().hex,case_ids=cases or [])

    def test_explicit_optout_and_sensitive_markers_never_authorize(self):
        for text in ('不要存储这条信息。我喜欢晚上慢跑。','请别留存。我偏好早起。','不记录这条信息。我喜欢喝茶。'):
            row=self.source(text)
            self.assertEqual(self.memory.auto_preferences('alpha','self',row['id']),[])
        source=self.source('其实我已被诊断为抑郁症')
        result=self.memory.save_fact('alpha','self',source['id'],source['content'],'background')
        self.assertEqual(result['write_status'],'pending_confirmation')
        self.assertEqual(self.memory.facts('alpha'),[])

    def test_authorization_is_range_scoped_and_secrets_rejected(self):
        source=self.source('请保存我的生日为2000-01-01。我已被诊断为抑郁症。')
        birth=self.memory.save_fact('alpha','self',source['id'],'请保存我的生日为2000-01-01','profile',field='birth.solar_datetime',value='2000-01-01')
        self.assertEqual(birth['write_status'],'saved')
        other=self.memory.save_fact('alpha','self',source['id'],'我已被诊断为抑郁症','background')
        self.assertEqual(other['write_status'],'pending_confirmation')
        secret=self.source('请记住我的密码为synthetic-only。')
        self.assertEqual(self.memory.save_fact('alpha','self',secret['id'],secret['content'],'background')['write_status'],'rejected')

    def test_multi_case_global_scope_and_distinct_versions(self):
        cases=[self.memory.create_case('alpha','self',t)['id'] for t in ('学习安排','工作安排','投资安排')]
        for idx,text in enumerate(('我不能参加夜间课程','我不接受周末加班','我偏好高风险投资')):
            source=self.source(text,cases=[cases[idx]])
            self.memory.save_fact('alpha','self',source['id'],text,'constraint',case_id=cases[idx])
        snap=self.memory.snapshot('alpha','self',cases[:2])
        self.assertEqual({f['case_id'] for f in snap['facts']},set(cases[:2]))
        before=snap['versions']
        unrelated=self.source('我喜欢长期投资',cases=[cases[2]])
        self.memory.save_fact('alpha','self',unrelated['id'],unrelated['content'],'preference',case_id=cases[2])
        self.assertTrue(self.repo.verify_versions('alpha',before))
        global_source=self.source('我喜欢简短回答')
        self.memory.save_fact('alpha','self',global_source['id'],global_source['content'])
        self.assertFalse(self.repo.verify_versions('alpha',before))

    def test_correction_preserves_independent_fact_from_same_message(self):
        source=self.source('我不能上夜班。我喜欢周末徒步。')
        night=self.memory.save_fact('alpha','self',source['id'],'我不能上夜班','constraint')
        hike=self.memory.save_fact('alpha','self',source['id'],'我喜欢周末徒步')
        correction=self.source('更正：我现在可以上夜班。')
        changed=self.memory.correct_fact('alpha',night['id'],correction['id'],correction['content'],expected_revision=night['revision'],operation_id='retry-correction')
        self.assertEqual(changed['write_status'],'saved')
        self.assertEqual({f['id'] for f in self.memory.facts('alpha')},{hike['id'],changed['id']})
        context=self.memory.get_source('alpha',source['id'],for_context=True)['content']
        self.assertNotIn('我不能上夜班',context);self.assertIn('我喜欢周末徒步',context)
        with self.assertRaises(EvidenceError):self.memory.save_fact('alpha','self',source['id'],'我不能上夜班','constraint')
        retry=self.memory.correct_fact('alpha',night['id'],correction['id'],correction['content'],expected_revision=night['revision'],operation_id='retry-correction')
        self.assertEqual(retry['id'],changed['id'])

    def test_source_delete_is_irreversible_and_ledger_has_no_text(self):
        source=self.source('我喜欢SYNTHETIC_PRIVACY_781',key='original-781')
        fact=self.memory.save_fact('alpha','self',source['id'],source['content'])
        result=self.memory.retire_fact('alpha',fact['id'],expected_revision=fact['revision'],scope='source')
        self.assertEqual(result['write_status'],'deleted')
        self.assertEqual(self.memory.get_source('alpha',source['id'])['content'],'')
        with self.assertRaises(EvidenceError):self.source('我喜欢SYNTHETIC_PRIVACY_781',key='original-781')
        self.assertNotIn('SYNTHETIC_PRIVACY_781',json.dumps(self.repo.revocations('alpha'),default=str))
        self.assertEqual(self.memory.retire_fact('alpha',fact['id'],expected_revision=0)['write_status'],'deleted')

    def test_cross_owner_subject_and_fake_author_fail(self):
        source=self.source('我喜欢安静')
        with self.assertRaises(ScopeError):self.repo.get('beta','message',source['id'])
        self.repo.create_subject('alpha','other','另一个合成人物')
        with self.assertRaises(ScopeError):self.memory.save_fact('alpha','other',source['id'],source['content'])
        assistant=self.memory.receive('alpha','self','我喜欢安静',source_id='assistant-only',role='assistant')
        with self.assertRaises(EvidenceError):self.memory.save_fact('alpha','self',assistant['id'],assistant['content'])
        self.repo.bind_channel('alpha','feishu','synthetic-A')
        with self.assertRaises(ScopeError):self.memory.receive('beta','self','synthetic',source_id='f',channel='feishu',external_id='synthetic-A')

    def test_hypothesis_and_legacy_do_not_become_effective(self):
        source=self.source('要是我喜欢高风险投资，应该怎么办？')
        self.assertEqual(self.memory.save_fact('alpha','self',source['id'],'我喜欢高风险投资')['write_status'],'rejected')
        legacy=self.memory.receive('alpha','self','SYNTHETIC_UNVERIFIED',channel='migration',source_id='legacy',role='legacy')
        pending=self.memory.save_fact('alpha','self',legacy['id'],legacy['content'],'background',assertion_status='legacy_unverified')
        self.assertEqual(pending['write_status'],'pending_confirmation')
        self.assertEqual(self.memory.snapshot('alpha')['facts'],[])

    def test_durable_idempotent_budget_and_expired_lease(self):
        request={'message_id':'synthetic-id','case_ids':[]}
        queued=self.repo.queue_run('alpha','stable-operation',request,depth='fast')
        duplicate=self.repo.queue_run('alpha','stable-operation',request,depth='fast')
        self.assertEqual(queued['id'],duplicate['id'])
        run=self.repo.claim_run('alpha',queued['id']);token=run['lease_token']
        self.assertEqual(self.repo.charge_run('alpha',run['id'],'model-1',token)['remaining'],1)
        self.assertEqual(self.repo.charge_run('alpha',run['id'],'model-1',token)['remaining'],1)
        self.repo.charge_run('alpha',run['id'],'repair',token,repair=True)
        with self.assertRaises(BudgetExceeded):self.repo.charge_run('alpha',run['id'],'overflow',token)
        with self.repo.transaction('alpha') as c:c.execute(sql.SQL("UPDATE {} SET lease_until=now()-interval '1 second' WHERE id=%s").format(self.repo.table('core_runs')),(run['id'],))
        self.assertEqual(self.repo.recover_runs('alpha'),1)
        claimed=self.repo.claim_run('alpha',run['id'])
        self.assertEqual(claimed['calls'],2);self.assertEqual(claimed['attempts'],2)
        with self.assertRaises(LeaseConflict):self.repo.charge_run('alpha',run['id'],'old-worker',token)

    def test_atomic_stale_commit_and_minimal_checkpoint(self):
        source=self.source('我喜欢安静')
        fact=self.memory.save_fact('alpha','self',source['id'],source['content'])
        run=self.repo.begin_run('alpha','commit-operation',{'message_id':source['id']})
        token=run['lease_token'];versions=self.memory.snapshot('alpha')['versions']
        self.repo.set_run_dependencies('alpha',run['id'],versions,token)
        with self.assertRaises(ValueError):self.repo.checkpoint_run('alpha',run['id'],{'snapshot':{'content':'private'}},token)
        self.repo.checkpoint_run('alpha',run['id'],{'phase':'synthesis','ids':['synthetic-output-id'],'budget':{'calls':0}},token)
        self.memory.retire_fact('alpha',fact['id'],expected_revision=fact['revision'])
        with self.assertRaises((RevisionConflict,LeaseConflict)):self.repo.commit_run('alpha',run['id'],versions,{'schema_version':'core3.0','validation':{'status':'validated'}},token)
        self.assertIsNone(self.repo.fetch_run('alpha',run['id'])['result'])
        self.assertEqual(self.repo.fetch_run('alpha',run['id'])['checkpoint'],{})

    def test_shared_capacity_across_pools_and_owners_retains_queue(self):
        from threading import Barrier
        repositories=[PostgresRepository(test_dsn(),schema=self.schema,initialize=False,max_running=1) for _ in range(2)]
        for repository in repositories:self.addCleanup(repository.close)
        queued=[repositories[index].queue_run(owner,'capacity-'+owner,{'synthetic':owner}) for index,owner in enumerate(('alpha','beta'))]
        barrier=Barrier(2)
        def claim(index):
            owner=('alpha','beta')[index];barrier.wait()
            try:return repositories[index].claim_run(owner,queued[index]['id'])
            except LeaseConflict:return None
        with ThreadPoolExecutor(max_workers=2) as workers:claimed=list(workers.map(claim,range(2)))
        self.assertEqual(sum(run is not None for run in claimed),1)
        winner=next(index for index,run in enumerate(claimed) if run)
        loser=1-winner;owners=('alpha','beta');run=claimed[winner]
        waiting=repositories[loser].fetch_run(owners[loser],queued[loser]['id'])
        self.assertEqual((waiting['status'],waiting['attempts'],waiting['calls']),('queued',0,0))
        with self.assertRaises(LeaseConflict):repositories[winner].claim_run(owners[winner],run['id'])
        repositories[winner].set_run_dependencies(owners[winner],run['id'],{},run['lease_token'])
        succeeded=repositories[winner].commit_run(owners[winner],run['id'],{},
                    {'schema_version':'core3.0','validation':{'status':'validated'}},run['lease_token'])
        next_run=repositories[loser].claim_run(owners[loser],waiting['id'])
        self.assertEqual(next_run['status'],'running')
        self.assertEqual(repositories[winner].claim_run(owners[winner],succeeded['id'])['status'],'succeeded')

    def test_capacity_releases_expired_lease_without_resetting_budget(self):
        self.repo.max_running=1
        first=self.repo.begin_run('alpha','capacity-expired',{'synthetic':'expired'})
        self.repo.charge_run('alpha',first['id'],'capacity-charge',first['lease_token'])
        second=self.repo.queue_run('beta','capacity-next',{'synthetic':'next'})
        with self.assertRaises(LeaseConflict):self.repo.claim_run('beta',second['id'])
        with self.repo.transaction('alpha') as connection:
            connection.execute(sql.SQL("UPDATE {} SET lease_until=now()-interval '1 second' WHERE id=%s").format(self.repo.table('core_runs')),(first['id'],))
        next_run=self.repo.claim_run('beta',second['id'])
        with self.assertRaises(LeaseConflict):self.repo.renew_run('alpha',first['id'],first['lease_token'])
        self.repo.fail_run('beta',next_run['id'],'SYNTHETIC_END',next_run['lease_token'])
        recovered=self.repo.claim_run('alpha',first['id'])
        self.assertEqual((recovered['calls'],recovered['attempts']),(1,2))

    def test_concurrent_versions_only_one_mutation_commits(self):
        source=self.source('我喜欢早起')
        fact=self.memory.save_fact('alpha','self',source['id'],source['content'])
        def mutate(label):
            try:self.repo.update('alpha','fact',fact['id'],{'label':label},expected_revision=fact['revision']);return True
            except RevisionConflict:return False
        with ThreadPoolExecutor(max_workers=2) as workers:results=list(workers.map(mutate,['one','two']))
        self.assertEqual(sorted(results),[False,True])

    def test_retry_stale_epoch_preserves_effect_receipts_and_global_budget(self):
        source=self.source('本轮合成问题')
        run=self.repo.begin_run('alpha','retry-operation',{'message':source['content'],'source_message_id':source['id']})
        token=run['lease_token'];versions=self.memory.snapshot('alpha')['versions']
        self.repo.set_run_dependencies('alpha',run['id'],versions,token)
        for stage,output in [('intake',{'source_id':source['id'],'plan':{}}),('memory',{'receipts':[]}),('snapshot',{'private':'SYNTHETIC_STALE_OUTPUT'}),('model:synthesis',{'private':'SYNTHETIC_STALE_OUTPUT'})]:
            self.repo.put('alpha','runtime_step',run['id']+':e0:'+stage,{'run_id':run['id'],'stage':stage,'output':output},operation_id='step:'+run['id']+':e0:'+stage)
        self.repo.charge_run('alpha',run['id'],'repair-old',token,repair=True)
        self.repo.checkpoint_run('alpha',run['id'],{'phase':'validation','ids':[run['id']+':e0:validation']},token)
        self.repo.fail_run('alpha',run['id'],'SYNTHETIC_ERROR',token)
        global_source=self.source('我喜欢清晰回答')
        self.memory.save_fact('alpha','self',global_source['id'],global_source['content'])
        prepared=self.repo.prepare_retry('alpha',run['id'])
        self.assertTrue(prepared['purge_checkpoint'])
        retried=prepared['run'];self.assertEqual(retried['retry_epoch'],1)
        self.assertEqual(retried['calls'],1);self.assertTrue(retried['repair_used'])
        self.assertEqual(retried['checkpoint'],{});self.assertEqual(retried['state_version'],{})
        steps=self.repo.list('alpha','runtime_step')
        self.assertEqual({step['stage'] for step in steps},{'intake','memory'})
        self.assertNotIn('SYNTHETIC_STALE_OUTPUT',json.dumps(steps))
        claimed=self.repo.claim_run('alpha',run['id'])
        with self.assertRaises(BudgetExceeded):self.repo.charge_run('alpha',run['id'],'second-repair',claimed['lease_token'],repair=True)

    def test_fresh_failure_retry_keeps_epoch_and_cache_and_source_deletion_blocks(self):
        source=self.source('合成有效原话')
        run=self.repo.begin_run('alpha','retry-fresh',{'message':source['content'],'source_message_id':source['id']})
        token=run['lease_token']
        self.repo.set_run_dependencies('alpha',run['id'],self.memory.snapshot('alpha')['versions'],token)
        self.repo.put('alpha','runtime_step',run['id']+':e0:intake',{'run_id':run['id'],'stage':'intake','output':{'source_id':source['id']}})
        self.repo.checkpoint_run('alpha',run['id'],{'phase':'intake'},token)
        self.repo.fail_run('alpha',run['id'],'temporary',token)
        prepared=self.repo.prepare_retry('alpha',run['id'])
        self.assertFalse(prepared['purge_checkpoint']);self.assertEqual(prepared['run']['retry_epoch'],0)
        self.assertEqual(prepared['run']['checkpoint'],{'phase':'intake'})
        claimed=self.repo.claim_run('alpha',run['id'])
        self.repo.fail_run('alpha',run['id'],'temporary',claimed['lease_token'])
        self.repo.delete('alpha','message',source['id'],expected_revision=source['revision'])
        with self.assertRaises(EvidenceError):self.repo.prepare_retry('alpha',run['id'])

    def test_correction_stales_existing_run_and_explicit_withdrawal_stays_terminal(self):
        old_source=self.source('我不能上夜班')
        fact=self.memory.save_fact('alpha','self',old_source['id'],old_source['content'],'constraint')
        current=self.source('合成本轮询问')
        run=self.repo.begin_run('alpha','correction-stale-run',{'message':current['content'],'source_message_id':current['id']})
        self.repo.set_run_dependencies('alpha',run['id'],self.memory.snapshot('alpha')['versions'],run['lease_token'])
        self.repo.charge_run('alpha',run['id'],'model-before-correction',run['lease_token'])
        correction=self.source('更正：我现在可以上夜班')
        new=self.memory.correct_fact('alpha',fact['id'],correction['id'],correction['content'],expected_revision=fact['revision'])
        invalid=self.repo.fetch_run('alpha',run['id'])
        self.assertEqual(invalid['status'],'stale');self.assertEqual(invalid['request']['message'],current['content'])
        retried=self.repo.prepare_retry('alpha',run['id'])['run']
        self.assertEqual(retried['retry_epoch'],1);self.assertEqual(retried['calls'],1)
        self.repo.invalidate_derived('alpha',[],[current['id']])
        self.assertEqual(self.repo.fetch_run('alpha',run['id'])['status'],'revoked')
        self.repo.invalidate_derived('alpha',[fact['id']],[],recomputable=True)
        self.assertEqual(self.repo.fetch_run('alpha',run['id'])['status'],'revoked')

    def test_mutation_request_atomic_idempotence_and_no_private_receipt(self):
        source=self.source('我喜欢简短回答')
        fact=self.memory.save_fact('alpha','self',source['id'],source['content'])
        calls=[]
        def effect():
            calls.append(True)
            row=self.repo.update('alpha','fact',fact['id'],{'label':'synthetic'},expected_revision=fact['revision'])
            return {'id':row['id'],'revision':row['revision'],'status':'saved'}
        payload={'id':fact['id'],'text':'SYNTHETIC_PRIVATE_INTENT','expected_revision':fact['revision']}
        first=self.repo.mutation_request('alpha','memory-edit','stable-http-key',payload,effect)
        second=self.repo.mutation_request('alpha','memory-edit','stable-http-key',payload,effect)
        self.assertEqual(first,second);self.assertEqual(len(calls),1)
        with self.assertRaises(EvidenceError):self.repo.mutation_request('alpha','memory-edit','stable-http-key',dict(payload,text='different'),effect)
        with self.repo.connection() as c:
            rows=c.execute(sql.SQL('SELECT * FROM {}').format(self.repo.table('core_mutation_requests'))).fetchall()
        self.assertNotIn('SYNTHETIC_PRIVATE_INTENT',json.dumps(rows,default=str))
        before=self.repo.get('alpha','fact',fact['id'])
        def private_effect():
            self.repo.update('alpha','fact',fact['id'],{'label':'must-rollback'},expected_revision=before['revision'])
            return {'text':'private fact body'}
        with self.assertRaises(EvidenceError):self.repo.mutation_request('alpha','memory-edit','private-key',{},private_effect)
        self.assertEqual(self.repo.get('alpha','fact',fact['id'])['revision'],before['revision'])

    def test_versioned_schema_checksum_rejects_modified_applied_migration(self):
        self.repo.initialize()
        with self.repo.transaction() as c:
            c.execute('SET TRANSACTION READ ONLY')
            verified=self.repo.verify_schema()
            self.assertEqual(verified['version'],4)
        with self.repo.connection() as c:
            versions=c.execute(sql.SQL('SELECT version,checksum FROM {} ORDER BY version').format(self.repo.table('schema_migrations'))).fetchall()
            self.assertEqual([row['version'] for row in versions],[1,2,3,4])
            self.assertTrue(all(len(row['checksum'])==64 for row in versions))
            c.execute(sql.SQL('UPDATE {} SET checksum=%s WHERE version=1').format(self.repo.table('schema_migrations')),('synthetic-wrong-checksum',))
        with self.assertRaises(EvidenceError):self.repo.initialize()
        with self.assertRaises(EvidenceError):self.repo.verify_schema()
        self.assertEqual(self.repo.list('alpha','fact'),[])

    def test_media_delete_intent_commits_before_physical_cleanup_and_path_guard(self):
        import tempfile
        import hashlib
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'media';folder=root/hashlib.sha256(b'alpha').hexdigest()[:24]
            folder.mkdir(parents=True);image=folder/'synthetic.jpg';image.write_bytes(b'SYNTHETIC_IMAGE')
            outside=Path(directory)/'protected.jpg';outside.write_bytes(b'PROTECTED')
            source=self.source('我喜欢合成图片')
            fact=self.memory.save_fact('alpha','self',source['id'],source['content'])
            upload=self.repo.put('alpha','upload','upload:synthetic-media',{'path':str(image),'source_ids':[source['id']]})
            with patch.dict(os.environ,{'ZHIMING_MEDIA_PATH':str(root)}):
                with self.assertRaises(RuntimeError):
                    with self.repo.transaction('alpha'):
                        self.memory.retire_fact('alpha',fact['id'],expected_revision=fact['revision'],scope='source')
                        raise RuntimeError('synthetic outer transaction rollback')
                self.assertTrue(image.is_file())
                self.assertEqual(self.repo.get('alpha','upload',upload['id'])['status'],'active')
                self.assertEqual(self.repo.cleanup_media_deletions('alpha'),{'deleted':0,'failed':0})
                self.memory.retire_fact('alpha',fact['id'],expected_revision=fact['revision'],scope='source')
                self.assertTrue(image.is_file())
                self.assertNotIn('path',self.repo.get('alpha','upload',upload['id'],include_deleted=True))
                self.assertFalse(self.repo.enqueue_media_deletion('alpha',{'id':'outside','path':str(outside)}))
                self.assertEqual(self.repo.cleanup_media_deletions('alpha'),{'deleted':1,'failed':0})
                self.assertFalse(image.exists());self.assertEqual(outside.read_bytes(),b'PROTECTED')

    def test_unselected_case_cannot_be_written_corrected_or_retired(self):
        case=self.memory.create_case('alpha','self','合成独立事项')['id']
        source=self.source('我不能上夜班',cases=[case])
        fact=self.memory.save_fact('alpha','self',source['id'],source['content'],'constraint',case_id=case)
        unrelated=self.source('更正：我现在可以上夜班。删除我不能上夜班。')
        with self.assertRaises(ScopeError):self.memory.save_fact('alpha','self',unrelated['id'],'我现在可以上夜班','constraint',case_id=case)
        with self.assertRaises(ScopeError):self.memory.apply_proposal('alpha',unrelated['id'],{'quote':'更正：我现在可以上夜班','supersedes':fact['id']},'unselected-correction')
        with self.assertRaises(ScopeError):self.memory.retire_from_message('alpha',fact['id'],unrelated['id'],'unselected-retire')
        self.assertEqual(self.repo.get('alpha','fact',fact['id'])['status'],'active')

    def test_stale_before_completed_memory_discards_intake_for_budgeted_reparse(self):
        source=self.source('合成待处理问题')
        run=self.repo.begin_run('alpha','retry-before-memory',{'message':source['content'],'source_message_id':source['id']})
        self.repo.put('alpha','runtime_step',run['id']+':e0:intake',{'run_id':run['id'],'stage':'intake','output':{'source_id':source['id']}})
        self.repo.charge_run('alpha',run['id'],'original-intake-call',run['lease_token'])
        self.repo.fail_run('alpha',run['id'],'changed',run['lease_token'],status='stale')
        retried=self.repo.prepare_retry('alpha',run['id'])['run']
        self.assertEqual(retried['retry_epoch'],1);self.assertEqual(retried['calls'],1)
        self.assertEqual(self.repo.list('alpha','runtime_step'),[])

    def test_shared_source_projects_only_selected_case_quotes_into_history(self):
        cases=[self.memory.create_case('alpha','self',title)['id'] for title in ('合成A事项','合成C事项')]
        source=self.source('我不能参加夜间课程。我喜欢SYNTHETIC_UNSELECTED_C。其他SYNTHETIC_UNPARSED_C。',cases=cases)
        self.memory.save_fact('alpha','self',source['id'],'我不能参加夜间课程','constraint',case_id=cases[0])
        self.memory.save_fact('alpha','self',source['id'],'我喜欢SYNTHETIC_UNSELECTED_C','preference',case_id=cases[1])
        selected=self.memory.snapshot('alpha','self',[cases[0]])
        self.assertIn('我不能参加夜间课程',json.dumps(selected,ensure_ascii=False))
        self.assertNotIn('SYNTHETIC_UNSELECTED_C',json.dumps(selected))
        self.assertNotIn('SYNTHETIC_UNPARSED_C',json.dumps(selected))
        self.assertEqual(self.memory.get_source('alpha',source['id'])['content'],source['content'])

    def test_source_delete_clears_feedback_and_cached_profile_receipts(self):
        source=self.source('我喜欢SYNTHETIC_SOURCE_DERIVED')
        fact=self.memory.save_fact('alpha','self',source['id'],source['content'])
        self.repo.put('alpha','feedback','derived-feedback',{'content':'SYNTHETIC_SOURCE_DERIVED','source_refs':[{'message_id':source['id']}]})
        self.repo.put('alpha','request','profile-confirm-cache',{'result':{'receipts':[dict(fact,content='SYNTHETIC_SOURCE_DERIVED')]}})
        self.memory.retire_fact('alpha',fact['id'],expected_revision=fact['revision'],scope='source')
        for kind,ident in [('feedback','derived-feedback'),('request','profile-confirm-cache')]:
            row=self.repo.get('alpha',kind,ident,include_deleted=True)
            self.assertEqual(row['status'],'deleted');self.assertNotIn('SYNTHETIC_SOURCE_DERIVED',json.dumps(row))
        self.repo.apply_privacy('alpha',self.repo.export_privacy('alpha'))


if __name__=='__main__':unittest.main()
