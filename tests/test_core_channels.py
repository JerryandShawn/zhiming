"""Source/identity regressions through actual PG/Core, never legacy StateStore."""
import asyncio
from contextlib import closing
from datetime import date
import hashlib
from pathlib import Path
import sqlite3
import unittest
from mingjing_core.domain.contracts import ScopeError, EvidenceError
from mingjing_core.adapters.channels.hermes import HermesChannelAdapter, render_channel
from mingjing_core.adapters.channels.reports import CoreReportAdapter, report_schedule
from tests import test_core_pg_channels as pg_channels

class CoreChannelSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pg_channels.CorePGChannels.setUpClass();cls.dsn=pg_channels.CorePGChannels.dsn
    setUp=pg_channels.CorePGChannels.setUp
    tearDown=pg_channels.CorePGChannels.tearDown

    def old_fact(self):
        self.hermes.sync('feishu','ou_alice')
        original=next(m for m in self.repo.list('alice','message') if m['source_id']=='alice-old:user')
        return self.service.memory.save_fact('alice','self',original['id'],original['content'],'preference'),original

    def test_unknown_binding_and_forged_current_source_rejected(self):
        with self.assertRaises(ScopeError):self.hermes.identity('feishu','unbound')
        for ident in ('bob-now','group-now','inactive','alice-assistant','missing'):
            with self.assertRaises(EvidenceError):asyncio.run(self.hermes.consult(channel='feishu',external_id='ou_alice',message_id=ident))
        self.assertEqual(self.repo.list('alice','message'),[])

    def test_only_bound_user_dm_active_rows_imported_and_original_unchanged(self):
        before=hashlib.sha256(self.raw.read_bytes()).hexdigest()
        self.assertEqual(self.hermes.sync('feishu','ou_alice'),{'imported':2,'skipped':0})
        revision=self.repo.get_revision('alice');self.hermes.sync('feishu','ou_alice')
        self.assertEqual(self.repo.get_revision('alice'),revision)
        rows=self.repo.list('alice','message')
        self.assertEqual({r['source_id'] for r in rows},{'alice-old:user','alice-now:user'})
        self.assertTrue(all(r['channel']=='feishu' and r['owner_user_id']=='alice' and r['role']=='user' for r in rows))
        self.assertEqual(hashlib.sha256(self.raw.read_bytes()).hexdigest(),before)

    def test_revoked_old_source_skipped_and_current_revocation_rejected(self):
        fact,original=self.old_fact()
        self.service.memory.retire_fact('alice',fact['id'],expected_revision=fact['revision'],operation='stop',scope='source')
        self.assertEqual(self.hermes.sync('feishu','ou_alice'),{'imported':1,'skipped':1})
        with self.assertRaises(EvidenceError):asyncio.run(self.hermes.consult(channel='feishu',external_id='ou_alice',message_id='alice-old'))

    def test_deleted_original_never_restored_from_hermes(self):
        fact,original=self.old_fact()
        self.service.memory.retire_fact('alice',fact['id'],expected_revision=fact['revision'],operation='delete',scope='source')
        self.assertEqual(self.hermes.sync('feishu','ou_alice')['skipped'],1)
        row=self.repo.get('alice','message',original['id'],include_deleted=True)
        self.assertEqual(row['status'],'deleted');self.assertNotIn('content',row)

    def test_chat_binding_has_one_real_author(self):
        self.repo.bind_channel('alice','feishu','oc_alice',binding_kind='chat')
        self.assertEqual(len(self.hermes.original_rows('feishu','oc_alice',binding_kind='chat')),2)
        with closing(sqlite3.connect(self.raw)) as database,database:
            database.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',('ambiguous','feishu','another-person','oc_alice','dm'))
        with self.assertRaises(ScopeError):self.hermes.sync('feishu','oc_alice',binding_kind='chat')

    def test_source_schema_missing_identity_fails_closed(self):
        malformed=Path(self.temporary.name)/'malformed.db'
        with closing(sqlite3.connect(malformed)) as database,database:
            database.executescript('CREATE TABLE sessions(id TEXT);CREATE TABLE messages(id TEXT);')
        adapter=HermesChannelAdapter('.',service=self.service,hermes_db=malformed)
        with self.assertRaises(EvidenceError):adapter.sync('feishu','ou_alice')

    def test_report_schedule_preserves_original_shanghai_times(self):
        for kind,day,prepare,deliver in (('daily','2026-10-11','06:45','07:00'),('weekly','2026-10-11','19:45','20:00'),('monthly','2026-11-01','08:45','09:00'),('quarterly','2027-01-01','09:45','10:00')):
            schedule=report_schedule(kind,date.fromisoformat(day))
            self.assertEqual(schedule['prepare_at'].strftime('%H:%M'),prepare)
            self.assertEqual(schedule['deliver_at'].strftime('%H:%M'),deliver)
            self.assertEqual(schedule['deliver_at'].utcoffset().total_seconds(),8*3600)
        self.assertIsNone(report_schedule('weekly',date(2026,10,12)))
        self.assertIsNone(report_schedule('quarterly',date(2026,11,1)))
        with self.assertRaises(ScopeError):CoreReportAdapter('.',service=self.service).identity('ou_alice')

    def test_rendering_is_exact_and_cannot_upgrade_legacy_output(self):
        result=asyncio.run(self.hermes.consult(channel='feishu',external_id='ou_alice',message_id='alice-now',depth='fast'))
        self.assertEqual(render_channel(result),result['answer'])
        for broken in (dict(result,validation={}),dict(result,meta={}),dict(result,answer='')):
            with self.assertRaises(EvidenceError):render_channel(broken)

if __name__=='__main__':unittest.main()
