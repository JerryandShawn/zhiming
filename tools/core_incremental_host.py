"""Authorized local-host adapter; no SSH, publication, provider or channel command."""

from __future__ import annotations

import json
import os
import platform
import shlex
import shutil
import subprocess
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Any

from psycopg.conninfo import conninfo_to_dict

from tools.core_incremental_contracts import (
    MIGRATIONS,
    MODEL_BASE,
    PREVIOUS,
    TARGET,
    Request,
    require,
)
from tools.core_incremental_environment import chart_environment
from tools.core_incremental_files import (
    ENV_FILES,
    HostFiles,
    file_sha,
    private_write,
    regular,
    retarget_skill,
    verify_skill,
)
from tools.core_incremental_pg import CommandRunner, PostgresPort


class LocalCommands:
    def run(
        self,
        args: list[str],
        *,
        env: Mapping[str, str] | None = None,
        stdin: str | None = None,
        output: Path | None = None,
    ) -> bytes:
        from tools.core_incremental_binaries import executable

        command = [executable(args[0]), *args[1:]]
        if output is None:
            result = subprocess.run(
                command,
                env=env,
                input=stdin.encode() if stdin else None,
                capture_output=True,
                check=False,
                timeout=60,
            )
        else:
            descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                result = subprocess.run(
                    command,
                    env=env,
                    stdout=stream,
                    stderr=subprocess.PIPE,
                    check=False,
                    timeout=60,
                )
        allow_missing = args[:2] == ["systemctl", "show"] and result.returncode == 4
        require(result.returncode == 0 or allow_missing, "HOST_COMMAND_FAILED")
        return result.stdout or b""


def parse_env(path: Path) -> dict[str, str]:
    regular(path, private=True)
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        require(separator and key.replace("_", "a").isalnum(), "ENVIRONMENT_FORMAT")
        if value.startswith(("'", '"')):
            tokens = shlex.split(value, comments=False)
            require(len(tokens) == 1, "ENVIRONMENT_FORMAT")
            value = tokens[0]
        else:
            require(not any(char.isspace() for char in value), "ENVIRONMENT_FORMAT")
        result[key] = value
    return result


@contextmanager
def local_fence(path: Path) -> Iterator[None]:
    import fcntl

    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


