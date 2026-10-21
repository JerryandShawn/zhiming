"""Injected PG and candidate command contracts; no real connection or subprocess."""

from __future__ import annotations

import json
import os
import unittest
from typing import Any
from unittest.mock import patch

from test_core_incremental_upgrade import H, fixture

from tools.core_incremental_contracts import MIGRATIONS, Request, UpgradeRejected
from tools.core_incremental_pg import PostgresPort


class Rows:
    def __init__(self, value: Any) -> None:
        self.value = value

    def fetchone(self) -> Any:
        return self.value

    def fetchall(self) -> Any:
        return self.value


class Connection:
    def __init__(self, factory: Factory, role: str) -> None:
        self.factory, self.role = factory, role

    def __enter__(self) -> Connection:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def execute(self, query: Any, params: Any = None) -> Rows:
        text = query if isinstance(query, str) else query.as_string(None)
        self.factory.statements.append((self.role, text, params))
        if text.startswith("SET "):
            return Rows({})
        if "AS version_num" in text:
            return Rows(
                {
                    "database": self.factory.database,
                    "role": self.factory.database + "_" + self.role,
                    "host": self.factory.host,
                    "port": 5432,
                    "version_num": 150018,
                }
            )
        if text.startswith("SELECT rolsuper"):
            return Rows({"elevated": self.factory.elevated})
        if "has_table_privilege" in text:
            return Rows({"safe": self.factory.granted, "allowed": self.factory.granted})
        if "schemaname||" in text:
            return Rows(
                [
                    {"name": "mingjing_core.core_entities"},
                    {"name": "public.checkpoints"},
                ]
            )
        if "FROM pg_tables" in text:
            return Rows([{"schemaname": "mingjing_core", "tablename": "core_entities"}])
        if "schema_migrations ORDER" in text:
            return Rows(
                [
                    {"version": int(key), "checksum": value}
                    for key, value in MIGRATIONS.items()
                    if self.factory.migrated or int(key) <= 4
                ]
            )
        if "FILTER(WHERE status='queued')" in text:
            return Rows({"queued": 0, "running": 0, "leases": 0})
        if "pg_stat_activity" in text:
            return Rows({"count": 0})
        if "jsonb_agg" in text:
            return Rows({"hash": H})
        raise AssertionError("UNEXPECTED_OFFLINE_SQL")


class Factory:
    def __init__(self, database: str) -> None:
        self.database, self.host = database, "127.0.0.1"
        self.migrated, self.elevated, self.granted = False, False, True
        self.statements: list[tuple[str, str, Any]] = []

    def __call__(self, dsn: str, **kwargs: Any) -> Connection:
        return Connection(self, "writer" if "_writer@" in dsn else "owner")


class Commands:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def run(self, args: list[str], **kwargs: Any) -> bytes:
        self.calls.append((args, kwargs))
        compile(args[-1], "synthetic-candidate-code", "exec")
        if "backfill" in args[-1]:
            return json.dumps({"mode": "dry-run", "sample_ids": [], "message_metadata": 0}).encode()
        return b'{"migrated":true}'


class PostgresPortTests(unittest.TestCase):
    def setUp(self) -> None:
        self.request = Request.parse(fixture()[0])
        self.environment = patch.dict(
            os.environ,
            {
                "CORE_INCREMENTAL_OWNER_DSN": "postgresql://zhiming_core_stage_owner@127.0.0.1:5432/zhiming_core_stage",
                "CORE_INCREMENTAL_WRITER_DSN": "postgresql://zhiming_core_stage_writer@127.0.0.1:5432/zhiming_core_stage",
                "KIMI_API_KEY": "SYNTHETIC_MUST_NOT_REACH_CHILD",
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        for name in (
            "subprocess.run",
            "socket.create_connection",
            "psycopg.connect",
            "tools.core_incremental_pg.connect",
            "urllib.request.urlopen",
        ):
            blocker = patch(name, side_effect=AssertionError("PG_PORT_TEST_EXTERNAL_ESCAPE"))
            blocker.start()
            self.addCleanup(blocker.stop)
        self.factory, self.commands = Factory(self.request.database), Commands()
        self.port = PostgresPort(self.request, self.commands, connector=self.factory)

    def test_runtime_and_owner_readonly_snapshots_keep_hashes_not_bodies(self) -> None:
        before = self.port.snapshot(migrated=False)
        self.assertEqual(set(before["checksums"]), {"1", "2", "3", "4"})
        self.assertTrue(before["runtime_safe"])
        self.assertEqual(len(before["state_sha256"]), 64)
        for role in ("writer", "owner"):
            first = next(text for current, text, _ in self.factory.statements if current == role)
            self.assertIn("READ ONLY", first)
        self.factory.migrated = True
        after = self.port.snapshot(migrated=True)
        self.assertEqual(after["checksums"], MIGRATIONS)
        self.assertTrue(after["new_tables_crud"])

    def test_actual_identity_mismatch_blocks_before_business_hash_queries(self) -> None:
        self.factory.host = "1.14.59.242"
        with self.assertRaisesRegex(UpgradeRejected, "LOOPBACK_ONLY"):
            self.port.snapshot(migrated=False)
        self.assertFalse(any("core_entities" in text for _, text, _ in self.factory.statements))

    def test_missing_crud_or_elevated_runtime_cannot_be_safe(self) -> None:
        self.factory.granted = False
        self.assertFalse(self.port.snapshot(migrated=False)["runtime_safe"])
        self.factory.granted, self.factory.elevated = True, True
        self.assertFalse(self.port.snapshot(migrated=False)["runtime_safe"])

    def test_candidate_mutations_use_pinned_interpreter_and_credential_free_provider_environment(
        self,
    ) -> None:
        self.port.migrate_and_grant()
        self.port.backfill("primary", apply=False)
        for args, options in self.commands.calls:
            self.assertEqual(args[0], self.request.release + "/venv/core/bin/python")
            self.assertEqual(args[1:6], ["-I", "-B", "-X", "pycache_prefix=" + os.path.abspath(os.devnull), "-c"])
            self.assertIn(repr(self.request.release), args[-1])
            self.assertNotIn("KIMI_API_KEY", options["env"])
            self.assertNotIn("MOONSHOT_API_KEY", options["env"])
            self.assertNotIn("SYNTHETIC_MUST_NOT_REACH_CHILD", str(options))
            self.assertNotIn("freeze(", args[-1])
        self.assertEqual(
            json.loads(self.commands.calls[-1][1]["stdin"]),
            {"owner": "primary", "apply": False},
        )

    def test_invalid_dsn_scope_role_host_or_port_rejected_before_connector(
        self,
    ) -> None:
        for value in (
            "postgresql://zhiming_core_live_writer@127.0.0.1:5432/zhiming_core_live",
            "postgresql://postgres@127.0.0.1:5432/zhiming_core_stage",
            "postgresql://zhiming_core_stage_writer@1.14.59.242:5432/zhiming_core_stage",
            "postgresql://zhiming_core_stage_writer@127.0.0.1:5433/zhiming_core_stage",
        ):
            with (
                self.subTest(value=value),
                patch.dict(os.environ, {"CORE_INCREMENTAL_WRITER_DSN": value}),
                self.assertRaises(UpgradeRejected),
            ):
                PostgresPort(self.request, self.commands, connector=self.factory)
        self.assertEqual(self.factory.statements, [])


if __name__ == "__main__":
    unittest.main()
