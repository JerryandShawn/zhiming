"""Independent, closed memory stage copy/restore; reuse native PG safety checks unchanged."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from tools.first_release_contracts import RestoreRejected, ordinary, require
from tools.first_release_native_exchange import Scope, _environment, _execute, write_private
from tools.first_release_restore import SafeParser
from tools.first_release_stage_copy import copy_stage

DATABASE = "zhiming_core_mem2_stage"
ROOT = "/opt/zhiming-core-mem2-stage"
UNIT = "zhiming-core-mem2-stage.service"


@dataclass(frozen=True)
class MemoryStageScope(Scope):
    database: str = DATABASE
    root: str = ROOT
    unit: str = UNIT

    @property
    def original(self) -> str:
        return self.database

    @property
    def source(self) -> str:
        return "zhiming_core_stage"

    @property
    def target(self) -> str:
        return self.database

    @property
    def replacement(self) -> str:
        return "zhiming_core_mem2_" + self.operation + "_restore"

    @property
    def failed(self) -> str:
        return "zhiming_core_mem2_" + self.operation + "_failed"

    def validate(self) -> None:
        super().validate()
        require(self.local_drill is False, "MEM2_FORMAL_ONLY")
        require(self.database == DATABASE, "MEM2_STAGE_DATABASE")
        require(self.root == ROOT and self.unit == UNIT, "MEM2_STAGE_ROOT_UNIT")
        require(self.operation not in {"4e680f175ea28cc8", "1a131275da9dc8d6"}, "MEM2_NEW_OPERATION_REQUIRED")


def parser():
    value = SafeParser(description=__doc__, allow_abbrev=False)
    value.add_argument("action", choices=("copy", "capture", "restore", "seal", "exchange"))
    value.add_argument("--operation", required=True)
    value.add_argument("--database", default=DATABASE)
    value.add_argument("--root", default=ROOT)
    value.add_argument("--unit", default=UNIT)
    value.add_argument("--admin-env-file", type=Path)
    for name in ("workspace", "metadata", "backup", "pg-dump", "pg-restore", "restore-receipt"):
        value.add_argument("--" + name, type=Path)
    for name in ("metadata", "backup", "pg-dump", "pg-restore", "restore-receipt"):
        value.add_argument("--" + name + "-sha256")
    value.add_argument("--output", type=Path, required=True)
    value.add_argument("--apply", action="store_true")
    return value


def execute(args, scope):
    environment = _environment(scope, args.admin_env_file)
    ordinary(args.output.parent, directory=True)
    require(not os.path.lexists(args.output), "MEM2_NEW_OUTPUT_REQUIRED")
    if args.action != "copy":
        require(args.metadata is not None, "MEM2_METADATA_REQUIRED")
        return _execute(args, scope, environment)
    require(not os.path.lexists(scope.root), "MEM2_NEW_ROOT_REQUIRED")
    require(
        not any(os.path.lexists(Path(path) / scope.unit) for path in ("/etc/systemd/system", "/lib/systemd/system")),
        "MEM2_NEW_UNIT_REQUIRED",
    )
    require(args.workspace and args.pg_dump and args.pg_restore, "MEM2_COPY_ARGUMENTS")
    return copy_stage(
        scope,
        args.workspace,
        args.pg_dump,
        args.pg_restore,
        args.pg_dump_sha256,
        args.pg_restore_sha256,
        environment=environment,
    )


def main(argv=None):
    try:
        args = parser().parse_args(argv)
        scope = MemoryStageScope(args.operation, False, args.database, args.root, args.unit)
        scope.validate()
        if not args.apply:
            print(json.dumps({"status": "arguments_validated", "database_connections": 0, "model_calls": 0}))
            return 0
        result = execute(args, scope)
        write_private(args.output, result)
    except RestoreRejected as error:
        print(json.dumps({"status": "blocked", "code": str(error), "automatic_retry": False}))
        return 2
    except Exception:
        print(json.dumps({"status": "blocked", "code": "MEM2_STAGE_STOP_PRESERVE_ALL", "automatic_retry": False}))
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
