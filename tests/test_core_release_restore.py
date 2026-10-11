"""Real PG final-DM migration and older-backup withdrawal replay; no sends."""
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid

from psycopg import sql
import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.deploy_core import snapshot_sqlite,sync_frozen_hermes,export_withdrawals,apply_withdrawals,file_sha
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.application.memory import MemoryService
from mingjing_core.adapters.tarot import TarotService,IdempotencyConflict
from mingjing_core.adapters.delivery import OutboxService,DeliveryUncertain
from mingjing_core.domain.contracts import ScopeError,EvidenceError,LeaseConflict
from mingjing_core.runtime import LangGraphRuntime


class CoreReleaseRestore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn=os.environ.get('CORE_TEST_DSN')
        path=ROOT.parent/'dev-environment.json'
        if not cls.dsn and path.is_file():cls.dsn=json.loads(path.read_text(encoding='utf-8'))['dsn']
        if not cls.dsn:raise unittest.SkipTest('requires disposable PostgreSQL CORE_TEST_DSN')

    def setUp(self):
        self.schema='test_release_restore_'+uuid.uuid4().hex[:16]
        self.repo=PostgresRepository(self.dsn,schema=self.schema,max_size=4)
        self.repo.ensure_owner('alpha');self.memory=MemoryService(self.repo);self.tarot=TarotService(self.repo)
        self.repo.bind_channel('alpha','feishu','ou_synthetic_alpha')
        self.temporary=tempfile.TemporaryDirectory();self.folder=Path(self.temporary.name)

    def tearDown(self):
        assert self.schema.startswith('test_release_restore_')
        with self.repo.transaction() as c:c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.repo.close();self.temporary.cleanup()

    def test_final_hermes_backup_imports_only_bound_active_dm_originals_and_replays(self):
        source=self.folder/'state.db';backup=self.folder/'hermes-state.db'
        with closing(sqlite3.connect(source)) as c,c:
            c.execute('CREATE TABLE sessions(id text,source text,user_id text,chat_id text,chat_type text)')
            c.execute('CREATE TABLE messages(id text,session_id text,role text,content text,timestamp real,active integer)')
            c.executemany('INSERT INTO sessions VALUES(?,?,?,?,?)',[
                ('trusted','feishu','ou_synthetic_alpha','oc_dm','dm'),
                ('foreign','feishu','ou_other','oc_other','dm'),
                ('group','feishu','ou_synthetic_alpha','oc_group','group')])
            c.executemany('INSERT INTO messages VALUES(?,?,?,?,?,?)',[
                ('one','trusted','user','SYNTHETIC_FINAL_DM_ONE',1700000000,1),
                ('two','trusted','user','SYNTHETIC_FINAL_DM_TWO',1700000001,1),
                ('assistant','trusted','assistant','NON_ORIGINAL',1700000002,1),
                ('inactive','trusted','user','INACTIVE',1700000003,0),
                ('foreign','foreign','user','FOREIGN',1700000004,1),
                ('group','group','user','GROUP',1700000005,1)])
        digest=snapshot_sqlite(source,backup)
        bindings=[{'owner':'alpha','subject':'self','channel':'feishu','external_id':'ou_synthetic_alpha','binding_kind':'user'}]
        first=sync_frozen_hermes(self.repo,backup,bindings,owner='alpha')
        self.assertEqual(first['added_originals'],2);self.assertEqual(first['matched_originals'],2)
        self.assertEqual(first['repeat_added'],0);self.assertEqual(first['facts_created'],0)
        self.assertEqual(sync_frozen_hermes(self.repo,backup,bindings,owner='alpha')['added_originals'],0)
        self.assertEqual(file_sha(backup),digest)
        originals=self.repo.list('alpha','message')
        self.assertEqual({row['content'] for row in originals},{'SYNTHETIC_FINAL_DM_ONE','SYNTHETIC_FINAL_DM_TWO'})
        self.assertFalse(self.memory.facts('alpha'))
        self.repo.delete('alpha','message',originals[0]['id'],expected_revision=originals[0]['revision'])
        self.assertEqual(sync_frozen_hermes(self.repo,backup,bindings,owner='alpha')['added_originals'],0)
        self.assertEqual(len(self.repo.list('alpha','message')),1)

    def pg_tool(self,name,*args):
        binary=shutil.which(name)
        if not binary:
            local=ROOT.parent/'postgres/pgsql/bin'/(name+'.exe')
            if local.is_file():binary=str(local)
        self.assertTrue(binary,'Real PostgreSQL backup tools are required for restore acceptance')
        env=dict(os.environ)
        with psycopg.connect(self.dsn) as c:fields=dict(c.info.get_parameters())
        fields.update(conninfo_to_dict(self.dsn))
        for key,label in {'host':'PGHOST','hostaddr':'PGHOSTADDR','port':'PGPORT','user':'PGUSER','password':'PGPASSWORD','dbname':'PGDATABASE','options':'PGOPTIONS','sslmode':'PGSSLMODE'}.items():
            if key in fields:env[label]=str(fields[key])
        result=subprocess.run([binary,*args],env=env,stdin=subprocess.DEVNULL,capture_output=True,timeout=60)
        self.assertEqual(result.returncode,0,'PostgreSQL backup/restore failed; diagnostic withheld')

    def test_older_backup_replay_erases_direct_draw_ids_context_checkpoints_and_protects_receipts(self):
        marker='SYNTHETIC_WITHDRAWAL_PRIVATE_271'
        source=self.memory.receive('alpha','self','我喜欢'+marker,source_id='source1')
        fact=self.memory.save_fact('alpha','self',source['id'],source['content'])
        case=self.memory.create_case('alpha','self','合成事项',operation_id='case')
        args={'subject_id':'self','case_id':case['id'],'question':marker,'context_snapshot':{'fact_ids':[fact['id']],'source_ids':[source['id']],'background':marker}}
        first=self.tarot.create_draw('alpha',idempotency_key='draw1',**args)['draw']
        second=self.tarot.create_draw('alpha',idempotency_key='draw2',explicit_new=True,**args)['draw']
        for position in (1,2,3):self.tarot.reveal('alpha',first['id'],position)
        reading=self.tarot.begin_reading('alpha',first['id'],model='synthetic',prompt_version='core3.0',context_snapshot={'private':marker},idempotency_key='reading1')['reading']
        run=self.repo.queue_run('alpha','synthetic-restored-run',{'draw_id':first['id'],'reading_id':reading['id'],'case_ids':[case['id']]},subject='self',case_ids=[case['id']],depth='fast')
        runtime=LangGraphRuntime(self.repo)
        config={'configurable':{'thread_id':run['id']+':e0','checkpoint_ns':''}}
        checkpoint={'v':1,'id':str(uuid.uuid4()),'ts':datetime.now(timezone.utc).isoformat(),
                    'channel_values':{'private':marker},'channel_versions':{'private':'1'},'versions_seen':{}}
        runtime.checkpointer.put(config,checkpoint,{}, {'private':'1'})
        self.assertIsNotNone(runtime.checkpointer.get_tuple(config))
        now=datetime.now(timezone.utc)
        with self.repo.transaction('alpha') as c:
            for ident in ('sent-ledger','uncertain-ledger'):
                c.execute(sql.SQL("INSERT INTO {}(id,owner,subject,business_id,channel,target,run_id,payload,dependencies,status,due) VALUES(%s,'alpha','self',%s,'feishu','ou_synthetic_alpha',%s,%s,'{{}}','pending',%s)").format(self.repo.table('delivery_outbox')),(ident,ident,run['id'],Jsonb({'private':marker}),now))
        archive=self.folder/'older-synthetic-schema.dump'
        self.pg_tool('pg_dump','--format=custom','--schema='+self.schema,'--no-owner','--no-acl','--file='+str(archive))
        archive.chmod(0o600)
        self.memory.retire_fact('alpha',fact['id'],expected_revision=fact['revision'],scope='source')
        self.tarot.delete('alpha',first['id'])  # Historical tombstone has no retained draw ID.
        self.repo.mutation_request('alpha','tarot-delete:'+second['id'],'delete2',{},lambda:self.tarot.delete('alpha',second['id']))
        with self.repo.transaction('alpha') as c:
            c.execute(sql.SQL("UPDATE {} SET status='sent',receipt='om_synthetic_receipt',attempts=1 WHERE id='sent-ledger'").format(self.repo.table('delivery_outbox')))
            c.execute(sql.SQL("UPDATE {} SET status='sending',attempts=1 WHERE id='uncertain-ledger'").format(self.repo.table('delivery_outbox')))
        latest=export_withdrawals(self.repo)
        self.assertNotIn(marker,json.dumps(latest));self.assertEqual(latest['owners'][0]['schema_version'],'core3.0')
        self.assertEqual(len(latest['tarot_requests']),3);self.assertEqual(latest['deleted_draws'],[{'owner':'alpha','draw_id':second['id']}])
        self.repo.close()
        assert self.schema.startswith('test_release_restore_')
        with psycopg.connect(self.dsn,autocommit=True) as c:c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.pg_tool('pg_restore','--dbname=','--exit-on-error','--single-transaction','--no-owner','--no-acl',str(archive))
        self.repo=PostgresRepository(self.dsn,schema=self.schema,initialize=False,max_size=4)
        self.repo.verify_schema();self.memory=MemoryService(self.repo);self.tarot=TarotService(self.repo)
        runtime=LangGraphRuntime(self.repo,initialize=False)
        self.assertEqual(self.tarot.get('alpha',first['id'])['question'],marker)
        result=apply_withdrawals(self.repo,latest)
        self.assertEqual(result['deleted_draws'],2)
        for draw in (first,second):
            with self.assertRaises(KeyError):self.tarot.get('alpha',draw['id'])
        with self.assertRaises(EvidenceError):self.memory.receive('alpha','self','我喜欢'+marker,source_id='source1')
        self.assertFalse(self.memory.facts('alpha'));self.assertEqual(self.repo.fetch_run('alpha',run['id'])['status'],'revoked')
        with self.assertRaises(KeyError):self.tarot.get_reading('alpha',reading['id'])
        self.assertIsNone(runtime.checkpointer.get_tuple(config))
        outbox=OutboxService(self.repo)
        self.assertEqual(outbox.business_status('alpha','sent-ledger')[0]['status'],'sent')
        self.assertEqual(outbox.business_status('alpha','uncertain-ledger')[0]['status'],'uncertain')
        with self.assertRaises(LeaseConflict):outbox.claim_delivery(owner='alpha',outbox_id='sent-ledger')
        with self.assertRaises(DeliveryUncertain):outbox.claim_delivery(owner='alpha',outbox_id='uncertain-ledger')
        for key in ('draw1','draw2'):
            with self.assertRaises(IdempotencyConflict):self.tarot.create_draw('alpha',idempotency_key=key,explicit_new=key=='draw2',**args)
        again=apply_withdrawals(self.repo,latest)
        self.assertEqual(again['deleted_draws'],0);self.assertEqual(again['protected_receipts'],1)
        with self.repo.connection() as c:
            for table,column in [('core_runs','request'),('core_runs','result'),('core_runs','checkpoint'),('delivery_outbox','payload'),('tarot_draws','private_deck')]:
                rows=c.execute(sql.SQL('SELECT {} FROM {} WHERE owner=%s').format(sql.Identifier(column),self.repo.table(table)),('alpha',)).fetchall()
                self.assertNotIn(marker,json.dumps(rows,default=str))

    def test_mismatched_tarot_request_blocks_the_whole_restore_replay(self):
        case=self.memory.create_case('alpha','self','合成事项',operation_id='case')
        self.tarot.create_draw('alpha',subject_id='self',case_id=case['id'],question='原始合成问题',idempotency_key='key')
        document={'schema':'core3-withdrawals-v2','owners':[self.repo.export_privacy('alpha')],
                  'tarot_requests':[{'owner':'alpha','operation':'create','request_key':'key','fingerprint':'0'*64,'result_type':'draw'}],
                  'deleted_draws':[],'delivery_receipts':[]}
        before=len(self.tarot.list_draws('alpha'))
        with self.assertRaisesRegex(ValueError,'differs'):apply_withdrawals(self.repo,document)
        self.assertEqual(len(self.tarot.list_draws('alpha')),before)


if __name__=='__main__':unittest.main()
