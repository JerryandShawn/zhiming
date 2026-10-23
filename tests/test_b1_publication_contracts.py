"""Offline publication sequencing and authorization; never selects native I/O."""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

from mingjing_core.timekit.clock import FrozenClock
from tools.b1_publication import execute, main
from tools.b1_publication_contracts import FILES, Plan, PublicationRejected, validate_review
from tools.b1_publication_native import NativePublicationPort
from tools.core_incremental_contracts import LIVE_UNITS, PREVIOUS, TARGET, digest

NOW = datetime(2026, 10, 21, 2, 30, tzinfo=UTC)


def fixture(action: str = "open") -> tuple[dict[str, Any], dict[str, Any], bytes]:
    root = "/root/zhiming-core-backups/incremental-rehearsal_001"
    text = ("结论：Go\nweb_then_background\n用户本人已对大脑说上线\n" + TARGET
            + "\n2026-10-20T20:00:00+08:00\n2026-10-21T10:00:00+08:00\n2026-10-21T13:00:00+08:00\n").encode()
    raw = dict(schema="b1-publication-plan-v1", operation_id="rehearsal_001", scope="live", hostname="test-host",
               target=TARGET, previous=PREVIOUS, operation_dir=root, review_file=root + "/31.md",
               review_sha256=hashlib.sha256(text).hexdigest(), review_written_at="2026-10-20T20:00:00+08:00",
               window_start="2026-10-21T10:00:00+08:00", window_end="2026-10-21T13:00:00+08:00",
               opening_mode="web_then_background", file_sha256={name: "a" * 64 for name in FILES},
               original_files={name: {"path": root + "/old-" + str(index), "sha256": "b" * 64}
                               for index, name in enumerate(FILES)},
               unit_states={name: {"active": name != "zhiming-core-reports.service",
                                   "enabled": name != "zhiming-core-reports.service"} for name in LIVE_UNITS},
               upgrade_receipt={"path": root + "/upgrade.json", "sha256": "c" * 64},
               rollback_proof={"path": root + "/restore.json", "sha256": "d" * 64})
    approval = dict(schema="b1-publication-approval-v1", operation_id=raw["operation_id"], scope="live",
                    plan_sha256=digest(raw), controller_sha256="e" * 64, action=action,
                    review_sha256=raw["review_sha256"], expires_at="2026-10-21T13:00:00+08:00",
                    model_calls=0, external_sends=0)
    return raw, approval, text


class Port:
    def __init__(self, review: bytes) -> None:
        self.text, self.calls, self.gate, self.opened, self.touched = review, [], True, None, False
        self.fail = ""
        self.value: dict[str, Any] = dict(schema=7, queues={"queued": 0, "running": 0, "leases": 0},
                                          other_sessions=0, writers_stopped=list(LIVE_UNITS))
        for name in ("identity_verified", "checksums_verified", "runtime_safe", "files_verified", "env_verified",
                     "release_verified", "rollback_ready", "maintenance", "fence_held"):
            self.value[name] = True

    def event(self, value: str) -> None:
        self.calls.append(value)
        if value == self.fail:
            raise RuntimeError("synthetic-publication-failure")

    def review(self, plan: Plan) -> bytes:
        return self.text

    def guard(self, plan: Plan) -> None:
        self.event("guard")

    def fence(self, plan: Plan) -> Any:
        self.event("fence")
        return nullcontext()

    def snapshot(self, plan: Plan, *, restored: bool = False) -> dict[str, Any]:
        self.event("snapshot")
        return dict(self.value, schema=4 if restored else self.value["schema"])

    def restore_unit(self, unit: str, *, active: bool, enabled: bool) -> None:
        self.touched = True
        self.event(f"unit:{unit}:{active}:{enabled}")

    def health(self, plan: Plan) -> None:
        self.event("health")

    def opening_checks(self, plan: Plan) -> None:
        self.event("opening_checks")

    def open_gate(self, plan: Plan, at: datetime) -> None:
        self.event("open_gate")
        self.gate, self.opened, self.touched = False, at, True

    def opened_at(self, plan: Plan) -> datetime | None:
        return self.opened

    def restore_original_files(self, plan: Plan) -> None:
        self.event("restore_original_files")

    def keep_closed(self, plan: Plan) -> None:
        self.gate = True
        self.event("keep_closed")


