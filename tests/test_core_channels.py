"""Real source/identity boundaries and thin-channel Core integration.

Synthetic Hermes rows are local SQLite fixtures. No real transport is called.
Model integration below uses a ModelPort fixture, never a service substitute.
"""
import asyncio
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hermes.state_store import EvidenceError, ScopeError, StateStore
from mingjing_core.adapters.channels.hermes import HermesChannelAdapter, render_channel
from mingjing_core.adapters.channels.reports import CoreReportAdapter, report_schedule


class ChannelFixtures(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.raw = self.base / "hermes-original.db"
        self.state = StateStore(self.base)
        self.state.ensure_owner("alice")
        self.state.ensure_owner("bob")
        self.state.bind_channel("alice", "feishu", "ou_alice")
        self.state.bind_channel("bob", "feishu", "ou_bob")
        self.state.bind_channel("alice", "report", "daily-alice")
        with closing(sqlite3.connect(self.raw)) as database, database:
            database.executescript(
                "CREATE TABLE sessions(id TEXT,source TEXT,user_id TEXT,chat_id TEXT,chat_type TEXT);"
                "CREATE TABLE messages(id TEXT,session_id TEXT,role TEXT,content TEXT,timestamp REAL,active INTEGER);"
            )
            database.executemany("INSERT INTO sessions VALUES(?,?,?,?,?)", [
                ("s-alice", "feishu", "ou_alice", "oc_alice", "dm"),
                ("s-bob", "feishu", "ou_bob", "oc_bob", "dm"),
                ("s-group", "feishu", "ou_alice", "oc_group", "group"),
                ("s-telegram", "telegram", "ou_alice", "oc_other", "dm"),
            ])
            database.executemany("INSERT INTO messages VALUES(?,?,?,?,?,?)", [
                ("a-old", "s-alice", "user", "请记住，我喜欢简洁的回答。", 1791660000, 1),
                ("a-now", "s-alice", "user", "今天先聊一件小事。", 1791660001, 1),
                ("a-assistant", "s-alice", "assistant", "你会成为亿万富翁。", 1791660002, 1),
                ("a-inactive", "s-alice", "user", "已撤回的私聊内容", 1791660003, 0),
                ("b-now", "s-bob", "user", "Bob 的个人秘密", 1791660004, 1),
                ("group-now", "s-group", "user", "群聊的个人秘密", 1791660005, 1),
                ("other-now", "s-telegram", "user", "另一个渠道秘密", 1791660006, 1),
            ])
        self.adapter = HermesChannelAdapter(self.base, hermes_db=self.raw)

    def old_fact(self):
        self.adapter.sync("feishu", "ou_alice")
        with self.state.db() as database:
            row = database.execute(
                "SELECT id FROM messages WHERE owner='alice' AND source='feishu' AND source_id='a-old:user'"
            ).fetchone()
        text = "请记住，我喜欢简洁的回答。"
        return self.state.put_fact(
            "alice", "self", text, [{"message_id": row["id"], "quote": text}],
            kind="preference", explicit=True,
        )


class CoreChannelSourceTests(ChannelFixtures):
    def test_unknown_binding_and_forged_current_source_rejected(self):
        with self.assertRaises(ScopeError):
            self.adapter.identity("feishu", "unbound")
        for message_id in ("b-now", "a-assistant", "a-inactive", "group-now", "other-now", "not-there"):
            with self.assertRaises(EvidenceError):
                asyncio.run(self.adapter.consult(channel="feishu", external_id="ou_alice", message_id=message_id))
        with self.state.db() as database:
            self.assertEqual(database.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 0)

    def test_only_bound_user_dm_active_rows_imported_and_original_unchanged(self):
        before = hashlib.sha256(self.raw.read_bytes()).hexdigest()
        self.assertEqual(self.adapter.sync("feishu", "ou_alice"), {"imported": 2, "skipped": 0})
        revision = self.state.revision("alice")
        self.adapter.sync("feishu", "ou_alice")
        self.assertEqual(self.state.revision("alice"), revision)
        with self.state.db() as database:
            sources = [dict(row) for row in database.execute("SELECT source,source_id,role,owner,subject,conversation_id FROM messages")]
        self.assertEqual({row["source_id"] for row in sources}, {"a-old:user", "a-now:user"})
        self.assertTrue(all(row["source"] == "feishu" and row["role"] == "user" and row["owner"] == "alice" for row in sources))
        self.assertTrue(all(row["conversation_id"] == "feishu:s-alice" for row in sources))
        self.assertEqual(hashlib.sha256(self.raw.read_bytes()).hexdigest(), before)

    def test_revoked_old_source_skipped_and_current_revocation_rejected(self):
        fact = self.old_fact()
        self.state.stop_fact("alice", fact["id"], self.state.revision("alice"))
        revision = self.state.revision("alice")
        self.assertEqual(self.adapter.sync("feishu", "ou_alice"), {"imported": 1, "skipped": 1})
        self.assertEqual(self.state.revision("alice"), revision)
        with self.assertRaises(EvidenceError):
            asyncio.run(self.adapter.consult(channel="feishu", external_id="ou_alice", message_id="a-old"))

    def test_deleted_original_never_restored_from_hermes(self):
        fact = self.old_fact()
        self.state.delete_fact("alice", fact["id"], self.state.revision("alice"), scope="source")
        self.assertEqual(self.adapter.sync("feishu", "ou_alice")["skipped"], 1)
        with self.state.db() as database:
            row = database.execute("SELECT content,status FROM messages WHERE source_id='a-old:user'").fetchone()
        self.assertEqual(dict(row), {"content": "", "status": "deleted"})

    def test_chat_binding_has_one_real_author(self):
        self.state.bind_channel("alice", "feishu", "oc_alice")
        self.assertEqual(len(self.adapter.original_rows("feishu", "oc_alice", binding_kind="chat")), 2)
        with closing(sqlite3.connect(self.raw)) as database, database:
            database.execute("INSERT INTO sessions VALUES(?,?,?,?,?)", ("ambiguous", "feishu", "another-person", "oc_alice", "dm"))
        with self.assertRaises(ScopeError):
            self.adapter.sync("feishu", "oc_alice", binding_kind="chat")

    def test_source_schema_missing_identity_fails_closed(self):
        malformed = self.base / "malformed.db"
        with closing(sqlite3.connect(malformed)) as database, database:
            database.executescript("CREATE TABLE sessions(id TEXT);CREATE TABLE messages(id TEXT);")
        adapter = HermesChannelAdapter(self.base, hermes_db=malformed)
        with self.assertRaises(EvidenceError):
            adapter.sync("feishu", "ou_alice")

    def test_report_schedule_preserves_original_shanghai_times(self):
        for kind, day, prepare, deliver in [
            ("daily", "2026-10-11", "06:45", "07:00"),
            ("weekly", "2026-10-11", "19:45", "20:00"),
            ("monthly", "2026-11-01", "08:45", "09:00"),
            ("quarterly", "2027-01-01", "09:45", "10:00"),
        ]:
            schedule = report_schedule(kind, date.fromisoformat(day))
            self.assertEqual(schedule["prepare_at"].strftime("%H:%M"), prepare)
            self.assertEqual(schedule["deliver_at"].strftime("%H:%M"), deliver)
            self.assertEqual(schedule["deliver_at"].utcoffset().total_seconds(), 8 * 3600)
        self.assertIsNone(report_schedule("weekly", date(2026, 10, 12)))
        self.assertIsNone(report_schedule("quarterly", date(2026, 11, 1)))
        with self.assertRaises(ScopeError):
            CoreReportAdapter(self.base).identity("ou_alice")

    def test_rendering_is_exact_and_cannot_upgrade_legacy_output(self):
        result = {"answer": "白话结论\n\n专业依据", "validation": {"core_version": "3.0"},
                  "meta": {"core_run": "run-a", "episode_id": "episode-a", "reading_id": "reading-a"}}
        self.assertEqual(render_channel(result), result["answer"])
        for broken in (dict(result, validation={}), dict(result, meta={}), dict(result, answer="")):
            with self.assertRaises(EvidenceError):
                render_channel(broken)


if __name__ == "__main__":
    unittest.main(verbosity=2)
