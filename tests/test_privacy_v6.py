import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'hermes'))
from privacy_replay import apply_privacy, export_privacy
from state_store import StateStore, EvidenceError, ScopeError
from tarot_store import TarotDrawService


class PrivacyRestoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.live = self.base / 'current'; self.restore = self.base / 'restore'
        self.state = StateStore(self.live); self.tarot = TarotDrawService(self.live)
        self.state.ensure_owner('alice'); self.state.ensure_owner('bob')
        self.secret = 'PRIVATE_SOURCE_BODY_2026 偏好安静的环境'
        self.message = self.state.import_message('alice', 'web', 'turn-old:user', 'user', self.secret)
        refs = [{'message_id': self.message['id'], 'quote': self.secret}]
        self.fact = self.state.put_fact('alice', 'self', self.secret, refs, idempotency_key='fact-key', explicit=True)
        self.case = self.state.create_case('alice', 'self', self.secret, refs)
        self.state.add_case_event('alice', self.case['id'], 'discussed', self.secret, refs)
        self.key = 'PRIVATE_CLEAR_RETRY_KEY'
        self.draw = self.tarot.create_draw('alice', subject_id='self', case_id=self.case['id'],
                                          question='PRIVATE_DRAW_QUESTION', context_snapshot={'fact_ids': [self.fact['id']], 'body': self.secret},
                                          idempotency_key=self.key)['draw']
        self.tarot.reveal('alice', self.draw['id'])
        self.reading = self.tarot.begin_reading('alice', self.draw['id'], model='test-model', prompt_version='test-v6',
                                               context_snapshot={'fact_ids': [self.fact['id']], 'body': self.secret},
                                               idempotency_key='PRIVATE_READING_KEY')['reading']
        self.tarot.finish_reading('alice', self.reading['id'], result={'body': self.secret}, validation={'ok': True})
        self.other_draw = self.tarot.create_draw('bob', subject_id='self', case_id='other-case',
                                                question='OTHER_OWNER_BODY', idempotency_key=self.key)['draw']
        self.state.record_trace('alice', 'old-trace', {'status': 'complete', 'injected_ids': [self.fact['id']]})
        self.state.record_trace('bob', 'other-trace', {'status': 'complete'})
        self.restore.mkdir()
        for name in ('state.sqlite', 'tarot.db'):
            with closing(sqlite3.connect(self.live / name)) as source, closing(sqlite3.connect(self.restore / name)) as destination:
                source.backup(destination)
        self.journal = self.base / 'revocations.json'

    def tearDown(self):
        self.temp.cleanup()

    def hashes(self, directory):
        return {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in ('state.sqlite', 'tarot.db')}

    def export(self):
        before = self.hashes(self.live)
        result = export_privacy('alice', self.live / 'state.sqlite', self.live / 'tarot.db', self.journal)
        self.assertEqual(before, self.hashes(self.live))
        text = self.journal.read_text(encoding='utf-8')
        for forbidden in (self.secret, self.key, 'PRIVATE_READING_KEY', 'PRIVATE_DRAW_QUESTION', 'OTHER_OWNER_BODY', '"quote"', '"request_key"'):
            self.assertNotIn(forbidden, text)
        self.assertNotIn('bob', text)
        if os.name != 'nt':
            self.assertEqual(self.journal.stat().st_mode & 0o777, 0o600)
        return result

    def apply(self, owner='alice'):
        return apply_privacy(owner, self.restore / 'state.sqlite', self.restore / 'tarot.db', self.journal)

    def test_deleted_fact_draw_and_retry_keys_cannot_resurrect_after_restore(self):
        self.state.delete_fact('alice', self.fact['id'], self.state.revision('alice'), scope='source')
        self.tarot.delete('alice', self.draw['id'])
        exported = self.export()
        self.assertEqual(exported['suppression_count'], 1)
        self.assertEqual(exported['tarot_key_count'], 2)
        live_hashes = self.hashes(self.live)
        result = self.apply()
        self.assertEqual(result['facts_revoked'], 1)
        self.assertEqual(result['messages_purged'], 1)
        self.assertEqual(result['cases_invalidated'], 1)
        self.assertEqual(result['case_events_deleted'], 1)
        self.assertEqual(result['tarot_draws_deleted'], 1)
        state = StateStore(self.restore); tarot = TarotDrawService(self.restore)
        self.assertEqual(state.list_facts('alice'), [])
        forgotten = state.get_fact('alice', self.fact['id'])
        self.assertEqual(forgotten['status'], 'deleted'); self.assertEqual(forgotten['content'], '')
        self.assertNotIn(self.secret, json.dumps(forgotten, ensure_ascii=False))
        with self.assertRaises(EvidenceError):
            state.get_message('alice', self.message['id'])
        self.assertEqual(state.get_message('alice', self.message['id'], include_suppressed=True)['content'], '')
        revived = state.import_message('alice', 'web', 'turn-old:user', 'user', self.secret)
        with self.assertRaises(EvidenceError):
            state.put_fact('alice', 'self', self.secret, [{'message_id': revived['id'], 'quote': self.secret}], explicit=True)
        self.assertNotIn(self.secret, json.dumps(state.snapshot('alice'), ensure_ascii=False))
        with self.assertRaises(KeyError): tarot.get('alice', self.draw['id'])
        with self.assertRaises(KeyError): tarot.get_reading('alice', self.reading['id'])
        with self.assertRaises(ValueError): tarot.request_result('alice', 'create', self.key)
        with self.assertRaises(ValueError):
            tarot.create_draw('alice', subject_id='self', case_id=self.case['id'], question='new', idempotency_key=self.key)
        self.assertEqual(tarot.get('bob', self.other_draw['id'])['question'], 'OTHER_OWNER_BODY')
        self.assertEqual(state.get_trace('bob', 'other-trace')['payload']['status'], 'complete')
        with self.assertRaises(ScopeError): state.get_trace('alice', 'old-trace')
        revision = state.revision('alice')
        again = self.apply()
        self.assertEqual(again['revision'], revision)
        self.assertEqual(again['tarot_draws_deleted'], 0)
        self.assertEqual(live_hashes, self.hashes(self.live))

    def test_stop_remains_suppressed_and_removes_source_derived_draw(self):
        self.state.stop_fact('alice', self.fact['id'], self.state.revision('alice'))
        self.export(); result = self.apply()
        self.assertEqual(result['tarot_draws_deleted'], 1)
        state = StateStore(self.restore); tarot = TarotDrawService(self.restore)
        self.assertEqual(state.list_facts('alice'), [])
        self.assertEqual(state.get_fact('alice', self.fact['id'])['status'], 'stopped')
        # Stopping context use preserves the original history according to its scope.
        self.assertEqual(state.get_message('alice', self.message['id'], include_suppressed=True)['content'], self.secret)
        with self.assertRaises(EvidenceError): state.get_message('alice', self.message['id'])
        with self.assertRaises(ValueError): tarot.request_result('alice', 'create', self.key)

    def test_fact_only_delete_keeps_original_but_purges_derived_fact(self):
        self.state.delete_fact('alice', self.fact['id'], self.state.revision('alice'), scope='fact')
        self.export(); self.apply()
        state = StateStore(self.restore)
        self.assertEqual(state.get_fact('alice', self.fact['id'])['content'], '')
        self.assertEqual(state.get_message('alice', self.message['id'], include_suppressed=True)['content'], self.secret)
        self.assertNotIn(self.secret, json.dumps(state.snapshot('alice'), ensure_ascii=False))

    def test_owner_mismatch_and_unrecognized_document_fail_without_target_changes(self):
        self.state.delete_fact('alice', self.fact['id'], self.state.revision('alice'))
        self.export(); before = self.hashes(self.restore)
        with self.assertRaises(ValueError): self.apply('bob')
        self.assertEqual(before, self.hashes(self.restore))
        data = json.loads(self.journal.read_text(encoding='utf-8')); data['body'] = self.secret
        self.journal.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaises(ValueError): self.apply()
        self.assertEqual(before, self.hashes(self.restore))

    def test_both_targets_rollback_on_missing_tarot_schema(self):
        self.state.delete_fact('alice', self.fact['id'], self.state.revision('alice'), scope='source')
        self.export()
        with closing(sqlite3.connect(self.restore / 'tarot.db')) as connection:
            connection.execute('DROP TABLE tarot_deleted_requests'); connection.commit()
        before = self.hashes(self.restore)
        with self.assertRaises(sqlite3.OperationalError): self.apply()
        self.assertEqual(before, self.hashes(self.restore))

    def test_wal_restore_is_rejected_before_mutating_either_database(self):
        self.state.delete_fact('alice', self.fact['id'], self.state.revision('alice'), scope='source')
        self.export()
        with closing(sqlite3.connect(self.restore / 'tarot.db')) as connection:
            self.assertEqual(connection.execute('PRAGMA journal_mode=WAL').fetchone()[0], 'wal')
        before = self.hashes(self.restore)
        with self.assertRaisesRegex(ValueError, 'rollback journals'):
            self.apply()
        self.assertEqual(before, self.hashes(self.restore))
        self.assertEqual(StateStore(self.restore).get_fact('alice', self.fact['id'])['status'], 'active')

    def test_export_is_create_only_and_cli_requires_explicit_restore_targets(self):
        self.export()
        with self.assertRaises(FileExistsError): self.export()
        result = subprocess.run([sys.executable, str(ROOT / 'hermes/privacy_replay.py'), '--apply', '--owner', 'alice',
                                 '--state-db', str(self.restore / 'state.sqlite'), '--tarot-db', str(self.restore / 'tarot.db'),
                                 '--file', str(self.journal)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(self.secret, result.stdout + result.stderr)

    def test_cli_export_then_apply_executes_real_restore(self):
        self.state.delete_fact('alice', self.fact['id'], self.state.revision('alice'), scope='source')
        self.tarot.delete('alice', self.draw['id'])
        commands = [
            ['--export', '--state-db', str(self.live / 'state.sqlite'), '--tarot-db', str(self.live / 'tarot.db')],
            ['--apply', '--restore-state-db', str(self.restore / 'state.sqlite'), '--restore-tarot-db', str(self.restore / 'tarot.db')],
        ]
        for arguments in commands:
            result = subprocess.run([sys.executable, str(ROOT / 'hermes/privacy_replay.py'), *arguments,
                                     '--owner', 'alice', '--file', str(self.journal)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn(self.secret, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['tarot_draws_deleted'], 1)
        self.assertEqual(StateStore(self.restore).get_fact('alice', self.fact['id'])['status'], 'deleted')
        with self.assertRaises(ValueError): TarotDrawService(self.restore).request_result('alice', 'create', self.key)


class TraceRetentionTests(unittest.TestCase):
    def test_default_and_configured_retention_are_owner_scoped_and_body_free(self):
        with tempfile.TemporaryDirectory() as base:
            state = StateStore(base); state.ensure_owner('alice'); state.ensure_owner('bob')
            for owner, run in (('alice', 'expired'), ('alice', 'recent'), ('bob', 'other-expired')):
                state.record_trace(owner, run, {'status': 'complete'})
            old = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat(timespec='microseconds')
            recent = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(timespec='microseconds')
            with state.db(True) as connection:
                connection.execute("UPDATE traces SET created_at=? WHERE run_id IN ('expired','other-expired')", (old,))
                connection.execute("UPDATE traces SET created_at=? WHERE run_id='recent'", (recent,))
            with patch.dict(os.environ, {}, clear=True):
                state.record_trace('alice', 'new', {'status': 'complete', 'body': 'DO_NOT_LOG', 'validation': {'body': 'DO_NOT_LOG', 'password': 'DO_NOT_LOG', 'ok': True}})
            with self.assertRaises(ScopeError): state.get_trace('alice', 'expired')
            state.get_trace('alice', 'recent'); state.get_trace('bob', 'other-expired')
            self.assertNotIn('DO_NOT_LOG', json.dumps(state.get_trace('alice', 'new')))
            with patch.dict(os.environ, {'ZHIMING_TRACE_RETENTION_DAYS': '2'}):
                state.record_trace('alice', 'newer', {'status': 'complete'})
            with self.assertRaises(ScopeError): state.get_trace('alice', 'recent')
            for invalid in (0, -1, True, 'never', 3651):
                with self.assertRaises(ValueError): state.record_trace('alice', 'invalid', {}, retention_days=invalid)


if __name__ == '__main__':
    unittest.main(verbosity=2)
