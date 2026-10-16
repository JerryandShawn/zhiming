"""Stage acceptance helpers run against isolated PostgreSQL schemas."""
import hashlib
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
import test_core_memory_migration as fixture
from test_core_memory import test_dsn
from tools import verify_core_stage as verifier


class StageAcceptanceHelperTests(unittest.TestCase):
    setUp=fixture.CoreMigrationPostgresTests.setUp
    cleanup=fixture.CoreMigrationPostgresTests.cleanup

    def test_migration_acceptance_checks_union_profile_and_body_free_sent_ledger(self):
        (self.source/'webchat.json').write_text(json.dumps([{'id':'older-json-only','role':'user','content':'合成旧记录。'}]),encoding='utf-8')
        jobs=[{'id':'synthetic-'+kind,'kind':'daily','target':'oc_syntheticPrivate'} for kind in ('sent','uncertain')]
        (self.source/'report-pipeline.json').write_text(json.dumps({'enabled':True,'jobs':jobs}),encoding='utf-8')
        connection=sqlite3.connect(self.source/'reports.db')
        try:
            connection.execute('CREATE TABLE outbox(id TEXT,kind TEXT,date TEXT,due TEXT,job_id TEXT,status TEXT,content TEXT,attempts INTEGER,first_send REAL,message_id TEXT)')
            connection.executemany('INSERT INTO outbox VALUES(?,?,?,?,?,?,?,?,?,?)',[
                ('sent','daily','2026-01-01','2026-01-01T07:00:00+08:00','synthetic-sent','sent','SYNTHETIC_OLD_REPORT_BODY',1,123,'om_syntheticReceipt'),
                ('uncertain','daily','2026-01-01','2026-01-01T07:00:00+08:00','synthetic-uncertain','retrying','SYNTHETIC_OLD_REPORT_BODY',1,123,'')]);connection.commit()
        finally:connection.close()
        result=verifier.verify_import(self.repo,self.source,'migration-owner',[])
        self.assertEqual(result['dry_run']['json_only_messages'],1)
        self.assertEqual(result['protected_delivery_rows'],2)
        self.assertEqual(result['legacy_delivery_statuses'],{'sent':1,'uncertain':1})
        self.assertTrue(result['legacy_profile_unverified'])
        self.assertNotIn('SYNTHETIC_OLD_REPORT_BODY',json.dumps(result))
        self.assertEqual(result['repeat']['imported_messages'],0)

    def test_latest_privacy_ledger_blocks_simulated_older_backup(self):
        result=verifier.verify_privacy_restore(test_dsn())
        self.assertTrue(all(result.values()))

    def test_hermes_snapshot_only_exact_active_dm_author_and_no_fact_extraction(self):
        snapshot=self.source/'hermes-backup.db'
        connection=sqlite3.connect(snapshot)
        try:
            connection.executescript('CREATE TABLE sessions(id TEXT,source TEXT,user_id TEXT,chat_id TEXT,chat_type TEXT);CREATE TABLE messages(id TEXT,session_id TEXT,role TEXT,content TEXT,timestamp REAL,active INTEGER);')
            connection.executemany('INSERT INTO sessions VALUES(?,?,?,?,?)',[
                ('own','feishu','ou_syntheticTrusted','oc_syntheticOwn','dm'),
                ('other','feishu','ou_syntheticOther','oc_syntheticOther','dm'),
                ('group','feishu','ou_syntheticTrusted','oc_syntheticGroup','group')])
            connection.executemany('INSERT INTO messages VALUES(?,?,?,?,?,?)',[
                ('own-message','own','user','我喜欢合成清晨学习',1791660000,1),
                ('withdrawn','own','user','SYNTHETIC_WITHDRAWN_HERMES',1791660001,1),
                ('other-message','other','user','SYNTHETIC_OTHER_AUTHOR',1791660002,1),
                ('group-message','group','user','SYNTHETIC_GROUP_BODY',1791660003,1),
                ('inactive','own','user','SYNTHETIC_INACTIVE_BODY',1791660004,0),
                ('assistant','own','assistant','SYNTHETIC_ASSISTANT_BODY',1791660005,1)]);connection.commit()
        finally:connection.close()
        snapshot.chmod(0o600)
        self.repo.bind_channel('migration-owner','feishu','ou_syntheticTrusted')
        old=self.memory.receive('migration-owner','self','SYNTHETIC_WITHDRAWN_HERMES',source_id='withdrawn:user',channel='feishu',external_id='ou_syntheticTrusted')
        self.repo.delete('migration-owner','message',old['id'],expected_revision=old['revision'])
        digest=hashlib.sha256(snapshot.read_bytes()).hexdigest()
        with patch.object(verifier,'HERMES_BACKUPS',self.source):
            result=verifier.verify_hermes(self.repo,snapshot,digest,'migration-owner',[{'channel':'feishu','external_id':'ou_syntheticTrusted','binding_kind':'user'}])
        self.assertEqual((result['imported'],result['skipped'],result['actual_postgres_added'],result['repeat_postgres_added']),(1,1,1,0))
        self.assertEqual(self.memory.facts('migration-owner'),[])
        self.assertEqual([row['content'] for row in self.memory.sources('migration-owner')],['我喜欢合成清晨学习'])
        self.assertEqual(hashlib.sha256(snapshot.read_bytes()).hexdigest(),digest)

    def test_bindings_path_and_owner_require_explicit_trusted_file(self):
        path=self.source/'bindings.json';path.write_text('[{"owner":"other","subject":"self","channel":"feishu","external_id":"ou_synthetic","binding_kind":"user"}]')
        path.chmod(0o600)
        with self.assertRaises(verifier.StageFailure):verifier.checked_bindings(path,'migration-owner')
        with self.assertRaises(verifier.StageFailure):verifier.checked_bindings(self.source/'missing.json','migration-owner')


if __name__=='__main__':unittest.main()
