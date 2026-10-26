"""Fixed service entries retain cooperative writer fences until real process exit."""

from __future__ import annotations

import importlib
import json
import os
import runpy
import sys
from contextlib import suppress
from pathlib import Path
from types import ModuleType
from typing import Any, NoReturn

import psycopg
from psycopg.rows import dict_row

from tools.first_release_contracts import RestoreRejected, ordinary, require
from tools.first_release_restore import SafeParser
from tools.first_release_service_binding import ROLES, ServiceBinding, checked_writer, writer_parameters
from tools.first_release_writer_fence import file_lock, pg_lock


def _arguments(argv: list[str] | None) -> tuple[ServiceBinding, list[str], bool]:
    values = list(sys.argv[1:] if argv is None else argv)
    split = values.index("--") if "--" in values else len(values)
    native = values[split + 1 :] if split < len(values) else []
    parser = SafeParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--role", choices=sorted(ROLES), required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--system-identifier", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--database-oid", type=int, required=True)
    parser.add_argument("--writer", required=True)
    parser.add_argument("--writer-oid", type=int, required=True)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(values[:split])
    binding = ServiceBinding(**{key: value for key, value in vars(args).items() if key != "run"})
    binding.validate(native)
    return binding, native, args.run


def _module(binding: ServiceBinding, name: str, relative: str) -> ModuleType:
    ordinary(binding.candidate / relative)
    loaded = importlib.import_module(name)
    require(Path(loaded.__file__).absolute() == binding.candidate / relative, "SERVICE_NATIVE_ORIGIN_REJECTED")
    return loaded


def _native(binding: ServiceBinding, native_args: list[str]) -> None:
    _module(binding, "mingjing_core", "mingjing_core/__init__.py")
    if binding.role == "web":
        import uvicorn

        ordinary(binding.candidate / "main.py")
        application = runpy.run_path(str(binding.candidate / "main.py"), run_name="_first_release_web")["app"]
        uvicorn.run(application, host="127.0.0.1", port=8787, workers=1, reload=False, timeout_keep_alive=30)
    elif binding.role == "feishu":
        _module(binding, "mingjing_core.adapters.feishu_gateway", "mingjing_core/adapters/feishu_gateway.py").main()
    elif binding.role == "report":
        _module(
            binding, "mingjing_core.adapters.core_report_worker", "mingjing_core/adapters/core_report_worker.py"
        ).main(native_args)
    else:
        ordinary(binding.candidate / "hermes/core_consultation.py")
        entry = runpy.run_path(str(binding.candidate / "hermes/core_consultation.py"), run_name="_first_release_hermes")
        entry["main"](native_args)


def _message(code: str) -> None:
    with suppress(BaseException):
        sys.stderr.write(code + "\n")


def _terminate(code: int) -> NoReturn:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except KeyboardInterrupt:
            code = 130
        except BaseException:
            if code == 0:
                code = 2
            _message("SERVICE_OUTPUT_FLUSH_FAILED")
    # No ExitStack/finally/unlock precedes this: all remaining threads die with
    # this process, and the kernel releases both handles rather than a function.
    os._exit(code)


def _run_native(binding: ServiceBinding, native_args: list[str]) -> NoReturn:
    code = 0
    try:
        _native(binding, native_args)
    except KeyboardInterrupt:
        code = 130
        _message("SERVICE_INTERRUPTED")
    except SystemExit as error:
        code = error.code if type(error.code) is int and 0 <= error.code <= 255 else 2
        if code:
            _message("SERVICE_NATIVE_EXIT")
    except BaseException:
        code = 2
        _message("SERVICE_NATIVE_FAILED")
    _terminate(code)


def _run(binding: ServiceBinding, native_args: list[str], parameters: dict[str, Any]) -> NoReturn:
    with (
        file_lock(binding.fence_path, exclusive=False, existing_only=True),
        psycopg.connect(**parameters, autocommit=True, row_factory=dict_row) as connection,
    ):
        connection.execute("SET search_path=pg_catalog")
        connection.execute("SET default_transaction_read_only=on")
        checked_writer(connection, binding, parameters)
        with pg_lock(connection, binding.fence_key, exclusive=False):
            checked_writer(connection, binding, parameters)
            require(not os.path.lexists(binding.maintenance), "SERVICE_MAINTENANCE_RETAINED")
            _run_native(binding, native_args)


def main(argv: list[str] | None = None) -> int:
    try:
        binding, native_args, run = _arguments(argv)
        parameters = writer_parameters(binding)
        if run:
            _run(binding, native_args, parameters)
        print(json.dumps({"status": "validated", "role": binding.role, "database_connections": 0, "mutations": 0}))
        return 0
    except RestoreRejected:
        _message("SERVICE_CONFIGURATION_OR_FENCE_REJECTED")
    except (OSError, ValueError, TypeError, KeyError, psycopg.Error):
        _message("SERVICE_START_REJECTED")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