class PublicationTests(unittest.TestCase):
    def run_action(self, action: str = "open", *, port: Port | None = None,
                   clock: FrozenClock | None = None) -> tuple[dict[str, Any], Port]:
        raw, approval, text = fixture(action)
        port = port or Port(text)
        return execute(raw, approval, port, action=action, clock=clock or FrozenClock(NOW), controller="e" * 64), port

    def test_verify_remains_closed(self) -> None:
        result, port = self.run_action("verify")
        self.assertFalse(result["publication"])
        self.assertTrue(port.gate)
        self.assertNotIn("open_gate", port.calls)

    def test_open_order_restores_inactive_and_records_beijing(self) -> None:
        result, port = self.run_action()
        self.assertEqual(result["opened_at"], "2026-10-21T10:30:00+08:00")
        gate = port.calls.index("open_gate")
        self.assertLess(port.calls.index("opening_checks"), gate)
        self.assertLess(port.calls.index("unit:mingjingtai.service:True:True"), gate)
        self.assertGreater(port.calls.index("unit:zhiming-core-reports.service:False:False"), gate)
        self.assertFalse(result["atomic_opening"])
        self.assertFalse(result["smoke_request_performed"])

    def test_partial_failures_close_gate(self) -> None:
        for stage in ("snapshot", "health", "opening_checks", "open_gate",
                      "unit:zhiming-core-feishu.service:True:True"):
            with self.subTest(stage=stage):
                port = Port(fixture()[2])
                port.fail = stage
                with self.assertRaises(RuntimeError):
                    self.run_action(port=port)
                self.assertTrue(port.gate)
                self.assertEqual(port.calls[-1], "keep_closed")

    def test_every_readiness_dimension_is_mandatory(self) -> None:
        for key in Port(b"").value:
            with self.subTest(key=key):
                port = Port(fixture()[2])
                port.value[key] = None
                with self.assertRaises(PublicationRejected):
                    self.run_action(port=port)
                self.assertNotIn("open_gate", port.calls)

    def test_plan_changes_and_false_boolean_approval_rejected_before_host(self) -> None:
        raw, approval, text = fixture()
        for field, value in (("controller_sha256", "f" * 64), ("model_calls", False),
                             ("scope", "stage"), ("action", "verify")):
            with self.subTest(field=field):
                changed, port = dict(approval, **{field: value}), Port(text)
                with self.assertRaises(PublicationRejected):
                    execute(raw, changed, port, action="open", clock=FrozenClock(NOW), controller="e" * 64)
                self.assertFalse(port.calls)

    def test_invalid_window_offset_notice_and_exact_file_set(self) -> None:
        raw = fixture()[0]
        variants = [("window_start", "2026-10-21T10:00:00+09:00"),
                    ("review_written_at", "2026-10-21T09:00:00+08:00"), ("scope", "stage"),
                    ("file_sha256", {}), ("opening_mode", "flag_last")]
        for field, value in variants:
            with self.subTest(field=field), self.assertRaises(PublicationRejected):
                Plan.parse(dict(raw, **{field: value}))

    def test_brain_go_cannot_be_replaced_by_json_approval(self) -> None:
        raw, _, text = fixture()
        for changed in (text.replace(b"Go", b"No-Go"), text.replace(b"web_then_background", b"flag_last")):
            raw["review_sha256"] = hashlib.sha256(changed).hexdigest()
            with self.assertRaises(PublicationRejected):
                validate_review(Plan.parse(raw), changed)

    def test_window_can_expire_after_health(self) -> None:
        clock, port = FrozenClock(NOW), Port(fixture()[2])
        port.health = lambda plan: clock.advance(timedelta(hours=3))
        with self.assertRaisesRegex(PublicationRejected, "WINDOW_ENDED"):
            self.run_action(port=port, clock=clock)
        self.assertTrue(port.gate)

    def test_rollback_is_closed_config_only_and_requires_first_hour(self) -> None:
        port = Port(fixture("rollback")[2])
        port.opened = NOW - timedelta(minutes=59)
        result, port = self.run_action("rollback", port=port)
        self.assertEqual(result["status"], "rollback_configured_closed")
        self.assertTrue(port.gate)
        self.assertNotIn("open_gate", port.calls)
        port.opened = NOW - timedelta(minutes=61)
        with self.assertRaisesRegex(PublicationRejected, "FIRST_HOUR"):
            self.run_action("rollback", port=port)

    def test_default_cli_constructs_no_native_port(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            path.write_text(json.dumps(fixture()[0]), encoding="utf-8")
            with patch("sys.argv", ["publication", "--action", "open", "--plan", str(path)]), \
                    patch("tools.b1_publication_native.NativePublicationPort") as native:
                self.assertEqual(main(), 0)
                native.assert_not_called()

    def test_native_rejects_fabricated_restore_booleans(self) -> None:
        raw = fixture()[0]
        native = NativePublicationPort()
        upgrade = {"status": "quiesced_upgraded", "publication": False, "database": "zhiming_core_live",
                   "target": "/root/zhiming-core-releases/" + TARGET}
        proof = {"schema": "b1-live-rollback-proof-v1", "previous": PREVIOUS, "actual_pg_restore": True}
        with patch.object(native, "document", side_effect=[upgrade, proof]), \
                self.assertRaisesRegex(PublicationRejected, "NATIVE_PRODUCTION_RESTORE_UNAVAILABLE"):
            native.verify_evidence(Plan.parse(copy.deepcopy(raw)))
