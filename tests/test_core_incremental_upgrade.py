"""Offline controller effects and rejection gates; host/network escape is forbidden."""

from __future__ import annotations

import copy
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

from test_core_incremental_support import restore_for

from tools.core_incremental import execute
from tools.core_incremental_contracts import (
    EXPECTED_MANIFEST,
    MIGRATIONS,
    MODEL_BASE,
    PREVIOUS,
    STAGE_UNITS,
    TARGET,
    Request,
    UpgradeRejected,
    digest,
)

H = "a" * 64
NOW = datetime(2026, 10, 18, 12, tzinfo=UTC)


def fixture(scope: str = "stage") -> tuple[dict[str, Any], dict[str, Any]]:
    units = list(STAGE_UNITS)
    if scope == "live":
        units = [
            "mingjingtai.service",
            "zhiming-core-feishu.service",
            "zhiming-core-reports.service",
            "zhiming-core-reports.timer",
        ]
    raw = {
        "schema": "b1-incremental-request-v1",
        "operation_id": "synthetic-b1-001",
        "scope": scope,
        "target": TARGET,
        "previous": PREVIOUS,
        "hostname": "synthetic-host",
        "manifest_sha256": EXPECTED_MANIFEST,
        "controller_sha256": H,
        "owners": ["primary"],
        "minimum_free_bytes": 8 * 1024**3,
        "unit_sha256": dict.fromkeys(units, H),
        "skill_manifest_sha256": H,
    }
    approval = {
        "schema": "b1-incremental-approval-v1",
        "operation_id": raw["operation_id"],
        "scope": scope,
        "request_sha256": digest(raw),
        "controller_sha256": H,
        "expires_at": "2026-10-18T13:00:00+00:00",
        "quiesced_upgrade": True,
        "resume_business": False,
        "model_calls": False,
        "channel_sends": False,
    }
    return raw, approval


class Sandbox:
    def __init__(self, request: Request) -> None:
        self.request = request
        self.events: list[str] = []
        self.migrated = False
        self.applies = 0
        self.closed = False
        self.overrides: dict[str, Any] = {}
        self.fail_at = ""

    @contextmanager
    def quiesce(self, request: Request) -> Iterator[None]:
        self.closed = True
        self.events.append("quiesce")
        if self.fail_at == "enter":
            raise RuntimeError("SYNTHETIC_ENTER_FAILURE")
        yield
        self.events.append("unlock")

    def snapshot(self, request: Request, *, migrated: bool) -> dict[str, Any]:
        self.events.append("snapshot")
        value = {
            "hostname": request.hostname,
            "manifest_sha256": request.manifest_sha256,
            "source_verified": True,
            "target": TARGET,
            "previous": PREVIOUS,
            "migration_manifest": MIGRATIONS,
            "free_bytes": 12 * 1024**3,
            "checksums": MIGRATIONS if self.migrated else {k: MIGRATIONS[k] for k in ("1", "2", "3", "4")},
            "identities": {
                role: {
                    "database": request.database,
                    "port": 5432,
                    "host": "127.0.0.1",
                    "role": request.database + "_" + role,
                    "version_num": 150018,
                }
                for role in ("owner", "writer")
            },
            "runtime_safe": True,
            "new_tables_crud": self.migrated,
            "queues": {"queued": 0, "running": 0, "leases": 0},
            "other_database_sessions": 0,
            "writers": {unit: {"inactive": True, "boot_disabled": True} for unit in request.units},
            "maintenance": self.closed,
            "fence_held": True,
            "hermes_fence_held": True,
            "model": {"model": "k3", "base": MODEL_BASE, "new_port": False},
            "state_sha256": "b" * 64 if self.migrated else H,
        }
        value.update(copy.deepcopy(self.overrides))
        return value

    def backup(self, request: Request, snapshot: dict[str, Any]) -> dict[str, Any]:
        self.events.append("backup")
        return {
            "schema": "b1-quiesced-backup-v1",
            "operation_id": request.operation_id,
            "database": request.database,
            "source_state_sha256": snapshot["state_sha256"],
            "target": TARGET,
            "manifest_sha256": request.manifest_sha256,
            "mode": "0600",
            "body_free_withdrawals": True,
            "dump_sha256": H,
            "withdrawals_sha256": H,
        }

    def verify_backup_files(self, backup: dict[str, Any]) -> None:
        self.events.append("verify_backup")
        if self.fail_at == "backup_hash":
            raise UpgradeRejected("BACKUP_FILE_CHANGED")

    def migrate_and_grant(self, request: Request) -> None:
        self.events.append("migrate")
        self.migrated = True
        if self.fail_at == "after_commit":
            raise KeyboardInterrupt("SYNTHETIC_AFTER_COMMIT")

    def backfill(self, request: Request, owner: str, *, apply: bool) -> dict[str, Any]:
        self.events.append("apply" if apply else "dry_run")
        count = 1 if not apply or self.applies == 0 else 0
        self.applies += int(apply)
        return {
            "message_metadata": count,
            "search_tokens": count,
            "assistant_created": count,
            "immutable_originals_preserved": True,
        }

    def retarget(self, request: Request) -> dict[str, Any]:
        self.events.append("retarget")
        return {
            "source_verified": True,
            "writers_still_stopped": True,
            "hermes_retired_preserved": True,
        }

    def keep_closed(self, request: Request) -> None:
        self.closed = True
        self.events.append("keep_closed")


