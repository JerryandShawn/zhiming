"""Fixed isolated-Python entry for reviewed service assets and the Hermes wrapper."""

from __future__ import annotations

import json
import os
import re
import shlex
import stat
import sys
from pathlib import Path
from typing import Any

# Direct `python -I /fixed/release/tools/this_file.py` ignores inherited Python
# search paths. Only this script's own source root is then made importable.
ROOT = Path(__file__).absolute().parents[1]
if __package__ in {None, ""}:
    if sys.flags.isolated != 1:
        sys.stderr.write("ENTRY_ISOLATED_RUNTIME_REQUIRED\n")
        raise SystemExit(78)
    sys.path.insert(0, str(ROOT))

from tools.first_release_contracts import ordinary, read_json, require  # noqa: E402
from tools.first_release_restore import SafeParser  # noqa: E402
from tools.first_release_service_assets import (  # noqa: E402
    Assets,
    LocalProjection,
    common_environment,
    launcher_argv,
)


def _private_read(path: Path) -> bytes:
    ordinary(path)
    require(os.name == "posix", "ENTRY_PRIVATE_PERMISSIONS_UNVERIFIED")
    observed = path.stat()
    require(not observed.st_mode & 0o077 and observed.st_uid == os.geteuid(), "ENTRY_PRIVATE_CONFIG_REQUIRED")
    require(observed.st_size <= 1_000_000, "ENTRY_CONFIG_SIZE_LIMIT")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        require(not opened.st_mode & 0o077 and opened.st_uid == os.geteuid(), "ENTRY_PRIVATE_CONFIG_REQUIRED")
        require(opened.st_size <= 1_000_000, "ENTRY_CONFIG_SIZE_LIMIT")
        require(_file_identity(observed) == _file_identity(opened), "ENTRY_CONFIG_CHANGED")
        data = stream.read(1_000_001)
        finished = os.fstat(stream.fileno())
    after = path.stat()
    require(
        _file_identity(observed) == _file_identity(opened) == _file_identity(finished) == _file_identity(after),
        "ENTRY_CONFIG_CHANGED",
    )
    return data


def _file_identity(value: os.stat_result) -> tuple[int, ...]:
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, stat.S_IMODE(value.st_mode), value.st_uid)


def _parse_environment(data: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in data.decode("utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        require(separator and bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key)), "ENTRY_ENV_LITERAL_REQUIRED")
        require(key not in result, "ENTRY_DUPLICATE_ENV_REJECTED")
        value = value.strip()
        if value.startswith(("'", '"')):
            tokens = shlex.split(value, comments=False, posix=True)
            require(len(tokens) == 1, "ENTRY_ENV_LITERAL_REQUIRED")
            value = tokens[0]
        else:
            require(not any(char.isspace() for char in value) and "\\" not in value, "ENTRY_ENV_LITERAL_REQUIRED")
        require("\x00" not in value, "ENTRY_ENV_LITERAL_REQUIRED")
        result[key] = value
    return result


def _injected(environment: dict[str, str]) -> None:
    require(
        not any((name.startswith("PG") or name.startswith("PYTHON")) and value for name, value in environment.items()),
        "ENTRY_INJECTED_ENVIRONMENT_REJECTED",
    )


def load_environment(assets: Assets) -> dict[str, str]:
    environment = dict(os.environ)
    _injected(environment)
    for name in assets.env_files:
        values = _parse_environment(_private_read(Path(name)))
        _injected(values)
        environment.update(values)
    data = _private_read(Path(assets.common_env_path))
    require(data == common_environment(assets), "ENTRY_COMMON_CONFIGURATION_CHANGED")
    environment.update(_parse_environment(data))
    return environment


def _origin(module: Any, relative: str, root: Path) -> None:
    expected = root / relative
    ordinary(expected)
    require(Path(module.__file__).absolute() == expected, "ENTRY_SOURCE_ORIGIN_REJECTED")


def run(
    assets: Assets,
    native_args: tuple[str, ...],
    *,
    role: str = "hermes",
    local_projection: LocalProjection | None = None,
) -> int:
    if local_projection is None:
        require(sys.flags.isolated == 1, "ENTRY_ISOLATED_RUNTIME_REQUIRED")
    assets.validate()
    command = launcher_argv(assets, role, native_args, local_projection=local_projection)
    root = Path(assets.release) if local_projection is None else local_projection.candidate
    python = Path(assets.core_python) if local_projection is None else local_projection.core_python
    require(root == ROOT and Path(sys.executable).absolute() == python, "ENTRY_FIXED_RUNTIME_REQUIRED")
    require(sys.version_info[:2] == (3, 11), "ENTRY_PYTHON311_REQUIRED")
    ordinary(root, directory=True)
    ordinary(python)
    environment = load_environment(assets)
    import tools.first_release_service as service
    import tools.first_release_service_assets as definitions
    import tools.first_release_service_binding as binding

    _origin(definitions, "tools/first_release_service_assets.py", root)
    _origin(service, "tools/first_release_service.py", root)
    _origin(binding, "tools/first_release_service_binding.py", root)
    os.environ.clear()
    os.environ.update(environment)
    os.chdir(root)
    return service.main(command[3:])


def main(argv: list[str] | None = None) -> int:
    try:
        require(sys.flags.isolated == 1, "ENTRY_ISOLATED_RUNTIME_REQUIRED")
        values = list(sys.argv[1:] if argv is None else argv)
        split = values.index("--") if "--" in values else len(values)
        native = tuple(values[split + 1 :]) if split < len(values) else ()
        parser = SafeParser(description=__doc__, allow_abbrev=False)
        parser.add_argument("--config", type=Path, required=True)
        parser.add_argument("--role", choices=("web", "feishu", "report", "hermes"), required=True)
        parser.add_argument("--run", action="store_true")
        args = parser.parse_args(values[:split])
        assets = Assets.parse(read_json(args.config))
        launcher_argv(assets, args.role, native)
        if args.run:
            raw = _private_read(args.config)
            require(
                Assets.parse(json.loads(raw)) == assets and str(args.config) == assets.config_path,
                "ENTRY_CONFIG_BINDING_REJECTED",
            )
            return run(assets, native, role=args.role)
        return 0
    except Exception:
        sys.stderr.write("SERVICE_ENTRY_CONFIGURATION_REJECTED\n")
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