class NativePort:
    def __init__(
        self,
        request: Request,
        config: dict[str, Any],
        *,
        runner: CommandRunner | None = None,
        database: Any = None,
        files: HostFiles | None = None,
        host_probe: Callable[[], tuple[str, int, str]] | None = None,
        fence: Callable[[Path], AbstractContextManager[None]] = local_fence,
    ) -> None:
        self.request, self.config = request, config
        self.runner, self.files = runner or LocalCommands(), files or HostFiles()
        self.database = database
        self.host_probe = host_probe or (
            lambda: (
                platform.system(),
                getattr(os, "geteuid", lambda: -1)(),
                platform.node(),
            )
        )
        self.fence = fence
        self.started, self.held = False, False
        self.op = self.files.path("/root/zhiming-core-backups/incremental-" + request.operation_id)
        self.gate = self.files.path(
            "/www/wwwroot/p-acme/core-maintenance.flag"
            if request.scope == "live"
            else "/root/zhiming-core-b1-stage/maintenance.flag"
        )
        self.retargeted = False
        self.new_unit_hashes: dict[str, str] = {}

    def guard(self) -> None:
        require(self.host_probe() == ("Linux", 0, self.request.hostname), "AUTHORIZED_LOCAL_HOST_REQUIRED")

    def source_checks(self) -> None:
        require(set(self.config) <= {"env_files_sha256", "nginx_sha256"}, "UNKNOWN_HOST_CONFIG")
        self.files.release(self.request)
        self.files.verify_units(self.request)
        if self.request.scope == "live":
            verify_skill(self.files, self.request)
            self.files.verify_previous_fence(self.request)
            nginx = self.files.path("/www/server/panel/vhost/nginx/p.jerrymeng.asia.conf")
            regular(nginx)
            require(file_sha(nginx) == self.config.get("nginx_sha256"), "NGINX_CHANGED")
            require("core-maintenance.flag" in nginx.read_text(encoding="utf-8"), "MAINTENANCE_GATE_MISSING")
        for name, expected in self.request.unit_sha256.items():
            if expected != "absent":
                raw = self.runner.run(
                    [
                        "systemctl",
                        "show",
                        name,
                        "--property=FragmentPath,DropInPaths,NeedDaemonReload,KillMode,SendSIGKILL",
                    ]
                )
                values = dict(line.split("=", 1) for line in raw.decode().splitlines() if "=" in line)
                require(
                    values.get("FragmentPath") == "/etc/systemd/system/" + name
                    and not values.get("DropInPaths")
                    and values.get("NeedDaemonReload") == "no",
                    "UNREVIEWED_EFFECTIVE_UNIT",
                )
                if name.endswith(".service"):
                    require(
                        values.get("KillMode") in {"control-group", "mixed"} and values.get("SendSIGKILL") == "yes",
                        "UNFENCED_SERVICE_CHILDREN",
                    )
        require(self.model() == {"model": "k3", "base": MODEL_BASE, "new_port": False}, "MODEL_CONFIGURATION")

    def model(self) -> dict[str, Any]:
        expected = (
            ENV_FILES if self.request.scope == "live" else ("/root/zhiming-core-secrets/stage-b1-upgrade-runtime.env",)
        )
        hashes = self.config.get("env_files_sha256", {})
        require(set(hashes) == set(expected), "EXACT_ENVIRONMENT_FILES")
        values = {}
        for name in expected:
            path = self.files.path(name)
            regular(path, private=True)
            require(file_sha(path) == hashes[name], "ENVIRONMENT_CHANGED")
            values.update(parse_env(path))
        require(
            all(
                parse_env(self.files.path(expected[-1])).get(key) == value
                for key, value in (("KIMI_MODEL", "k3"), ("KIMI_BASE_URL", MODEL_BASE))
            ),
            "RUNTIME_MODEL_CONFIG",
        )
        identity = conninfo_to_dict(values.get("ZHIMING_DATABASE_URL", ""))
        require(
            identity.get("dbname") == self.request.database
            and identity.get("host") in {"127.0.0.1", "::1"}
            and identity.get("port", "5432") == "5432"
            and identity.get("user") == self.request.database + "_writer",
            "RUNTIME_CONFIG_DATABASE",
        )
        require(not values.get("MODELS_CONFIG") and not values.get("MINGJING_MODEL_PORT"), "NEW_MODEL_PORT_ENABLED")
        require(values.get("LANGSMITH_TRACING", "false").lower() == "false", "TRACING_ENABLED")
        if self.request.scope == "stage":
            require(
                not any(values.get(key) for key in ("KIMI_API_KEY", "MOONSHOT_API_KEY")),
                "STAGE_PROVIDER_CREDENTIALS",
            )
            require(values.get("CORE_FEISHU_ENABLED", "false").lower() == "false", "STAGE_CHANNEL_ENABLED")
        return {
            "model": values.get("KIMI_MODEL"),
            "base": values.get("KIMI_BASE_URL"),
            "new_port": False,
        }

    def units(self) -> dict[str, dict[str, bool]]:
        result = {}
        for name, expected in self.request.unit_sha256.items():
            if expected == "absent":
                require(not self.files.path("/etc/systemd/system/" + name).exists(), "UNEXPECTED_STAGE_UNIT")
                raw = self.runner.run(["systemctl", "show", name, "--property=LoadState,ActiveState"])
                values = dict(line.split("=", 1) for line in raw.decode().splitlines() if "=" in line)
                require(
                    values.get("LoadState") == "not-found" and values.get("ActiveState") == "inactive",
                    "UNEXPECTED_STAGE_UNIT",
                )
                result[name] = {"inactive": True, "boot_disabled": True}
                continue
            raw = self.runner.run(
                [
                    "systemctl",
                    "show",
                    name,
                    "--property=ActiveState,UnitFileState,FragmentPath,DropInPaths,NeedDaemonReload",
                ]
            )
            values = dict(line.split("=", 1) for line in raw.decode().splitlines() if "=" in line)
            require(
                values.get("FragmentPath") == "/etc/systemd/system/" + name
                and not values.get("DropInPaths")
                and values.get("NeedDaemonReload") == "no",
                "UNREVIEWED_EFFECTIVE_UNIT",
            )
            result[name] = {
                "inactive": values.get("ActiveState") in {"inactive", "failed"},
                "boot_disabled": values.get("UnitFileState") in {"disabled", "masked", "static"},
            }
        return result

    def stop(self) -> None:
        failed = False
        for name, expected in self.request.unit_sha256.items():
            if expected != "absent":
                for operation in (["disable", "--now"], ["stop"]):
                    try:
                        self.runner.run(["systemctl", *operation, name])
                    except BaseException:
                        failed = True
        require(not failed, "WRITER_SHUTDOWN_INCOMPLETE")

    @contextmanager
    def quiesce(self, request: Request) -> Iterator[None]:
        self.guard()
        require(shutil.disk_usage(self.files.root).free >= request.minimum_free_bytes, "INSUFFICIENT_CAPACITY")
        self.source_checks()
        self.started = True
        if self.gate.exists():
            regular(self.gate)
        if not self.gate.exists():
            private_write(self.gate, b"B1 maintenance; explicit publication is separate.\n")
        self.stop()
        lock = self.files.path(
            "/root/zhiming-core-secrets/core-skill-writer.lock"
            if request.scope == "live"
            else "/root/zhiming-core-secrets/b1-stage-writer.lock"
        )
        with self.fence(lock):
            self.held = True
            try:
                self.database = self.database or PostgresPort(request, self.runner)
                yield
            finally:
                self.held = False

    def snapshot(self, request: Request, *, migrated: bool) -> dict[str, Any]:
        self.files.release(request)
        if self.retargeted:
            require(
                all(
                    file_sha(self.files.path("/etc/systemd/system/" + name)) == expected
                    for name, expected in self.new_unit_hashes.items()
                ),
                "RETARGETED_UNIT_CHANGED",
            )
        else:
            self.files.verify_units(request)
        result = self.database.snapshot(migrated=migrated)
        result.update(
            hostname=request.hostname,
            manifest_sha256=request.manifest_sha256,
            target=TARGET,
            previous=PREVIOUS,
            source_verified=True,
            migration_manifest=MIGRATIONS,
            free_bytes=shutil.disk_usage(self.files.root).free,
            writers=self.units(),
            maintenance=self.gate.is_file(),
            fence_held=self.held,
            hermes_fence_held=self.held and request.scope == "live",
            model=self.model(),
        )
        return result

    def backup(self, request: Request, snapshot: dict[str, Any]) -> dict[str, Any]:
        self.op.mkdir(parents=True, mode=0o700, exist_ok=False)
        self.database.dump(self.op / "before.dump")
        document = self.database.withdrawals()
        require(document.get("schema") == "core3-withdrawals-v2", "WITHDRAWAL_EXPORT")
        private_write(self.op / "withdrawals.json", json.dumps(document, sort_keys=True).encode())
        after = self.database.snapshot(migrated=False)
        require(after["state_sha256"] == snapshot["state_sha256"], "BACKUP_STATE_CHANGED")
        result = {
            "schema": "b1-quiesced-backup-v1",
            "operation_id": request.operation_id,
            "database": request.database,
            "source_state_sha256": snapshot["state_sha256"],
            "target": TARGET,
            "manifest_sha256": request.manifest_sha256,
            "mode": "0600",
            "body_free_withdrawals": True,
            "dump_sha256": file_sha(self.op / "before.dump"),
            "withdrawals_sha256": file_sha(self.op / "withdrawals.json"),
        }
        self.record("backup", result)
        return result

    def verify_backup_files(self, backup: dict[str, Any]) -> None:
        for name, key in (
            ("before.dump", "dump_sha256"),
            ("withdrawals.json", "withdrawals_sha256"),
        ):
            path = self.op / name
            regular(path, private=True)
            require(file_sha(path) == backup.get(key), "BACKUP_FILE_CHANGED")

    def record(self, phase: str, values: dict[str, Any]) -> None:
        private_write(
            self.op / (phase + ".json"),
            (json.dumps(values, sort_keys=True) + "\n").encode(),
        )

    def migrate_and_grant(self, request: Request) -> None:
        self.files.release(request)
        self.record("migration-started", {"target": TARGET, "rollback": "forward_only"})
        self.database.migrate_and_grant()
        self.record("migration-committed", {"target": TARGET, "schema": 7})

    def backfill(self, request: Request, owner: str, *, apply: bool) -> dict[str, Any]:
        self.files.release(request)
        return self.database.backfill(owner, apply=apply)

    def retarget(self, request: Request) -> dict[str, Any]:
        self.files.release(request)
        receipt: dict[str, Any] = {
            "source_verified": True,
            "writers_still_stopped": True,
        }
        backup = self.op / "retarget-before"
        environment = chart_environment(self.files, request, backup / "runtime.env")
        self.config = dict(self.config, env_files_sha256=dict(self.config["env_files_sha256"]))
        self.config["env_files_sha256"][environment["path"]] = environment["after_sha256"]
        receipt["chart_environment"] = environment
        receipt["units_sha256"] = self.files.retarget_units(request, backup / "units")
        self.new_unit_hashes = receipt["units_sha256"]
        if request.scope == "live":
            receipt.update(retarget_skill(self.files, request, backup / "hermes"))
        self.runner.run(["systemctl", "daemon-reload"])
        require(all(all(values.values()) for values in self.units().values()), "WRITER_ACTIVE")
        self.retargeted = True
        self.record("retargeted", receipt)
        return receipt

    def keep_closed(self, request: Request) -> None:
        if self.started:
            if not self.gate.exists():
                private_write(self.gate, b"B1 maintenance retained.\n")
            self.stop()
