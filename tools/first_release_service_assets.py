"""Render review-only Linux service assets; never install or control a service."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from tools.first_release_contracts import ordinary, read_json, require
from tools.first_release_restore import SafeParser

SCHEMA = "first-release-service-assets-v1"
PRIVATE_ROOT = PurePosixPath("/root/zhiming-core-secrets")
ROLES = frozenset({"web", "feishu", "report", "hermes"})
UNITS = {
    "web": "mingjingtai.service",
    "feishu": "zhiming-core-feishu.service",
    "report": "zhiming-core-reports.service",
}


def _linux_path(value: object) -> PurePosixPath:
    require(isinstance(value, str) and bool(re.fullmatch(r"/[A-Za-z0-9_./-]+", value)), "ASSETS_LITERAL_PATH_REQUIRED")
    path = PurePosixPath(value)
    require(str(path) == value and not {".", ".."} & set(value.split("/")), "ASSETS_CANONICAL_PATH_REQUIRED")
    return path


@dataclass(frozen=True)
class Assets:
    candidate: str
    workspace: str
    system_identifier: str
    database: str
    database_oid: int
    writer: str
    writer_oid: int
    report_owner: str
    env_files: tuple[str, str]
    config_path: str
    common_env_path: str
    k3_tokenizer_dir: str

    @property
    def release(self) -> str:
        return "/root/zhiming-core-releases/" + self.candidate

    @property
    def core_python(self) -> str:
        return self.release + "/venv/core/bin/python"

    @property
    def chart_python(self) -> str:
        return self.release + "/venv/charts/bin/python"

    def validate(self) -> None:
        require(
            isinstance(self.candidate, str) and bool(re.fullmatch(r"[0-9a-f]{40}", self.candidate)),
            "ASSETS_SHA_REQUIRED",
        )
        _linux_path(self.workspace)
        _linux_path(self.k3_tokenizer_dir)
        require(
            isinstance(self.system_identifier, str) and bool(re.fullmatch(r"[0-9]{15,20}", self.system_identifier)),
            "ASSETS_SYSTEM_IDENTIFIER_REQUIRED",
        )
        require(
            all(type(value) is int and 0 < value < 2**32 for value in (self.database_oid, self.writer_oid)),
            "ASSETS_OIDS_REQUIRED",
        )
        require(
            all(
                isinstance(value, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", value)
                for value in (self.database, self.writer, self.report_owner)
            ),
            "ASSETS_IDENTIFIERS_REQUIRED",
        )
        require(type(self.env_files) is tuple and len(self.env_files) == 2, "ASSETS_ORDERED_ENV_FILES_REQUIRED")
        paths = tuple(_linux_path(value) for value in (*self.env_files, self.config_path, self.common_env_path))
        require(len(set(paths)) == 4, "ASSETS_DISTINCT_CONFIGURATION_REQUIRED")
        require(all(path.parent == PRIVATE_ROOT for path in paths[2:]), "ASSETS_FIXED_PRIVATE_CONFIG_DIRECTORY")

    @classmethod
    def parse(cls, value: dict[str, Any]) -> Assets:
        fields = set(cls.__dataclass_fields__)
        require(type(value) is dict and set(value) == fields | {"schema"}, "ASSETS_CONFIG_FIELDS")
        require(value["schema"] == SCHEMA, "ASSETS_CONFIG_SCHEMA")
        require(type(value["env_files"]) is list, "ASSETS_ORDERED_ENV_FILES_REQUIRED")
        result = cls(
            **{key: tuple(item) if key == "env_files" else item for key, item in value.items() if key != "schema"}
        )
        result.validate()
        return result

    def document(self) -> dict[str, Any]:
        return {"schema": SCHEMA, **asdict(self)}


@dataclass(frozen=True)
class LocalProjection:
    """Explicit test-library mapping; never accepted by JSON, CLI, or Linux rendering."""

    candidate: Path
    core_python: Path
    workspace: Path

    def validate(self) -> None:
        ordinary(self.candidate, directory=True)
        ordinary(self.core_python)
        ordinary(self.workspace, directory=True)


def launcher_argv(
    assets: Assets,
    role: str,
    native_args: tuple[str, ...] = (),
    *,
    local_projection: LocalProjection | None = None,
) -> list[str]:
    assets.validate()
    require(role in ROLES, "ASSETS_ROLE_REJECTED")
    require(
        type(native_args) is tuple
        and len(native_args) <= 128
        and all(isinstance(value, str) and "\x00" not in value for value in native_args)
        and sum(map(len, native_args)) <= 16_000
        and (role in {"report", "hermes"} or not native_args),
        "ASSETS_NATIVE_ARGUMENTS_REJECTED",
    )
    candidate, python, workspace = assets.release, assets.core_python, assets.workspace
    if local_projection is not None:
        require(type(local_projection) is LocalProjection, "ASSETS_LOCAL_PROJECTION_REJECTED")
        local_projection.validate()
        candidate, python, workspace = map(
            str, (local_projection.candidate, local_projection.core_python, local_projection.workspace)
        )
    command = [
        python,
        "-m",
        "tools.first_release_service",
        "--role",
        role,
        "--candidate",
        candidate,
        "--workspace",
        workspace,
        "--system-identifier",
        assets.system_identifier,
        "--database",
        assets.database,
        "--database-oid",
        str(assets.database_oid),
        "--writer",
        assets.writer,
        "--writer-oid",
        str(assets.writer_oid),
        "--run",
    ]
    return command + (["--", *native_args] if native_args else [])


def common_environment(assets: Assets) -> bytes:
    return (
        "TZ=Asia/Shanghai\nMINGJING_AGENT_ENABLED=true\nCORE_RUN_CONCURRENCY=3\nCORE_DB_POOL_SIZE=4\n"
        "CHART_PYTHON=" + assets.chart_python + "\nK3_TOKENIZER_DIR=" + assets.k3_tokenizer_dir + "\n"
    ).encode()


def entry_argv(
    assets: Assets,
    role: str,
    native_args: tuple[str, ...] | None = None,
    *,
    local_projection: LocalProjection | None = None,
) -> list[str]:
    require(native_args is None or type(native_args) is tuple, "ASSETS_NATIVE_ARGUMENTS_REJECTED")
    native = ("--owner", assets.report_owner) if native_args is None and role == "report" else native_args or ()
    launcher_argv(assets, role, native, local_projection=local_projection)
    root, python, config = assets.release, assets.core_python, assets.config_path
    if local_projection is not None:
        root, python = str(local_projection.candidate), str(local_projection.core_python)
    return [
        python,
        "-I",
        str(Path(root) / "tools/first_release_hermes_entry.py")
        if local_projection
        else root + "/tools/first_release_hermes_entry.py",
        "--config",
        config,
        "--role",
        role,
        "--run",
        *(["--", *native] if native else []),
    ]


def _unit(assets: Assets, role: str) -> bytes:
    lines = [
        "[Unit]",
        "After=network-online.target",
        "Wants=network-online.target",
        "",
        "[Service]",
        "Type=" + ("oneshot" if role == "report" else "simple"),
        "User=root",
        "UMask=0077",
        "WorkingDirectory=" + assets.release,
        "KillMode=control-group",
        "ExecStart=" + " ".join(entry_argv(assets, role)),
    ]
    if role == "report":
        lines += ["TimeoutStartSec=900"]
    else:
        lines += [
            "Restart=on-failure",
            "RestartSec=" + ("10" if role == "feishu" else "5"),
            "",
            "[Install]",
            "WantedBy=multi-user.target",
        ]
    return ("\n".join(lines) + "\n").encode()


def _wrapper(assets: Assets) -> bytes:
    command = entry_argv(assets, "hermes")
    # This installed file uses only stdlib before replacing an old Hermes Python.
    text = f'''"""Pinned Core service wrapper; no service installation or legacy fallback."""
import os
import sys

def main():
    if any((name.startswith("PYTHON") or name.startswith("PG")) and value for name, value in os.environ.items()):
        sys.stderr.write("HERMES_INJECTED_ENVIRONMENT_REJECTED\\n")
        return 78
    command = {command!r}
    os.chdir({assets.release!r})
    os.execv(command[0], [*command, "--", *sys.argv[1:]])

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError):
        sys.stderr.write("HERMES_FIXED_CORE_START_REJECTED\\n")
        raise SystemExit(78) from None
'''
    return text.encode()


def render(assets: Assets) -> dict[str, bytes]:
    assets.validate()
    result = {name: _unit(assets, role) for role, name in UNITS.items()}
    result.update(
        {
            "core_consultation.py": _wrapper(assets),
            "service-config.json": (json.dumps(assets.document(), sort_keys=True) + "\n").encode(),
            "service-common.env": common_environment(assets),
        }
    )
    destinations = {name: "/etc/systemd/system/" + name for name in UNITS.values()}
    destinations.update(
        {
            "core_consultation.py": "/root/.hermes/skills/zhiming/core_consultation.py",
            "service-config.json": assets.config_path,
            "service-common.env": assets.common_env_path,
        }
    )
    manifest = {
        "schema": "first-release-service-assets-manifest-v1",
        "candidate": assets.candidate,
        "scope": "review_only",
        "timer_generated": False,
        "timer_policy": "retain_reviewed_timer_stopped",
        "timer_runtime_state": "unknown",
        "linux_runtime_verified": False,
        "files": {
            name: {"sha256": hashlib.sha256(data).hexdigest(), "install_path": destinations[name]}
            for name, data in result.items()
        },
    }
    result["manifest.json"] = (json.dumps(manifest, sort_keys=True) + "\n").encode()
    return result


def _output(output: Path) -> None:
    private = Path.cwd().absolute() / "private"
    ordinary(private, directory=True)
    require(
        output.is_absolute() and output.is_relative_to(private) and output != private, "ASSETS_PRIVATE_OUTPUT_REQUIRED"
    )
    ordinary(output.parent, directory=True)
    require(not os.path.lexists(output), "ASSETS_NEW_OUTPUT_REQUIRED")


def _write(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    ordinary(path)
    require(path.read_bytes() == data, "ASSETS_OUTPUT_CHANGED")


def execute(assets: Assets, output: Path, *, write_local: bool = False) -> dict[str, Any]:
    require(type(write_local) is bool, "ASSETS_WRITE_FLAG_REQUIRED")
    files = render(assets)
    _output(output)
    if write_local:
        os.mkdir(output, 0o700)
        ordinary(output, directory=True)
        for name, data in files.items():
            _write(output / name, data)
        if os.name != "nt":
            descriptor = os.open(output, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    return {
        "status": "assets_written" if write_local else "validated",
        "scope": "review_only",
        "files_written": len(files) if write_local else 0,
        "database_connections": 0,
        "processes_started": 0,
        "timer_generated": False,
        "installed": False,
        "linux_runtime_verified": False,
        "manifest_sha256": hashlib.sha256(files["manifest.json"]).hexdigest(),
    }


def main(argv: list[str] | None = None) -> int:
    try:
        parser = SafeParser(description=__doc__, allow_abbrev=False)
        parser.add_argument("--config", type=Path, required=True)
        parser.add_argument("--output", type=Path, required=True)
        parser.add_argument("--write-assets-local", action="store_true")
        args = parser.parse_args(argv)
        receipt = execute(Assets.parse(read_json(args.config)), args.output, write_local=args.write_assets_local)
    except Exception:
        print(json.dumps({"status": "blocked", "code": "SERVICE_ASSETS_REJECTED_OUTPUTS_RETAINED"}))
        return 2
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