class UpgradeTests(unittest.TestCase):
    def setUp(self) -> None:
        for name in (
            "subprocess.run",
            "socket.create_connection",
            "urllib.request.urlopen",
            "os.system",
            "os.execv",
        ):
            blocker = patch(name, side_effect=AssertionError("OFFLINE_TEST_EXTERNAL_ESCAPE"))
            blocker.start()
            self.addCleanup(blocker.stop)
        self.raw, self.approval = fixture()
        self.port = Sandbox(Request.parse(self.raw))

    def run_action(self, action: str, **kwargs: Any) -> dict[str, Any]:
        return execute(
            self.raw,
            self.approval,
            self.port,
            now=NOW,
            action=action,
            controller=H,
            **kwargs,
        )

    def saved(self) -> tuple[dict[str, Any], dict[str, Any]]:
        backup = self.run_action("backup")["backup"]
        restore = restore_for(self.port.request, backup)
        self.approval["restore_sha256"] = digest(restore)
        return backup, restore

    def migrated(self) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        backup, restore = self.saved()
        migration = self.run_action("migrate", backup=backup, restore=restore)
        self.approval["migration_sha256"] = digest(migration)
        self.approval["backfill_review_sha256"] = digest(migration["review"])
        return backup, restore, migration

    def test_three_phases_mutate_only_after_matching_fresh_reviews(self) -> None:
        backup, restore, migration = self.migrated()
        self.assertTrue(self.port.migrated)
        self.assertEqual(self.port.applies, 0)
        result = self.run_action(
            "backfill",
            backup=backup,
            restore=restore,
            migration=migration,
            reviewed_backfills=migration["review"],
        )
        self.assertEqual(result["status"], "quiesced_upgraded")
        self.assertFalse(result["publication"])
        self.assertEqual(self.port.applies, 2)
        self.assertTrue(self.port.closed)
        self.assertLess(self.port.events.index("backup"), self.port.events.index("migrate"))
        self.assertLess(self.port.events.index("migrate"), self.port.events.index("apply"))

    def test_static_pins_approval_time_and_scope_block_before_quiescing(self) -> None:
        for key, value in (
            ("target", "f" * 40),
            ("previous", "f" * 40),
            ("scope", "restore"),
            ("owners", []),
            ("owners", ["primary", "primary"]),
            ("owners", [{}]),
            ("minimum_free_bytes", 791592960),
        ):
            with self.subTest(key=key, value=value):
                raw = dict(self.raw, **{key: value})
                with self.assertRaises(UpgradeRejected):
                    execute(
                        raw,
                        self.approval,
                        self.port,
                        now=NOW,
                        action="backup",
                        controller=H,
                    )
        for key, value in (
            ("request_sha256", "f" * 64),
            ("scope", "live"),
            ("model_calls", True),
            ("resume_business", True),
            ("channel_sends", True),
            ("controller_sha256", "f" * 64),
            ("expires_at", "2026-10-17T00:00:00+00:00"),
        ):
            with self.subTest(key=key), self.assertRaises(UpgradeRejected):
                execute(
                    self.raw,
                    dict(self.approval, **{key: value}),
                    self.port,
                    now=NOW,
                    action="backup",
                    controller=H,
                )
        self.assertEqual(self.port.events, [])

    def test_live_unknown_writer_model_schema_capacity_fail_closed(self) -> None:
        cases = [
            {"hostname": "wrong"},
            {"source_verified": False},
            {"manifest_sha256": "f" * 64},
            {"migration_manifest": {"1": H}},
            {"checksums": MIGRATIONS},
            {"free_bytes": 791592960},
            {"runtime_safe": False},
            {"writers": {}},
            {"fence_held": False},
            {"maintenance": False},
            {"queues": {"queued": 1, "running": 0, "leases": 0}},
            {"other_database_sessions": 1},
            {"other_database_sessions": False},
            {"state_sha256": None},
            {"model": {"model": "k3-256k", "base": MODEL_BASE, "new_port": False}},
        ]
        for change in cases:
            with self.subTest(change=change):
                self.port.overrides = change
                with self.assertRaises(UpgradeRejected):
                    self.run_action("backup")
                self.assertNotIn("backup", self.port.events)
                self.assertTrue(self.port.closed)

    def test_wrong_database_host_port_role_and_privileges_are_rejected(self) -> None:
        original = self.port.snapshot(self.port.request, migrated=False)["identities"]
        for key, value in (
            ("database", "zhiming_core_live"),
            ("host", "1.14.59.242"),
            ("port", 5433),
            ("role", "postgres"),
            ("version_num", 160000),
        ):
            with self.subTest(key=key):
                identities = copy.deepcopy(original)
                identities["writer"][key] = value
                self.port.overrides = {"identities": identities}
                with self.assertRaises(UpgradeRejected):
                    self.run_action("backup")

    def test_backup_restore_tampering_prevents_migration(self) -> None:
        backup, restore = self.saved()
        for change in (
            {"backup_sha256": "f" * 64},
            {"checksums": {"1": H}},
            {"database": self.port.request.database},
            {"actual_pg_restore": False},
            {"model_calls": 1},
        ):
            with self.subTest(change=change), self.assertRaises(UpgradeRejected):
                self.run_action("migrate", backup=backup, restore=dict(restore, **change))
        self.port.fail_at = "backup_hash"
        with self.assertRaises(UpgradeRejected):
            self.run_action("migrate", backup=backup, restore=restore)
        self.assertNotIn("migrate", self.port.events)

    def test_crash_after_commit_keeps_gate_and_does_not_restart_or_revert_schema(
        self,
    ) -> None:
        backup, restore = self.saved()
        self.port.fail_at = "after_commit"
        with self.assertRaises(KeyboardInterrupt):
            self.run_action("migrate", backup=backup, restore=restore)
        self.assertTrue(self.port.migrated and self.port.closed)
        self.assertEqual(self.port.events[-1], "keep_closed")
        self.assertNotIn("retarget", self.port.events)

    def test_partial_fence_entry_failure_still_attempts_keep_closed(self) -> None:
        self.port.fail_at = "enter"
        with self.assertRaises(RuntimeError):
            self.run_action("backup")
        self.assertEqual(self.port.events, ["quiesce", "keep_closed"])

    def test_changed_state_or_missing_review_cannot_apply_backfill(self) -> None:
        backup, restore, migration = self.migrated()
        for change in ({"after_state_sha256": "f" * 64}, {"backup_sha256": "f" * 64}):
            changed = dict(migration, **change)
            self.approval["migration_sha256"] = digest(changed)
            with self.subTest(change=change), self.assertRaises(UpgradeRejected):
                self.run_action(
                    "backfill",
                    backup=backup,
                    restore=restore,
                    migration=changed,
                    reviewed_backfills=migration["review"],
                )
        self.approval["migration_sha256"] = digest(migration)
        with self.assertRaises(UpgradeRejected):
            self.run_action("backfill", backup=backup, restore=restore, migration=migration)
        self.assertEqual(self.port.applies, 0)

    def test_live_requires_exact_all_writer_units_and_hermes_fence(self) -> None:
        self.raw, self.approval = fixture("live")
        self.port = Sandbox(Request.parse(self.raw))
        self.port.overrides = {"hermes_fence_held": False}
        with self.assertRaisesRegex(UpgradeRejected, "HERMES_WRITER_FENCE"):
            self.run_action("backup")
        self.assertNotIn("backup", self.port.events)

    def test_changed_immutable_receipt_never_retargets_or_opens_gate(self) -> None:
        backup, restore, migration = self.migrated()
        original = self.port.backfill

        def changed(request: Request, owner: str, *, apply: bool) -> dict[str, Any]:
            value = original(request, owner, apply=apply)
            if apply:
                value["immutable_originals_preserved"] = False
            return value

        with (
            patch.object(self.port, "backfill", side_effect=changed),
            self.assertRaisesRegex(UpgradeRejected, "BACKFILL_ORIGINAL_CHANGED"),
        ):
            self.run_action(
                "backfill",
                backup=backup,
                restore=restore,
                migration=migration,
                reviewed_backfills=migration["review"],
            )
        self.assertNotIn("retarget", self.port.events)
        self.assertTrue(self.port.closed)


if __name__ == "__main__":
    unittest.main()
