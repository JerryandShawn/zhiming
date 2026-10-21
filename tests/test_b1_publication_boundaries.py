"""Synthetic proc/commands plus real temporary files; not a Linux-mode proof."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from test_b1_publication_contracts import NOW, Port, fixture

from tools.b1_publication import main
from tools.b1_publication_contracts import GATE, Plan, PublicationRejected, ZONE
from tools.b1_publication_native import NativePublicationPort, NoRedirect
from tools.b1_publication_pg import no_unknown_clients, web_client_ports
from tools.core_incremental_files import HostFiles


class Rows:
    def __init__(self, value: list[dict[str, Any]]) -> None:
        self.value = value

    def __enter__(self) -> Rows:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def execute(self, query: str) -> Rows:
        return self

    def fetchall(self) -> list[dict[str, Any]]:
        return self.value


class Database:
    def __init__(self, values: list[dict[str, Any]]) -> None:
        self.values = values

    def _connection(self, role: str) -> Rows:
        return Rows(self.values)


class BoundaryTests(unittest.TestCase):
    def test_web_socket_mapping_includes_children_and_excludes_other_sockets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory)
            links = {}
            for pid, children, inode in ((42, "43", "101"), (43, "", "102")):
                root = proc / str(pid)
                child = root / "task" / str(pid) / "children"
                child.parent.mkdir(parents=True)
                child.write_text(children)
                descriptor = root / "fd" / "3"
                descriptor.parent.mkdir()
                descriptor.touch()
                links[str(descriptor)] = f"socket:[{inode}]"
            (proc / "net").mkdir()
            rows = ["header", "0: 0100007F:C001 0100007F:1538 01 0 0 0 0 0 101",
                    "1: 0100007F:C002 0100007F:1538 01 0 0 0 0 0 102",
                    "2: 0100007F:C003 0100007F:1538 01 0 0 0 0 0 103",
                    "3: 0100007F:C004 0100007F:0050 01 0 0 0 0 0 101"]
            (proc / "net" / "tcp").write_text("\n".join(rows))
            (proc / "net" / "tcp6").write_text("header\n")
            with patch("tools.b1_publication_pg.os.readlink", side_effect=lambda path: links[str(path)]):
                self.assertEqual(web_client_ports(42, proc), {49153, 49154})

    def test_unknown_web_pid_and_missing_proc_fail(self) -> None:
        with self.assertRaises(PublicationRejected):
            web_client_ports(0)
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(FileNotFoundError):
            web_client_ports(42, Path(directory))

    def test_catalog_clients_require_exact_role_host_and_pid_owned_port(self) -> None:
        valid = {"usename": "zhiming_core_live_writer", "host": "127.0.0.1", "client_port": 49153}
        no_unknown_clients(Database([valid]), {49153})
        for key, value in (("usename", "zhiming_core_live_owner"), ("host", "192.0.2.1"), ("client_port", 49154)):
            with self.subTest(key=key), self.assertRaises(PublicationRejected):
                no_unknown_clients(Database([dict(valid, **{key: value})]), {49153})

    def test_native_guard_denies_wrong_os_user_or_hostname(self) -> None:
        plan = Plan.parse(fixture()[0])
        for identity in (("Windows", 0, plan.hostname), ("Linux", 1, plan.hostname), ("Linux", 0, "wrong-host")):
            with self.subTest(identity=identity), self.assertRaisesRegex(PublicationRejected, "LOCAL_HOST"):
                NativePublicationPort(host_probe=lambda: identity).guard(plan)

    def test_real_file_open_records_before_gate_and_never_overwrites_record(self) -> None:
        plan = Plan.parse(fixture()[0])
        with tempfile.TemporaryDirectory() as directory:
            files = HostFiles(Path(directory))
            gate = files.path(GATE)
            gate.parent.mkdir(parents=True)
            gate.write_bytes(b"closed")
            files.path(plan.operation_dir).mkdir(parents=True)
            port = NativePublicationPort(files=files)
            port.held = True
            port.open_gate(plan, NOW.astimezone(ZONE))
            self.assertFalse(gate.exists())
            record = files.path(plan.operation_dir) / "publication-opened.json"
            self.assertEqual(json.loads(record.read_text())["opened_at"], "2026-10-21T10:30:00+08:00")
            gate.write_bytes(b"closed-again")
            with self.assertRaises(RuntimeError):
                port.open_gate(plan, NOW.astimezone(ZONE))
            self.assertTrue(gate.exists())

    def test_private_record_write_failure_never_removes_gate(self) -> None:
        plan = Plan.parse(fixture()[0])
        with tempfile.TemporaryDirectory() as directory:
            files = HostFiles(Path(directory))
            gate = files.path(GATE)
            gate.parent.mkdir(parents=True)
            gate.write_bytes(b"closed")
            port = NativePublicationPort(files=files)
            port.held = True
            with patch("tools.b1_publication_native.private_write", side_effect=OSError("synthetic-disk-full")), \
                    self.assertRaises(OSError):
                port.open_gate(plan, NOW.astimezone(ZONE))
            self.assertEqual(gate.read_bytes(), b"closed")

    def test_receipt_write_failure_after_open_keeps_closed(self) -> None:
        raw, approval, text = fixture()
        port = Port(text)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, document in (("plan", raw), ("approval", approval)):
                (root / (name + ".json")).write_text(json.dumps(document))
            argv = ["publication", "--action", "open", "--plan", str(root / "plan.json"), "--apply", "--native",
                    "--approval", str(root / "approval.json"), "--output", str(root / "result.json")]
            # The CLI's private-mode test is modeled; no POSIX claim on Windows.
            native_name = "tools.b1_publication_native.NativePublicationPort"
            with patch("sys.argv", argv), patch(native_name, return_value=port), \
                    patch("tools.core_incremental_files.regular"), \
                    patch("tools.b1_publication.execute", return_value={"status": "opened"}), \
                    patch("tools.core_incremental_files.private_write", side_effect=OSError("synthetic-disk-full")):
                port.gate, port.touched = False, True
                self.assertEqual(main(), 2)
            self.assertTrue(port.gate)
            self.assertEqual(port.calls, ["keep_closed"])

    def test_health_redirect_is_refused(self) -> None:
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://invalid.test"))
