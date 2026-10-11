"""Real PostgreSQL, LangGraph and business service; only provider is synthetic."""
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import uuid

from psycopg import sql
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.domain.contracts import ScopeError, BudgetExceeded
from tests.test_core_pg_channels import FixtureModel

ROOT = Path(__file__).resolve().parents[1]


class ProgrammableProvider(FixtureModel):
    def __init__(self, *, proposal=None, synthesis_failures=0, invalid_answer=False, malformed=False):
        super().__init__(); self.proposal=proposal; self.synthesis_failures=synthesis_failures
        self.invalid_answer=invalid_answer; self.malformed=malformed
        self.during_synthesis=None

    def generate(self, **kwargs):
        response=super().generate(**kwargs)
        purpose=kwargs['purpose']
        if purpose=='intake' and self.proposal is not None:
            response['output']['proposals']=[deepcopy(self.proposal)]
        if purpose=='synthesis':
            if self.during_synthesis:
                callback=self.during_synthesis; self.during_synthesis=None; callback()
            if self.synthesis_failures:
                self.synthesis_failures-=1; raise TimeoutError('synthetic provider unavailable')
        if purpose in ('synthesis','repair') and self.invalid_answer:
            response['output']['cited_fact_ids']=['invented-fact']
        if purpose=='intake' and self.malformed:
            response['output']['private_extra']='PRIVATE_CHECKPOINT_BODY_9371'
        return response


class CoreRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn=os.getenv('CORE_TEST_DSN')
        settings=ROOT.parent/'dev-environment.json'
        if not cls.dsn and settings.is_file(): cls.dsn=json.loads(settings.read_text())['dsn']
        if not cls.dsn: raise unittest.SkipTest('requires disposable PostgreSQL')

    def setUp(self):
        self.schema='test_runtime_'+uuid.uuid4().hex[:16]
        self.repo=PostgresRepository(self.dsn,schema=self.schema)
        self.repo.ensure_owner('alice'); self.repo.ensure_owner('bob')
        self.provider=ProgrammableProvider(); self.service=ConsultationService(self.repo,model=self.provider)

    def tearDown(self):
        # LangGraph tables are public on this disposable database; delete only
        # this test's known UUID threads, then only its verified temporary schema.
        with self.repo.transaction() as c:
            rows=c.execute(sql.SQL('SELECT id,retry_epoch FROM {}').format(self.repo.table('core_runs'))).fetchall()
        for row in rows:
            for epoch in range(row['retry_epoch']+1):self.service.runtime.purge(row['id'],epoch)
        assert self.schema.startswith('test_runtime_')
        with self.repo.transaction() as c:c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.repo.close()

    def consult(self, *, message='今天如何安排学习？', request_id=None, depth='fast', **kwargs):
        return asyncio.run(self.service.consult(owner='alice',message=message,request_id=request_id or uuid.uuid4().hex,depth=depth,**kwargs))

    def run_by_request(self, request_id):
        with self.repo.transaction('alice') as c:
            row=c.execute(sql.SQL('SELECT id FROM {} WHERE owner=%s AND operation_id=%s').format(self.repo.table('core_runs')),('alice',request_id)).fetchone()
        return self.repo.fetch_run('alice',row['id'])

    def resume_failed(self, run):
        prepared=self.repo.prepare_retry('alice',run['id'])
        if prepared['purge_checkpoint']:self.service.runtime.purge(run['id'],run.get('retry_epoch',0))
        return self.service.execute('alice',run['id'])

    def test_persistent_fast_standard_deep_limits_include_every_provider_call(self):
        for depth, limit in (('fast',2),('standard',6),('deep',10)):
            before=len(self.provider.requests)
            result=self.consult(depth=depth)
            run=self.repo.fetch_run('alice',result['meta']['core_run']['run_id'])
            self.assertEqual(run['call_limit'],limit)
            self.assertEqual(run['calls'],len(self.provider.requests)-before)
            self.assertLessEqual(run['calls'],limit)
            with self.repo.transaction('alice') as c:
                count=c.execute(sql.SQL('SELECT count(*) AS n FROM {} WHERE owner=%s AND run_id=%s').format(self.repo.table('core_model_charges')),('alice',run['id'])).fetchone()['n']
            self.assertEqual(count,run['calls'])

    def test_replayed_completed_request_reads_business_commit_without_new_charge(self):
        result=self.consult(request_id='replay-durable')
        self.assertEqual(self.consult(request_id='replay-durable'),result)
        self.assertEqual(len(self.provider.requests),2)

    def test_business_commit_survives_graph_checkpoint_crash(self):
        original=self.service.runtime.checkpointer.put
        injected=[]
        def put(config, checkpoint, metadata, new_versions):
            result=original(config,checkpoint,metadata,new_versions)
            if checkpoint.get('channel_values',{}).get('phase')=='commit' and not injected:
                injected.append(True); raise RuntimeError('synthetic after-commit checkpoint failure')
            return result
        with patch.object(self.service.runtime.checkpointer,'put',side_effect=put):
            result=self.consult(request_id='commit-before-checkpoint')
        self.assertEqual(injected,[True])
        self.assertEqual(self.run_by_request('commit-before-checkpoint')['status'],'succeeded')
        self.assertEqual(self.consult(request_id='commit-before-checkpoint'),result)
        self.assertEqual(len(self.provider.requests),2)

    def test_checkpoint_state_contains_identifiers_without_private_history(self):
        secret='PRIVATE_HISTORY_BODY_2036'
        result=self.consult(message=secret,request_id='private-state')
        run_id=result['meta']['core_run']['run_id']
        thread=run_id+':e0'
        checkpoint=self.service.runtime.checkpointer.get_tuple({'configurable':{'thread_id':thread}})
        self.assertIsNotNone(checkpoint)
        self.assertEqual(set(checkpoint.checkpoint['channel_values']),{'owner','run_id','phase'})
        self.assertNotIn(secret,repr(checkpoint))
        with self.repo.transaction() as c:
            rows=c.execute('SELECT blob FROM checkpoint_blobs WHERE thread_id=%s',(thread,)).fetchall()
        self.assertTrue(rows)
        self.assertFalse(any(secret.encode() in bytes(r['blob'] or b'') for r in rows))

    def test_malformed_provider_output_does_not_leak_private_body_into_checkpoint_error(self):
        self.provider.malformed=True
        with self.assertRaises(Exception): self.consult(request_id='bad-provider-contract')
        run=self.run_by_request('bad-provider-contract')
        with self.repo.transaction() as c:
            rows=c.execute('SELECT blob FROM checkpoint_writes WHERE thread_id=%s',(run['id']+':e0',)).fetchall()
        self.assertTrue(rows)
        self.assertFalse(any(b'PRIVATE_CHECKPOINT_BODY_9371' in bytes(r['blob'] or b'') for r in rows),
                         'LangGraph error checkpoint must not persist provider bodies')

    def test_service_ordinary_memory_has_program_receipt_and_is_recalled(self):
        self.provider.proposal={'quote':'我不能上夜班','category':'约束'}
        first=self.consult(message='我不能上夜班。今天怎样安排学习？',request_id='ordinary-save')
        self.assertTrue(any(r.get('write_status')=='saved' for r in first['memory_receipts']))
        self.provider.proposal=None
        second=self.consult(message='请根据之前的限制安排。',request_id='ordinary-recall')
        self.assertIn('我不能上夜班',json.dumps(self.provider.requests[-1]['payload'],ensure_ascii=False))
        self.assertTrue(second['cited_fact_ids'])

    def test_failed_provider_call_remains_charged_on_checkpoint_recovery(self):
        self.provider.synthesis_failures=1
        with self.assertRaises(TimeoutError):self.consult(request_id='recover-provider',depth='standard')
        failed=self.run_by_request('recover-provider')
        self.assertEqual(failed['calls'],2)
        result=self.resume_failed(failed)
        run=self.run_by_request('recover-provider')
        self.assertEqual(run['calls'],3)
        self.assertEqual(len(self.provider.requests),3)
        self.assertEqual(result['meta']['core_run']['run_id'],failed['id'])
        self.assertEqual(run['attempts'],2)

    def test_exhausted_fast_budget_cannot_restart_or_reset_call_count(self):
        self.provider.synthesis_failures=1
        with self.assertRaises(TimeoutError):self.consult(request_id='exhaust-fast',depth='fast')
        failed=self.run_by_request('exhaust-fast')
        with self.assertRaises(BudgetExceeded):self.repo.prepare_retry('alice',failed['id'])
        self.assertEqual(self.repo.fetch_run('alice',failed['id'])['calls'],2)
        self.assertEqual(len(self.provider.requests),2)

    def test_stale_retry_rebuilds_memory_context_and_preserves_budget(self):
        source=self.service.memory.receive('alice',content='我不能上夜班',source_id='before-stale')
        old=self.service.memory.save_fact('alice','self',source['id'],'我不能上夜班','constraint')
        new=[]
        def correct_during_model():
            correction=self.service.memory.receive('alice',content='更正：我现在可以上夜班',source_id='during-stale')
            new.append(self.service.memory.correct_fact('alice',old['id'],correction['id'],'更正：我现在可以上夜班',expected_revision=old['revision'],operation_id='correct-during-stale'))
        self.provider.during_synthesis=correct_during_model
        with self.assertRaises(Exception):self.consult(request_id='stale-memory',depth='standard')
        failed=self.run_by_request('stale-memory')
        self.assertIn(failed['status'],('stale','failed'))
        before=failed['calls']; result=self.resume_failed(failed)
        run=self.run_by_request('stale-memory')
        self.assertEqual(run['retry_epoch'],1)
        self.assertGreater(run['calls'],before);self.assertEqual(run['calls'],len(self.provider.requests))
        facts=self.provider.requests[-1]['payload']['reference_data']['facts']
        self.assertNotIn(old['id'],{f['id'] for f in facts})
        self.assertIn(new[0]['id'],{f['id'] for f in facts})
        self.assertNotIn(old['id'],result['cited_fact_ids'])
        self.assertIsNone(self.service.runtime.checkpointer.get_tuple({'configurable':{'thread_id':run['id']+':e0'}}))

    def test_explicit_no_save_and_third_person_proposals_do_not_become_self_facts(self):
        for index,(message,quote) in enumerate((('不要记住这件事，我喜欢深夜学习。','我喜欢深夜学习'),
                                                ('朋友喜欢深夜学习，我只是在转述。','朋友喜欢深夜学习'))):
            self.provider.proposal={'quote':quote,'category':'偏好'}
            result=self.consult(message=message,request_id='negative-memory-'+str(index))
            self.assertTrue(result['memory_receipts'])
            self.assertFalse(any(r.get('write_status')=='saved' for r in result['memory_receipts']))
        self.assertEqual(self.service.memory.facts('alice'),[])

    def test_selected_case_and_owner_scope_precede_every_provider_call(self):
        foreign=self.service.memory.create_case('bob','self','Bob private',operation_id='foreign-case')
        self.repo.create_subject('alice','friend','合成第三人')
        other=self.service.memory.create_case('alice','friend','第三人事项',operation_id='third-case')
        for case in (foreign,other):
            with self.assertRaises(ScopeError): self.consult(case_ids=[case['id']])
        self.assertEqual(self.provider.requests,[])

    def test_selected_cases_filter_saved_context_and_old_predictions_are_not_facts(self):
        a=self.service.memory.create_case('alice','self','事项A',operation_id='case-a')
        b=self.service.memory.create_case('alice','self','事项B',operation_id='case-b')
        for case,quote in ((a,'我不能上夜班'),(b,'我不能接受额外费用')):
            source=self.service.memory.receive('alice',content=quote,source_id='source-'+case['id'],case_ids=[case['id']])
            self.service.memory.save_fact('alice','self',source['id'],quote,'constraint',case_id=case['id'])
        self.service.memory.receive('alice',content='旧助手预测：今年必定成功。',source_id='old-prediction',role='assistant',case_ids=[a['id']])
        result=self.consult(case_ids=[a['id']])
        facts=self.provider.requests[-1]['payload']['reference_data']['facts']
        self.assertEqual({f['content'] for f in facts},{'我不能上夜班'})
        self.assertTrue(all(f['assertion_status']=='user_asserted' for f in facts))
        self.assertTrue(result['cited_fact_ids'])


if __name__=='__main__': unittest.main()
