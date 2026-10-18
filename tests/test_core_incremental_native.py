"""Native adapter control flow with injected commands/PG/lock and a synthetic filesystem."""

from __future__ import annotations

import json
import tempfile
import unittest
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from test_core_incremental_upgrade import Sandbox, fixture

from tools.core_incremental_contracts import (
    MODEL_BASE,
    PREVIOUS,
    TARGET,
    Request,
    UpgradeRejected,
)
from tools.core_incremental_files import (
    ENV_FILES,
    HostFiles,
    file_sha,
    previous_wrapper,
    private_write,
    regular,
    retarget_skill,
    retired_stub,
    verify_skill,
)
from tools.core_incremental_host import LocalCommands, NativePort

REPO = Path(__file__).resolve().parents[1]


class FakeCommands:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.fail = ""

    def run(
        self,
        args: list[str],
        *,
        env: Mapping[str, str] | None = None,
        stdin: str | None = None,
        output: Path | None = None,
    ) -> bytes:
        self.calls.append(args)
        if self.fail and self.fail in args:
            raise UpgradeRejected("SYNTHETIC_HOST_FAILURE")
        if "show" in args:
            if any("--property=FragmentPath" in part for part in args):
                return (
                    f"FragmentPath=/etc/systemd/system/{args[2]}\nDropInPaths=\nNeedDaemonReload=no\n"
                    "KillMode=control-group\nSendSIGKILL=yes\n"
                ).encode()
            return (
                f"ActiveState=inactive\nUnitFileState=disabled\nFragmentPath=/etc/systemd/system/{args[2]}\n"
                "DropInPaths=\nNeedDaemonReload=no\n"
            ).encode()
        return b""


class FakeDatabase:
    def __init__(self, request: Request) -> None:
        self.box = Sandbox(request)

    def snapshot(self, *, migrated: bool) -> dict[str, Any]:
        return self.box.snapshot(self.box.request, migrated=migrated)

    def dump(self, output: Path) -> None:
        private_write(output, b"SYNTHETIC-CUSTOM-DUMP-NOT-REAL-PG")

    def withdrawals(self) -> dict[str, Any]:
        return {
            "schema": "core3-withdrawals-v2",
            "owners": [],
            "tarot_requests": [],
            "deleted_draws": [],
            "delivery_receipts": [],
        }

    def migrate_and_grant(self) -> None:
        self.box.migrate_and_grant(self.box.request)

    def backfill(self, owner: str, *, apply: bool) -> dict[str, Any]:
        return self.box.backfill(self.box.request, owner, apply=apply)


@contextmanager
def fake_fence(path: Path) -> Iterator[None]:
    yield


class NativeAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        # Windows cannot attest POSIX mode bits. This fixture explicitly models
        # a trusted mode-0600 filesystem; actual Linux modes remain a stage gate.
        for target in (
            "tools.core_incremental_files.regular",
            "tools.core_incremental_host.regular",
        ):
            policy = patch(
                target,
                side_effect=lambda path, private=False: regular(path, private=False),
            )
            policy.start()
            self.addCleanup(policy.stop)
        for target in (
            "subprocess.run",
            "socket.create_connection",
            "urllib.request.urlopen",
            "os.system",
            "os.execv",
        ):
            blocker = patch(target, side_effect=AssertionError("OFFLINE_NATIVE_ESCAPE"))
            blocker.start()
            self.addCleanup(blocker.stop)
        self.raw, _ = fixture("live")
        capacity = patch(
            "tools.core_incremental_host.shutil.disk_usage",
            return_value=SimpleNamespace(free=12 * 1024**3),
        )
        capacity.start()
        self.addCleanup(capacity.stop)
        self.request = Request.parse(self.raw)
        self.files = HostFiles(self.root)
        self._release()
        self._units()
        self._skill()
        self.config = self._environments()
        nginx = self.files.path("/www/server/panel/vhost/nginx/p.jerrymeng.asia.conf")
        private_write(nginx, b"# SYNTHETIC core-maintenance.flag\n")
        self.config["nginx_sha256"] = file_sha(nginx)
        self.commands = FakeCommands()
        self.database = FakeDatabase(self.request)
        self.port = NativePort(
            self.request,
            self.config,
            runner=self.commands,
            database=self.database,
            files=self.files,
            host_probe=lambda: ("Linux", 0, self.request.hostname),
            fence=fake_fence,
        )

    def _release(self) -> None:
        root = self.files.path(self.request.release)
        rows = {}
        for source in (REPO / "mingjing_core/repositories/migrations").glob("*.sql"):
            name = "mingjing_core/repositories/migrations/" + source.name
            private_write(root / name, source.read_bytes())
            rows[name] = {"sha256": file_sha(root / name)}
        private_write(root / "hermes/SKILL.md", b"Synthetic fixed candidate skill\n")
        rows["hermes/SKILL.md"] = {"sha256": file_sha(root / "hermes/SKILL.md")}
        name = "tools/deploy_core.py"
        private_write(root / name, (REPO / name).read_bytes())
        rows[name] = {"sha256": file_sha(root / name)}
        manifest = {"schema": "core3-release-v1", "commit": TARGET, "files": rows}
        private_write(root / "__release_manifest__.json", json.dumps(manifest).encode())
        sha = file_sha(root / "__release_manifest__.json")
        self.request = replace(self.request, manifest_sha256=sha)
        old = self.files.path("/root/zhiming-core-releases/" + PREVIOUS)
        private_write(old / name, (REPO / name).read_bytes())
        private_write(
            old / "__release_manifest__.json",
            json.dumps({"commit": PREVIOUS, "files": {name: rows[name]}}).encode(),
        )
        self.files = HostFiles(
            self.root,
            approved_manifest=sha,
            previous_manifest=file_sha(old / "__release_manifest__.json"),
        )

    def _units(self) -> None:
        hashes = {}
        for name in self.request.units:
            path = self.files.path("/etc/systemd/system/" + name)
            private_write(
                path,
                ("# synthetic\nExecStart=/root/zhiming-core-releases/" + PREVIOUS + "/venv/core/bin/python\n").encode(),
            )
            hashes[name] = file_sha(path)
        self.request = replace(self.request, unit_sha256=hashes)

    def _skill(self) -> None:
        skill = self.files.path("/root/.hermes/skills/zhiming")
        members = {
            "SKILL.md": b"Synthetic prior skill\n",
            "core_consultation.py": previous_wrapper(),
            "chat_agent.py": retired_stub(),
            "v6_agent.py": retired_stub(),
        }
        for name, content in members.items():
            private_write(skill / name, content)
        original = "/root/zhiming-core-backups/synthetic-old/hermes-skill"
        private_write(self.files.path(original) / "SKILL.md", b"Synthetic historical original\n")
        saved = {
            "schema": "core3-hermes-skill-backup-v1",
            "commit": PREVIOUS,
            "files": {"SKILL.md": {"sha256": file_sha(self.files.path(original) / "SKILL.md")}},
        }
        saved_path = self.files.path(original) / "__hermes_skill_backup__.json"
        private_write(saved_path, json.dumps(saved).encode())
        manifest = {
            "schema": "core3-hermes-skill-v1",
            "commit": PREVIOUS,
            "release_dir": "/root/zhiming-core-releases/" + PREVIOUS,
            "env_files": list(ENV_FILES),
            "backup_path": original,
            "backup_manifest_sha256": file_sha(saved_path),
            "files": {name: {"sha256": file_sha(skill / name)} for name in members},
        }
        path = skill / "__core_skill_manifest__.json"
        private_write(path, json.dumps(manifest).encode())
        self.request = replace(self.request, skill_manifest_sha256=file_sha(path))

    def _environments(self) -> dict[str, Any]:
        hashes = {}
        for index, name in enumerate(ENV_FILES):
            text = "# Synthetic configuration\n"
            if index == 1:
                text += f"KIMI_MODEL=k3\nKIMI_BASE_URL={MODEL_BASE}\nLANGSMITH_TRACING=false\n"
                text += f"ZHIMING_DATABASE_URL=postgresql://{self.request.database}_writer@127.0.0.1:5432/{self.request.database}\n"
            private_write(self.files.path(name), text.encode())
            hashes[name] = file_sha(self.files.path(name))
        return {"env_files_sha256": hashes}

    def test_pinned_release_rejects_changed_source_and_extra_file(
        self,
    ) -> None:
        self.files.release(self.request)
        extra = self.files.path(self.request.release) / "unexpected.py"
        private_write(extra, b"raise RuntimeError('SYNTHETIC')")
        with self.assertRaisesRegex(UpgradeRejected, "UNEXPECTED_RELEASE_FILE"):
            self.files.release(self.request)
        extra.unlink()
        source = self.files.path(self.request.release) / "hermes/SKILL.md"
        source.write_bytes(b"Changed synthetic source")
        with self.assertRaisesRegex(UpgradeRejected, "RELEASE_FILE_CHANGED"):
            self.files.release(self.request)

    def test_host_guard_failure_has_no_commands_or_gate(self) -> None:
        self.port.host_probe = lambda: ("Windows", -1, self.request.hostname)
        with (
            self.assertRaisesRegex(UpgradeRejected, "AUTHORIZED_LOCAL_HOST_REQUIRED"),
            self.port.quiesce(self.request),
        ):
            self.fail("must reject")
        self.assertEqual(self.commands.calls, [])
        self.assertFalse(self.port.gate.exists())

    def test_native_quiesced_backup_and_hash_check_use_only_injected_ports(
        self,
    ) -> None:
        with self.port.quiesce(self.request):
            self.assertTrue(self.port.held)
            before = self.port.snapshot(self.request, migrated=False)
            backup = self.port.backup(self.request, before)
            self.port.verify_backup_files(backup)
            (self.port.op / "before.dump").write_bytes(b"changed")
            with self.assertRaisesRegex(UpgradeRejected, "BACKUP_FILE_CHANGED"):
                self.port.verify_backup_files(backup)
        self.port.keep_closed(self.request)
        self.assertTrue(self.port.gate.exists())
        self.assertFalse(self.port.held)
        self.assertFalse(
            any("ssh" in part or part in {"start", "restart", "enable"} for row in self.commands.calls for part in row)
        )

    def test_hermes_manifest_last_retarget_preserves_stub_original_and_load_order(
        self,
    ) -> None:
        original = self.files.path("/root/zhiming-core-backups/synthetic-old/hermes-skill/SKILL.md").read_bytes()
        stub = self.files.path("/root/.hermes/skills/zhiming/chat_agent.py").read_bytes()
        with self.port.quiesce(self.request):
            result = self.port.retarget(self.request)
        self.assertTrue(result["hermes_retired_preserved"])
        self.assertFalse(result["hermes_restarted"])
        self.assertEqual(
            self.files.path("/root/.hermes/skills/zhiming/chat_agent.py").read_bytes(),
            stub,
        )
        self.assertEqual(
            self.files.path("/root/zhiming-core-backups/synthetic-old/hermes-skill/SKILL.md").read_bytes(),
            original,
        )
        manifest = json.loads(self.files.path("/root/.hermes/skills/zhiming/__core_skill_manifest__.json").read_text())
        self.assertEqual(manifest["env_files"], list(ENV_FILES))
        self.assertEqual(manifest["commit"], TARGET)
        self.assertEqual(manifest["previous_commit"], PREVIOUS)
        compile(
            self.files.path("/root/.hermes/skills/zhiming/core_consultation.py").read_bytes(),
            "synthetic-wrapper",
            "exec",
        )
        self.assertIn(["systemctl", "daemon-reload"], self.commands.calls)

    def test_unknown_skill_or_changed_original_backup_blocks_before_retarget(
        self,
    ) -> None:
        skill = self.files.path("/root/.hermes/skills/zhiming")
        private_write(skill / "unknown.py", b"# synthetic unexpected source")
        with self.assertRaisesRegex(UpgradeRejected, "UNKNOWN_SKILL_CODE"):
            verify_skill(self.files, self.request)
        (skill / "unknown.py").unlink()
        saved = self.files.path("/root/zhiming-core-backups/synthetic-old/hermes-skill/SKILL.md")
        saved.write_bytes(b"changed")
        with self.assertRaisesRegex(UpgradeRejected, "ORIGINAL_SKILL_BACKUP_CHANGED"):
            retarget_skill(self.files, self.request, self.root / "retarget")

    def test_shutdown_attempts_every_writer_even_when_one_command_fails(self) -> None:
        self.commands.fail = self.request.units[0]
        with self.assertRaisesRegex(UpgradeRejected, "WRITER_SHUTDOWN_INCOMPLETE"):
            self.port.stop()
        stopped = {args[-1] for args in self.commands.calls if "stop" in args}
        self.assertEqual(stopped, set(self.request.units))

    def test_real_runner_rejects_arbitrary_shell_ssh_and_python_before_subprocess(
        self,
    ) -> None:
        runner = LocalCommands()
        for args in (
            ["ssh", "invalid"],
            ["sh", "-c", "invalid"],
            ["python", "-c", "invalid"],
        ):
            with (
                self.subTest(args=args),
                self.assertRaisesRegex(UpgradeRejected, "HOST_COMMAND_NOT_ALLOWED"),
            ):
                runner.run(args)

    def test_effective_dropin_and_unfenced_children_rejected_before_gate(self) -> None:
        original = self.commands.run
        for before, after in (
            (b"DropInPaths=\n", b"DropInPaths=/run/synthetic.conf\n"),
            (b"KillMode=control-group", b"KillMode=process"),
        ):
            with (
                self.subTest(after=after),
                patch.object(
                    self.commands,
                    "run",
                    side_effect=lambda *args, before=before, after=after, **kwargs: original(*args, **kwargs).replace(
                        before, after
                    ),
                ),
                self.assertRaises(UpgradeRejected),
            ):
                self.port.source_checks()
        self.assertFalse(self.port.gate.exists())

    def test_old_fence_modified_even_with_rehashed_old_manifest_is_rejected(
        self,
    ) -> None:
        root = self.files.path("/root/zhiming-core-releases/" + PREVIOUS)
        source = root / "tools/deploy_core.py"
        source.write_bytes(source.read_bytes().replace(b"if Path(MAINTENANCE).exists():", b"if False:"))
        path = root / "__release_manifest__.json"
        document = json.loads(path.read_text())
        document["files"]["tools/deploy_core.py"]["sha256"] = file_sha(source)
        path.write_text(json.dumps(document))
        self.files.previous_manifest = file_sha(path)
        with self.assertRaisesRegex(UpgradeRejected, "UNREVIEWED_PREVIOUS_FENCE"):
            self.files.verify_previous_fence(self.request)

    def test_existing_wrapper_template_is_identical_to_pinned_legacy_generator(
        self,
    ) -> None:
        from tools.deploy_core import skill_wrapper

        args = SimpleNamespace(
            commit=PREVIOUS,
            release_dir="/root/zhiming-core-releases/" + PREVIOUS,
            env_file=list(ENV_FILES),
        )
        self.assertEqual(previous_wrapper(), skill_wrapper(args))


if __name__ == "__main__":
    unittest.main()
