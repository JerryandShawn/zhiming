"""Legacy SQLite is input only; every migration target is real PostgreSQL."""
import json
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path
from psycopg import sql
from test_core_memory import test_dsn
from migration_core import migrate
from mingjing_core.application.memory import MemoryService
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.domain.contracts import ScopeError


def source_hashes(directory):
    import hashlib
    return {str(path.relative_to(directory)):hashlib.sha256(path.read_bytes()).hexdigest()
            for path in directory.rglob('*') if path.is_file()}


class CoreMigrationPostgresTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.source=Path(self.directory.name)
        self.schema='test_migration_'+uuid.uuid4().hex[:20]
        self.repo=PostgresRepository(test_dsn(),schema=self.schema);self.addCleanup(self.cleanup)
        self.memory=MemoryService(self.repo)
        self.repo.ensure_owner('migration-owner')
        c=sqlite3.connect(self.source/'web.db')
        try:
            c.executescript('CREATE TABLE turns(id TEXT,session_id TEXT,message TEXT,answer TEXT,status TEXT,created_at TEXT); CREATE TABLE memories(id TEXT,text TEXT,quote TEXT,category TEXT,source_turn TEXT,status TEXT);')
            c.executemany('INSERT INTO turns VALUES(?,?,?,?,?,?)',[
                ('turn-a','shared','我喜欢早起。我喜欢周末徒步。','合成助手回答','complete','2026-01-01T00:00:00+00:00'),
                ('turn-b','shared','我喜欢SYNTHETIC_STOPPED_981。','','complete','2026-01-02T00:00:00+00:00')])
            c.executemany('INSERT INTO memories VALUES(?,?,?,?,?,?)',[
                ('fact-a','我喜欢早起','我喜欢早起','偏好','turn-a','active'),
                ('fact-b','我喜欢周末徒步','我喜欢周末徒步','偏好','turn-a','active'),
                ('fact-hidden','我喜欢SYNTHETIC_STOPPED_981','我喜欢SYNTHETIC_STOPPED_981','偏好','turn-b','hidden'),
                ('no-source','助手认为未来会升职','助手认为未来会升职','背景','missing','active')])
            c.commit()
        finally:c.close()
        (self.source/'archive.json').write_text(json.dumps({'user':{'birth':{'solar_datetime':'2000-01-01 12:00'}},'conversation_state':{'user_facts':[{'id':'fact-hidden','text':'我喜欢SYNTHETIC_STOPPED_981','quote':'我喜欢SYNTHETIC_STOPPED_981','status':'active','category':'偏好','source_turn':'turn-b'}]}}),encoding='utf-8')

    def cleanup(self):
        with self.repo.pool.connection() as c:c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.repo.close()

    def test_dry_run_readonly_and_repeated_apply_with_withdrawal_first(self):
        original=(self.source/'web.db').read_bytes()
        before=source_hashes(self.source)
        dry=migrate(self.source,'migration-owner')
        self.assertTrue(dry['dry_run']);self.assertEqual(dry['inactive_first'],1)
        self.assertEqual(self.repo.list('migration-owner','message'),[])
        first=migrate(self.source,'migration-owner',repository=self.repo,apply=True)
        self.assertEqual(first['errors'],[]);self.assertEqual(first['verified_facts'],2)
        facts=self.memory.snapshot('migration-owner')['facts']
        self.assertEqual({f['content'] for f in facts},{'我喜欢早起','我喜欢周末徒步'})
        self.assertNotIn('SYNTHETIC_STOPPED_981',json.dumps(self.memory.snapshot('migration-owner'),ensure_ascii=False))
        self.assertEqual(self.memory.snapshot('migration-owner')['profile'],{})
        second=migrate(self.source,'migration-owner',repository=self.repo,apply=True)
        self.assertEqual(second['verified_facts'],0);self.assertEqual(second['imported_messages'],0)
        self.assertEqual((self.source/'web.db').read_bytes(),original)
        self.assertEqual(source_hashes(self.source),before)
        self.assertEqual(second['source_messages'],first['source_messages'])
        self.assertEqual(second['source_memories'],first['source_memories'])
        self.assertEqual(len(self.repo.list('migration-owner','legacy')),3)

    def test_source_delete_purges_legacy_reply_and_its_dependent_run(self):
        migrate(self.source,'migration-owner',repository=self.repo,apply=True)
        reply=next(message for message in self.memory.sources('migration-owner') if message.get('role')=='assistant')
        fact=next(fact for fact in self.memory.facts('migration-owner') if fact.get('content')=='我喜欢早起')
        source_id=fact['source_refs'][0]['message_id']
        self.assertEqual(reply['source_ids'],[source_id])
        run=self.repo.begin_run('migration-owner','legacy-reply-reader',{'synthetic':'legacy history'})
        self.repo.set_run_dependencies('migration-owner',run['id'],{'message:'+reply['id']:reply['revision']},run['lease_token'])
        self.memory.retire_fact('migration-owner',fact['id'],expected_revision=fact['revision'],scope='source')
        self.assertEqual(self.repo.fetch_run('migration-owner',run['id'])['status'],'revoked')
        deleted=self.memory.get_source('migration-owner',reply['id'])
        self.assertEqual((deleted['status'],deleted['content']),('deleted',''))
        self.assertTrue(self.repo.is_revoked('migration-owner','message',reply['id']))
        repeated=migrate(self.source,'migration-owner',repository=self.repo,apply=True)
        self.assertEqual(repeated['errors'],[])
        self.assertNotIn(reply['id'],[message['id'] for message in self.memory.sources('migration-owner')])

    def test_images_and_legacy_sections_keep_safe_readonly_references(self):
        from PIL import Image
        import hashlib
        import io
        buf=io.BytesIO();Image.new('RGB',(2,2),(255,255,255)).save(buf,format='JPEG')
        raw=buf.getvalue();ident=hashlib.sha256(raw).hexdigest()
        (self.source/'images').mkdir();(self.source/'images'/(ident+'.jpg')).write_bytes(raw)
        c=sqlite3.connect(self.source/'web.db')
        try:
            c.execute('ALTER TABLE turns ADD COLUMN images TEXT')
            c.execute('UPDATE turns SET images=? WHERE id=?',(json.dumps([ident]),'turn-a'));c.commit()
        finally:c.close()
        archive=json.loads((self.source/'archive.json').read_text())
        archive.update({'graph':{'persons':[]},'forecast_registry':[{'id':'synthetic-prediction'}],'dimension_stats':{},'omen_dictionary':[],'calibration':{},'reports':[]})
        (self.source/'archive.json').write_text(json.dumps(archive),encoding='utf-8')
        before=source_hashes(self.source)
        first=migrate(self.source,'migration-owner',repository=self.repo,apply=True)
        self.assertEqual(first['errors'],[]);self.assertEqual(first['imported_uploads'],1)
        upload=self.repo.list('migration-owner','upload')[0]
        self.assertEqual(Path(upload['path']).resolve().parent,(self.source/'images').resolve())
        message=self.repo.get('migration-owner','message',upload['message_id'])
        self.assertEqual(message['image_ids'],[upload['id']])
        sections={row.get('section') for row in self.repo.list('migration-owner','legacy')}
        self.assertTrue({'graph','forecast_registry','dimension_stats','omen_dictionary','calibration','reports'}<=sections)
        self.assertEqual((self.source/'images'/(ident+'.jpg')).read_bytes(),raw)
        second=migrate(self.source,'migration-owner',repository=self.repo,apply=True)
        self.assertEqual(second['imported_uploads'],0)
        self.assertEqual(len(self.repo.list('migration-owner','upload')),1)
        self.assertEqual(source_hashes(self.source),before)

    def test_foreign_binding_rejected_before_originals_or_facts_imported(self):
        self.repo.ensure_owner('foreign-owner')
        self.repo.bind_channel('foreign-owner','feishu','ou_syntheticForeign')
        before=source_hashes(self.source)
        with self.assertRaises(ScopeError):
            migrate(self.source,'migration-owner',repository=self.repo,apply=True,
                    bindings=[{'channel':'feishu','external_id':'ou_syntheticForeign'}])
        self.assertEqual(self.repo.list('migration-owner','message'),[])
        self.assertEqual(self.repo.list('migration-owner','fact'),[])
        self.assertEqual(self.repo.resolve_channel('feishu','ou_syntheticForeign')['owner'],'foreign-owner')
        self.assertEqual(source_hashes(self.source),before)

    def test_dry_run_shadow_reads_never_writes_source_or_core(self):
        from unittest.mock import patch
        real_connect=sqlite3.connect
        opened=[]
        def readonly_connect(database,*args,**kwargs):
            self.assertTrue(kwargs.get('uri'))
            self.assertTrue(database.endswith('?mode=ro'))
            connection=real_connect(database,*args,**kwargs)
            opened.append(connection)
            return connection
        before=source_hashes(self.source)
        revision=self.repo.get_revision('migration-owner')
        with patch('migration_core.sqlite3.connect',side_effect=readonly_connect):
            report=migrate(self.source,'migration-owner',repository=self.repo,apply=False)
        self.assertEqual(report['imported_messages'],0)
        self.assertEqual(report['verified_facts'],0)
        self.assertEqual(self.repo.get_revision('migration-owner'),revision)
        self.assertEqual(source_hashes(self.source),before)
        self.assertEqual(len(opened),3)

    def test_history_union_sqlite_priority_settings_and_pending_requests(self):
        (self.source/'webchat.json').write_text(json.dumps([
            {'turn_id':'turn-a','role':'user','content':'旧的冲突副本'},
            {'turn_id':'json-only-old','role':'user','content':'仅JSON保留的旧问题'},
            {'turn_id':'json-only-old','role':'assistant','content':'仅JSON保留的旧答复'}]),encoding='utf-8')
        c=sqlite3.connect(self.source/'web.db')
        try:
            c.executescript('CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT);')
            c.execute("INSERT INTO settings VALUES('auto_save_low_sensitivity','false')")
            c.execute("INSERT INTO turns VALUES('pending-web','shared','合成未完成问题','','running','2026-01-03T00:00:00+00:00')")
            c.execute("INSERT INTO turns VALUES('interrupted-web','shared','合成需要用户重试的问题','','interrupted','2026-01-03T00:00:00+00:00')")
            c.commit()
        finally:c.close()
        first=migrate(self.source,'migration-owner',repository=self.repo,apply=True)
        self.assertEqual(first['errors'],[]);self.assertEqual(first['json_only_messages'],2)
        self.assertEqual(first['json_sqlite_conflicts'],1)
        originals=self.repo.list('migration-owner','message')
        self.assertIn('仅JSON保留的旧问题',{row.get('content') for row in originals})
        self.assertNotIn('旧的冲突副本',{row.get('content') for row in originals})
        self.assertFalse(self.repo.assert_scope('migration-owner')['settings']['auto_save_low_sensitivity'])
        self.assertEqual(first['queued_legacy_runs'],1);self.assertEqual(first['legacy_pending_requests'],1)
        second=migrate(self.source,'migration-owner',repository=self.repo,apply=True)
        self.assertEqual(second['queued_legacy_runs'],0);self.assertEqual(second['legacy_pending_requests'],0)
        self.assertEqual(len(self.repo.queued_runs('migration-owner')),1)
        self.assertTrue(first['source_unchanged']);self.assertEqual(first['source_sha256'],second['source_sha256'])

    def test_source_identity_change_is_reported_and_does_not_replace_original(self):
        migrate(self.source,'migration-owner',repository=self.repo,apply=True)
        before={row['id']:row.get('content') for row in self.repo.list('migration-owner','message')}
        c=sqlite3.connect(self.source/'web.db')
        try:c.execute("UPDATE turns SET message='后来的冲突副本' WHERE id='turn-a'");c.commit()
        finally:c.close()
        changed=migrate(self.source,'migration-owner',repository=self.repo,apply=True)
        self.assertIn('SOURCE_IDENTITY_CONFLICT',{row['code'] for row in changed['errors']})
        self.assertEqual(before,{row['id']:row.get('content') for row in self.repo.list('migration-owner','message')})

    def test_changed_source_during_import_rolls_back_core(self):
        from unittest.mock import patch
        import migration_core
        original_apply=migration_core._migrate
        def changed_during_read(*args,**kwargs):
            result=original_apply(*args,**kwargs)
            (self.source/'archive.json').write_text('{}',encoding='utf-8')
            return result
        from mingjing_core.domain.contracts import EvidenceError
        with patch('migration_core._migrate',side_effect=changed_during_read):
            with self.assertRaises(EvidenceError):migrate(self.source,'migration-owner',repository=self.repo,apply=True)
        self.assertEqual(self.repo.list('migration-owner','message'),[])
        self.assertEqual(self.repo.list('migration-owner','fact'),[])

    def test_legacy_reports_keep_receipts_uncertainty_and_waiting_without_body(self):
        jobs=[{'id':'synthetic-'+kind,'kind':'daily','target':'oc_syntheticPrivate'} for kind in ('sent','waiting','uncertain')]
        (self.source/'report-pipeline.json').write_text(json.dumps({'enabled':True,'jobs':jobs}),encoding='utf-8')
        c=sqlite3.connect(self.source/'reports.db')
        try:
            c.execute('CREATE TABLE outbox(id TEXT,kind TEXT,date TEXT,due TEXT,job_id TEXT,status TEXT,content TEXT,attempts INTEGER,first_send REAL,message_id TEXT)')
            c.executemany('INSERT INTO outbox VALUES(?,?,?,?,?,?,?,?,?,?)',[
                ('old-sent','daily','2026-01-01','2026-01-01T07:00:00+08:00','synthetic-sent','sent','SYNTHETIC_PRIVATE_OLD_REPORT',1,123,'om_syntheticRealReceipt'),
                ('old-waiting','daily','2026-01-01','2026-01-01T07:00:00+08:00','synthetic-waiting','waiting','SYNTHETIC_UNVERIFIED_REPORT',0,0,''),
                ('old-uncertain','daily','2026-01-01','2026-01-01T07:00:00+08:00','synthetic-uncertain','retrying','SYNTHETIC_PRIVATE_OLD_REPORT',1,123,'')]);c.commit()
        finally:c.close()
        before=source_hashes(self.source)
        from migration_core import plan
        projected=plan(self.source)['legacy_outbox']
        self.assertTrue(all('content' not in row and 'error' not in row for row in projected))
        first=migrate(self.source,'migration-owner',repository=self.repo,apply=True)
        self.assertEqual(first['errors'],[]);self.assertEqual(first['legacy_delivery_rows'],3)
        with self.repo.connection() as connection:
            rows=connection.execute(sql.SQL('SELECT * FROM {} WHERE owner=%s ORDER BY business_id').format(self.repo.table('delivery_outbox')),('migration-owner',)).fetchall()
        by={row['business_id']:row for row in rows}
        sent=by['report:synthetic-sent:daily:2026-01-01']
        self.assertEqual(sent['status'],'sent');self.assertEqual(sent['receipt'],'om_syntheticRealReceipt')
        self.assertEqual(sent['reconciliation']['verification'],'legacy_sent')
        self.assertEqual(by['report:synthetic-waiting:daily:2026-01-01']['status'],'stale')
        self.assertEqual(by['report:synthetic-uncertain:daily:2026-01-01']['status'],'uncertain')
        self.assertTrue(all(row['payload']=={} and row['run_id'].startswith('legacy:') for row in rows))
        self.assertNotIn('SYNTHETIC_PRIVATE_OLD_REPORT',json.dumps(rows,default=str))
        self.assertEqual(migrate(self.source,'migration-owner',repository=self.repo,apply=True)['legacy_delivery_rows'],0)
        self.assertEqual(source_hashes(self.source),before)

    def test_source_delete_clears_legacy_and_upload_metadata_and_restore_ledger(self):
        source=self.memory.receive('migration-owner','self','我喜欢SYNTHETIC_LEGACY_DELETE',source_id='delete-legacy')
        fact=self.memory.save_fact('migration-owner','self',source['id'],source['content'])
        legacy=self.repo.put('migration-owner','legacy','archive-user',{'payload':{'private':'SYNTHETIC_LEGACY_DELETE'}})
        upload=self.repo.put('migration-owner','upload','upload:synthetic',{'message_id':source['id'],'path':'synthetic-protected-path'})
        self.memory.retire_fact('migration-owner',fact['id'],expected_revision=fact['revision'],scope='source')
        self.assertEqual(self.repo.get('migration-owner','legacy',legacy['id'],include_deleted=True)['status'],'deleted')
        self.assertNotIn('path',self.repo.get('migration-owner','upload',upload['id'],include_deleted=True))
        ledger=self.repo.export_privacy('migration-owner')
        self.assertNotIn('SYNTHETIC_LEGACY_DELETE',json.dumps(ledger))
        from psycopg.types.json import Jsonb
        with self.repo.transaction('migration-owner') as connection:
            for kind,row,data in [('legacy',legacy,{'payload':{'private':'SYNTHETIC_LEGACY_DELETE'}}),('upload',upload,{'path':'synthetic-protected-path'})]:
                connection.execute(sql.SQL("UPDATE {} SET data=%s,status='active' WHERE owner=%s AND kind=%s AND id=%s").format(self.repo.table('core_entities')),
                                   (Jsonb(data),'migration-owner',kind,row['id']))
        self.repo.apply_privacy('migration-owner',ledger)
        for kind,row in [('legacy',legacy),('upload',upload)]:
            restored=self.repo.get('migration-owner',kind,row['id'],include_deleted=True)
            self.assertEqual(restored['status'],'deleted')
            self.assertNotIn('payload',restored);self.assertNotIn('path',restored)

    def test_later_legacy_hidden_is_applied_before_retry(self):
        migrate(self.source,'migration-owner',repository=self.repo,apply=True)
        c=sqlite3.connect(self.source/'web.db')
        try:c.execute("UPDATE memories SET status='hidden' WHERE id='fact-a'");c.commit()
        finally:c.close()
        migrate(self.source,'migration-owner',repository=self.repo,apply=True)
        self.assertEqual({f['content'] for f in self.memory.facts('migration-owner')},{'我喜欢周末徒步'})
        migrate(self.source,'migration-owner',repository=self.repo,apply=True)
        self.assertEqual(len(self.memory.facts('migration-owner')),1)

    def test_privacy_ledger_replayed_after_restore_keeps_bodies_out(self):
        source=self.memory.receive('migration-owner','self','我喜欢SYNTHETIC_PRIVATE_318',source_id='privacy-source')
        fact=self.memory.save_fact('migration-owner','self',source['id'],source['content'])
        old_fact=dict(fact);old_source=dict(source)
        self.memory.retire_fact('migration-owner',fact['id'],expected_revision=fact['revision'],scope='source')
        ledger=self.repo.export_privacy('migration-owner')
        self.assertNotIn('SYNTHETIC_PRIVATE_318',json.dumps(ledger))
        # Simulate offline restored content; restore tools are not permitted to invent new identities.
        with self.repo.transaction('migration-owner') as c:
            for kind,row in [('fact',old_fact),('message',old_source)]:
                data={k:v for k,v in row.items() if k not in ('id','owner','owner_user_id','subject','subject_id','case_id','revision','status','created_at','updated_at','fact_id','write_status')}
                from psycopg.types.json import Jsonb
                c.execute(sql.SQL("UPDATE {} SET data=%s,status='active' WHERE owner=%s AND kind=%s AND id=%s").format(self.repo.table('core_entities')),(Jsonb(data),'migration-owner',kind,row['id']))
        self.repo.apply_privacy('migration-owner',ledger)
        self.assertEqual(self.memory.snapshot('migration-owner')['facts'],[])
        self.assertEqual(self.memory.get_source('migration-owner',source['id'])['content'],'')
        self.repo.apply_privacy('migration-owner',ledger)
        self.assertEqual(self.memory.get_source('migration-owner',source['id'])['content'],'')

    def test_trusted_pipeline_configuration_and_explicit_targets_migrate(self):
        config={'enabled':True,'structured_from':'2026-09-30','jobs':[{'id':'synthetic-daily','target':'oc_synthetic','at':'07:00','kind':'daily'}]}
        (self.source/'report-pipeline.json').write_text(json.dumps(config),encoding='utf-8')
        migrate(self.source,'migration-owner',repository=self.repo,apply=True)
        self.assertEqual(self.repo.assert_scope('migration-owner')['settings']['report_pipeline'],config)
        self.assertEqual(self.repo.resolve_channel('report','synthetic-daily')['binding_kind'],'task')
        self.assertEqual(self.repo.resolve_channel('feishu','oc_synthetic')['binding_kind'],'chat')


if __name__=='__main__':unittest.main()
