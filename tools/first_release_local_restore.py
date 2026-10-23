"""Explicit native restore into a brand-new local test database; never stage or production."""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import psycopg
from psycopg.conninfo import conninfo_to_dict

from tools.first_release_contracts import ReleasePin, RestoreContract, RestoreRejected, read_json, require
from tools.first_release_local_inputs import DumpPin, LocalInputs, file_hash
from tools.first_release_local_pg import new_target, verify_original
from tools.first_release_restore import SafeParser


def process_environment(owner_dsn: str) -> dict[str, str]:
    fields = conninfo_to_dict(owner_dsn)
    result = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP") if key in os.environ}
    result.update(
        PGPASSFILE=os.devnull,
        PGCONNECT_TIMEOUT="5",
        LANGSMITH_TRACING="false",
        LANGCHAIN_TRACING_V2="false",
        OTEL_SDK_DISABLED="true",
        CORE_FEISHU_ENABLED="false",
    )
    if fields.get("password"):
        result["PGPASSWORD"] = fields["password"]
    return result


def run_program(inputs: LocalInputs, arguments: list[str], environment: dict[str, str]) -> bytes:
    require(file_hash(inputs.pg_restore) == inputs.dump_pin.pg_restore_sha256, "REVIEWED_PG_RESTORE_CHANGED")
    try:
        result = subprocess.run(
            [str(inputs.pg_restore), *arguments],
            env=environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=180,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RestoreRejected("LOCAL_PG_RESTORE_PROCESS_FAILED") from None
    require(result.returncode == 0, "LOCAL_PG_RESTORE_PROCESS_FAILED")
    return result.stdout


def preflight_program(inputs: LocalInputs, environment: dict[str, str]) -> None:
    version = run_program(inputs, ["--version"], environment)
    require(re.search(rb"PostgreSQL\) 15\.[0-9]+", version), "LOCAL_PG_RESTORE15_REQUIRED")
    listing = run_program(inputs, ["--list", str(inputs.dump)], environment)
    require(
        not re.search(rb"\bcore_model_(?:accounts|usage|batches|authorizations)(?:\b|_)", listing),
        "CENTRAL_LEDGER_ARCHIVE_REJECTED",
    )


def restore_command(inputs: LocalInputs, owner_dsn: str) -> list[str]:
    fields = conninfo_to_dict(owner_dsn)
    return [
        "--host=" + fields["host"],
        "--port=" + fields["port"],
        "--username=" + fields["user"],
        "--dbname=" + fields["dbname"],
        "--no-password",
        "--no-owner",
        "--no-acl",
        "--exit-on-error",
        "--single-transaction",
        str(inputs.dump),
    ]


def execute(
    inputs: LocalInputs, *, apply_local: bool = False, environment: Mapping[str, str] | None = None
) -> dict[str, Any]:
    receipt = inputs.validate()
    if not apply_local:
        return receipt
    dsns = inputs.connections(environment)
    child_environment = process_environment(dsns["owner"])
    preflight_program(inputs, child_environment)
    with new_target(inputs, dsns):
        # Recheck immutable bytes immediately before the only restore; failure never retries or removes its target.
        require(file_hash(inputs.dump) == inputs.dump_pin.dump_sha256, "REVIEWED_DUMP_CHANGED")
        run_program(inputs, restore_command(inputs, dsns["owner"]), child_environment)
        require(file_hash(inputs.dump) == inputs.dump_pin.dump_sha256, "REVIEWED_DUMP_CHANGED")
        original = verify_original(inputs, dsns["owner"])
    receipt.pop("mutations", None)
    return {
        **receipt,
        **original,
        "schema": "first-release-local-original-restore-v1",
        "local_pg_restore_completed": True,
        "actual_pg_restore": True,
        "forward_migrations": [],
        "latest_withdrawals_replayed": False,
        "runtime_acl_verified": False,
        "native_restore_completed": False,
        "linux_attestation": False,
        "publication": False,
        "database_connections": 4,
        "created_roles": 2,
        "created_databases": 1,
        "mutation_scope": "new-local-database-only",
    }


def main(argv: list[str] | None = None) -> int:
    parser = SafeParser(description=__doc__)
    for name in ("pin", "contract", "dump-pin", "dump", "pg-restore"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--apply-local", action="store_true")
    try:
        args = parser.parse_args(argv)
        inputs = LocalInputs(
            ReleasePin.parse(read_json(args.pin)),
            RestoreContract.parse(read_json(args.contract)),
            DumpPin.parse(read_json(args.dump_pin)),
            args.dump,
            args.pg_restore,
            Path.cwd(),
        )
        receipt = execute(inputs, apply_local=args.apply_local)
    except RestoreRejected as error:
        print(json.dumps({"status": "blocked", "code": str(error), "automatic_cleanup": False}))
        return 2
    except (psycopg.Error, OSError, ValueError, TypeError, KeyError):
        print(json.dumps({"status": "blocked", "code": "LOCAL_RESTORE_FAILED_TARGETS_RETAINED"}))
        return 2
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
