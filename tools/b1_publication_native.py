"""Local Linux publication boundary; missing production restore keeps opening blocked.

This adapter deliberately cannot approve its own missing native rollback path.
The portable controller can be rehearsed using explicit test ports meanwhile.
"""

from __future__ import annotations

import json
import os
import platform
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from psycopg.conninfo import conninfo_to_dict

from tools.b1_publication_contracts import ENV_FILES, FILES, GATE, LOCK, MODEL_BASE, SKILL, Plan, require, stamp
from tools.b1_publication_pg import no_unknown_clients, web_client_ports
from tools.core_incremental_contracts import EXPECTED_MANIFEST, LIVE_UNITS, MIGRATIONS, PREVIOUS, TARGET, Request
from tools.core_incremental_files import HostFiles, file_sha, private_write, regular, retired_stub, wrapper
from tools.core_incremental_host import LocalCommands, local_fence, parse_env
from tools.core_incremental_pg import CommandRunner, PostgresPort


class NativePublicationPort:
    def __init__(
        self, *, files: HostFiles | None = None, runner: CommandRunner | None = None, database: Any = None,
        host_probe: Callable[[], tuple[str, int, str]] | None = None,
        fence: Callable[[Path], AbstractContextManager[None]] = local_fence,
    ) -> None:
        self.files, self.runner, self.database = files or HostFiles(), runner or LocalCommands(), database
        self.host_probe = host_probe or (
            lambda: (platform.system(), getattr(os, "geteuid", lambda: -1)(), platform.node()))
        self.lock, self.held, self.touched = fence, False, False

    def request(self, plan: Plan) -> Request:
        return Request(plan.operation_id, "live", plan.hostname, EXPECTED_MANIFEST, "0" * 64, (),
                       8 * 1024**3, {}, "0" * 64)

    def review(self, plan: Plan) -> bytes:
        path = self.files.path(plan.raw["review_file"])
        regular(path, private=True)
        return path.read_bytes()

    def guard(self, plan: Plan) -> None:
        require(self.host_probe() == ("Linux", 0, plan.hostname), "AUTHORIZED_LOCAL_HOST_REQUIRED")
        root = self.files.path(plan.operation_dir)
        require(root.is_dir() and not root.is_symlink() and root.stat().st_mode & 0o077 == 0,
                "OPERATION_DIRECTORY_MODE")
        regular(self.files.path(GATE))
        require(not (root / "publication-opened.json").exists(), "ALREADY_OPENED_OR_RECOVERY_REQUIRED")

    @contextmanager
    def fence(self, plan: Plan) -> Iterator[None]:
        with self.lock(self.files.path(LOCK)):
            self.held = True
            try:
                yield
            finally:
                self.held = False

    def document(self, record: dict[str, str]) -> dict[str, Any]:
        path = self.files.path(record["path"])
        regular(path, private=True)
        require(file_sha(path) == record["sha256"], "PUBLICATION_EVIDENCE_CHANGED")
        value = json.loads(path.read_text(encoding="utf-8"))
        require(isinstance(value, dict), "PUBLICATION_EVIDENCE_FORMAT")
        return value

    def verify_evidence(self, plan: Plan) -> None:
        upgrade = self.document(plan.raw["upgrade_receipt"])
        require(upgrade.get("status") == "quiesced_upgraded" and upgrade.get("publication") is False
                and upgrade.get("database") == "zhiming_core_live"
                and upgrade.get("target") == self.request(plan).release, "UPGRADE_RECEIPT")
        proof = self.document(plan.raw["rollback_proof"])
        require(proof.get("schema") == "b1-live-rollback-proof-v1" and proof.get("previous") == PREVIOUS,
                "LIVE_ROLLBACK_PROOF_REQUIRED")
        # No current tool implements authorized restore-to-new-live-DB + latest
        # ledger/rebinding/old-package checks. JSON booleans cannot fill that gap.
        require(False, "NATIVE_PRODUCTION_RESTORE_UNAVAILABLE")

    def verify_files(self, plan: Plan) -> None:
        for name in FILES:
            path = self.files.path(name)
            regular(path, private=name in ENV_FILES or name.startswith(SKILL + "/"))
            require(file_sha(path) == plan.raw["file_sha256"][name], "PUBLICATION_FILE_CHANGED")
            saved = plan.raw["original_files"][name]
            original = self.files.path(saved["path"])
            regular(original, private=True)
            require(file_sha(original) == saved["sha256"], "PUBLICATION_BACKUP_CHANGED")
        self.files.release(self.request(plan))
        self.verify_skill(plan)

    def verify_skill(self, plan: Plan) -> None:
        root = self.files.path(SKILL)
        manifest = json.loads((root / "__core_skill_manifest__.json").read_text(encoding="utf-8"))
        require(manifest.get("schema") == "core3-hermes-skill-incremental-v1"
                and manifest.get("commit") == TARGET and manifest.get("previous_commit") == PREVIOUS
                and manifest.get("source_manifest_sha256") == EXPECTED_MANIFEST
                and manifest.get("env_files") == list(ENV_FILES)
                and manifest.get("original_skill_manifest_preserved") is True, "PUBLICATION_SKILL_SOURCE")
        rows = manifest.get("files", {})
        require({"SKILL.md", "core_consultation.py"} <= set(rows), "PUBLICATION_SKILL_FILES")
        require({path.name for path in root.glob("*.py")} == {name for name in rows if name.endswith(".py")},
                "PUBLICATION_UNKNOWN_SKILL")
        for name, row in rows.items():
            require(Path(name).name == name and name not in {".", ".."}, "PUBLICATION_SKILL_MEMBER")
            path = root / name
            regular(path, private=True)
            require(file_sha(path) == row.get("sha256"), "PUBLICATION_SKILL_CHANGED")
            if name not in {"SKILL.md", "core_consultation.py"}:
                require(path.read_bytes() == retired_stub(), "LEGACY_ENTRY_NOT_RETIRED")
        require((root / "core_consultation.py").read_bytes() == wrapper(self.request(plan)), "UNREVIEWED_WRAPPER")
        self.verify_retirement_backup(manifest.get("original_retirement_backup", {}))

    def verify_retirement_backup(self, record: dict[str, Any]) -> None:
        name = record.get("backup_path", "")
        require(isinstance(name, str) and name.startswith("/root/zhiming-core-backups/")
                and Path(name).name == "hermes-skill", "ORIGINAL_RETIREMENT_BACKUP_MISSING")
        root = self.files.path(name)
        manifest = root / "__hermes_skill_backup__.json"
        regular(manifest, private=True)
        require(file_sha(manifest) == record.get("backup_manifest_sha256"), "ORIGINAL_RETIREMENT_BACKUP_CHANGED")
        value = json.loads(manifest.read_text(encoding="utf-8"))
        require(value.get("schema") == "core3-hermes-skill-backup-v1" and isinstance(value.get("files"), dict),
                "ORIGINAL_RETIREMENT_BACKUP_FORMAT")
        for item, row in value["files"].items():
            require(Path(item).name == item and item not in {".", ".."}, "ORIGINAL_RETIREMENT_BACKUP_MEMBER")
            path = root / item
            regular(path, private=True)
            require(file_sha(path) == row.get("sha256"), "ORIGINAL_RETIREMENT_BACKUP_CHANGED")

    def environment(self) -> dict[str, str]:
        values = {}
        for name in ENV_FILES:
            values.update(parse_env(self.files.path(name)))
        fields = conninfo_to_dict(values.get("ZHIMING_DATABASE_URL", ""))
        require(fields.get("host") in {"127.0.0.1", "::1"} and fields.get("port", "5432") == "5432"
                and fields.get("dbname") == "zhiming_core_live"
                and fields.get("user") == "zhiming_core_live_writer", "PUBLICATION_RUNTIME_DATABASE")
        require(values.get("KIMI_MODEL") == "k3" and values.get("KIMI_BASE_URL") == MODEL_BASE,
                "PUBLICATION_MODEL_CHANGED")
        require(values.get("CHART_PYTHON") == self.request_release() + "/venv/charts/bin/python",
                "PUBLICATION_CHART_PYTHON")
        require(not values.get("MODELS_CONFIG") and not values.get("MINGJING_MODEL_PORT"), "NEW_MODEL_PORT_ENABLED")
        require(values.get("LANGSMITH_TRACING", "false").lower() == "false", "TRACING_ENABLED")
        return values

    @staticmethod
    def request_release() -> str:
        return "/root/zhiming-core-releases/" + TARGET

    def unit(self, name: str) -> dict[str, str]:
        require(name in LIVE_UNITS, "PUBLICATION_UNIT_NOT_ALLOWED")
        properties = "ActiveState,UnitFileState,FragmentPath,DropInPaths,NeedDaemonReload,KillMode,SendSIGKILL,MainPID"
        raw = self.runner.run(["systemctl", "show", name, "--property=" + properties])
        value = dict(line.split("=", 1) for line in raw.decode().splitlines() if "=" in line)
        require(value.get("FragmentPath") == "/etc/systemd/system/" + name and not value.get("DropInPaths")
                and value.get("NeedDaemonReload") == "no", "UNREVIEWED_EFFECTIVE_UNIT")
        if name.endswith(".service"):
            require(value.get("KillMode") in {"mixed", "control-group"} and value.get("SendSIGKILL") == "yes",
                    "UNFENCED_SERVICE_CHILDREN")
        return value

    def db(self, plan: Plan) -> Any:
        self.database = self.database or PostgresPort(self.request(plan), self.runner)
        return self.database

    def snapshot(self, plan: Plan, *, restored: bool = False) -> dict[str, Any]:
        require(not restored, "NATIVE_PRODUCTION_RESTORE_UNAVAILABLE")
        self.verify_files(plan)
        self.environment()
        self.verify_evidence(plan)
        value = self.db(plan).snapshot(migrated=True)
        stopped = [name for name in LIVE_UNITS if self.unit(name).get("ActiveState") in {"inactive", "failed"}]
        return dict(schema=7, identity_verified=True, checksums_verified=value["checksums"] == MIGRATIONS,
                    runtime_safe=value["runtime_safe"] and value["new_tables_crud"], files_verified=True,
                    env_verified=True, release_verified=True, rollback_ready=False,
                    maintenance=self.files.path(GATE).is_file(), fence_held=self.held,
                    queues=value["queues"], other_sessions=value["other_database_sessions"], writers_stopped=stopped)

    def restore_unit(self, unit: str, *, active: bool, enabled: bool) -> None:
        require(unit in LIVE_UNITS and self.held, "PUBLICATION_FENCE_REQUIRED")
        self.touched = True
        self.runner.run(["systemctl", "enable" if enabled else "disable", unit])
        self.runner.run(["systemctl", "start" if active else "stop", unit])
        state = self.unit(unit)
        require((state.get("ActiveState") == "active") == active, "UNIT_ACTIVATION_FAILED")
        require((state.get("UnitFileState") in {"enabled", "enabled-runtime"}) == enabled,
                "UNIT_ENABLE_STATE_CHANGED")

    def health(self, plan: Plan) -> None:
        values = self.environment()
        require(values.get("MINGJING_TOKEN"), "WEB_HEALTH_TOKEN_MISSING")
        request = urllib.request.Request("http://127.0.0.1:8787/api/health",
                                         headers={"X-Token": values["MINGJING_TOKEN"]})
        # No redirects/proxies; token must never leave this exact loopback endpoint.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=5) as response:
            require(response.status == 200, "WEB_HEALTH_FAILED")
            value = json.loads(response.read(8192))
        require(value.get("ok") is True and value.get("database") == "postgresql"
                and value.get("context_version") == "core3.0" and value.get("model") == "k3", "WEB_HEALTH_FAILED")

    def opening_checks(self, plan: Plan) -> None:
        require(self.held and self.files.path(GATE).is_file(), "OPENING_FENCE_LOST")
        self.verify_files(plan)
        self.environment()
        self.verify_evidence(plan)
        for name in LIVE_UNITS[1:]:
            require(self.unit(name).get("ActiveState") in {"inactive", "failed"}, "BACKGROUND_WRITER_ACTIVE")
        value = self.db(plan).snapshot(migrated=True)
        require(value["queues"] == {"queued": 0, "running": 0, "leases": 0}, "OPENING_NONEMPTY_QUEUE")
        pid = int(self.unit("mingjingtai.service").get("MainPID", "0"))
        no_unknown_clients(self.db(plan), web_client_ports(pid))

    def open_gate(self, plan: Plan, at: datetime) -> None:
        require(self.held, "PUBLICATION_FENCE_REQUIRED")
        path = self.files.path(GATE)
        regular(path)
        self.touched = True
        # Conservatively start the rollback clock before removal, never after it.
        private_write(self.files.path(plan.operation_dir) / "publication-opened.json",
                      json.dumps({"opened_at": at.isoformat(), "gate_removal_attempted": True}).encode())
        path.unlink()

    def opened_at(self, plan: Plan) -> datetime | None:
        path = self.files.path(plan.operation_dir) / "publication-opened.json"
        if not path.exists():
            return None
        regular(path, private=True)
        return stamp(json.loads(path.read_text())["opened_at"])

    def restore_original_files(self, plan: Plan) -> None:
        require(False, "NATIVE_PRODUCTION_RESTORE_UNAVAILABLE")

    def keep_closed(self, plan: Plan) -> None:
        self.touched = True
        gate = self.files.path(GATE)
        if not gate.exists():
            private_write(gate, b"B1 publication failed; maintenance retained.\n")
        failed = False
        for name in LIVE_UNITS:
            try:
                self.runner.run(["systemctl", "disable", "--now", name])
                self.runner.run(["systemctl", "stop", name])
            except BaseException:
                failed = True
        require(not failed, "PUBLICATION_STOP_INCOMPLETE")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None
