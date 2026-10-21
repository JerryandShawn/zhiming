"""Observe an empty-target restore; default validation never connects to PostgreSQL."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from mingjing_core.timekit.clock import get_clock
from tools.b1_restore_proof_contracts import FORMAL_SCHEMA, LOCAL_SCHEMA, ProofRequest
from tools.b1_restore_proof_pg import (
    empty_target,
    restored_snapshot,
    writer_permissions,
)
from tools.b1_restore_proof_process import restore_archive, run_worker
from tools.b1_restore_replay import protected_output
from tools.b1_restore_replay_contracts import ReplayRejected, file_hash, require
from tools.b1_runtime_trust import inspect_core_venv
from tools.core_incremental_contracts import (
    EXPECTED_MANIFEST,
    MIGRATIONS,
    TARGET,
    UpgradeRejected,
    digest,
    validate_restore,
)

GENERATOR_SOURCES = (
    "tools/b1_restore_proof.py",
    "tools/b1_restore_proof_contracts.py",
    "tools/b1_restore_proof_pg.py",
    "tools/b1_restore_proof_process.py",
    "tools/b1_restore_proof_worker.py",
    "tools/b1_restore_replay.py",
    "tools/b1_restore_replay_contracts.py",
    "tools/b1_restore_replay_worker.py",
    "tools/b1_runtime_trust.py",
    "tools/core_incremental_contracts.py",
    "mingjing_core/__init__.py",
    "mingjing_core/timekit/__init__.py",
    "mingjing_core/timekit/clock.py",
)


def output_preflight(path: Path, *, local: bool) -> None:
    require(path.is_absolute() and path.parent.is_dir() and not path.exists(), "NEW_PROOF_OUTPUT_REQUIRED")
    require(not any(item.is_symlink() for item in (path, *path.parents)), "PROOF_OUTPUT_SYMLINK")
    require(local or path.parent.stat().st_mode & 0o077 == 0, "PRIVATE_PROOF_DIRECTORY")


def generator_hash() -> str:
    root = Path(__file__).resolve().parents[1]
    return digest({name: file_hash(root / name) for name in GENERATOR_SOURCES})


def generate(request: ProofRequest) -> dict[str, Any]:
    request.platform()
    upgrade, backup, document = request.validate()
    request.dsns()
    if not request.local_drill:
        inspect_core_venv()
    observed = empty_target(request)
    archive = restore_archive(request)
    restored = restored_snapshot(request, backup["source_state_sha256"])
    migration = run_worker(request, "migrate", document)
    require(migration.get("checksums") == MIGRATIONS, "PINNED_SCHEMA7_REQUIRED")
    first = run_worker(request, "replay", document)
    second = run_worker(request, "replay", document)
    require(second.get("changed") is False, "REPLAY_NOT_IDEMPOTENT")
    require(
        first["state_after_sha256"] == second["state_before_sha256"] == second["state_after_sha256"],
        "REPLAY_STATE_CHANGED",
    )
    permissions = writer_permissions(request)
    # Rehash all immutable inputs after physical effects; a changed ledger cannot yield proof.
    final_upgrade, final_backup, final_document = request.validate()
    require(upgrade == final_upgrade and backup == final_backup and document == final_document, "PROOF_INPUT_CHANGED")
    local = request.local_drill
    receipt = {
        "schema": LOCAL_SCHEMA if local else FORMAL_SCHEMA,
        "created_at": get_clock().now().astimezone(ZoneInfo("Asia/Shanghai")).isoformat(),
        "admissible": not local,
        "operation_id": upgrade.operation_id,
        "backup_sha256": digest(backup),
        "target": TARGET,
        "manifest_sha256": EXPECTED_MANIFEST,
        "database": request.database,
        "checksums": MIGRATIONS,
        "actual_pg_restore": True,
        "latest_withdrawals_replayed": True,
        "sent_uncertain_protected": True,
        "runtime_safe": True,
        "model_calls": 0,
        "external_sends": 0,
        "generator_sha256": generator_hash(),
        "candidate_python_sha256": file_hash(request.candidate_python),
        "dump_sha256": backup["dump_sha256"],
        "latest_ledger_sha256": request.ledger_sha256,
        "platform": sys.platform,
        "posix_permissions_verified": os.name == "posix" and not local,
        "empty_target_observed": observed,
        "database_creation_observed": False,
        "pg_restore": archive,
        "restored_schema4": restored,
        "migration": migration,
        "replay_first": first,
        "replay_second": second,
        "writer_permissions": permissions,
    }
    return validate_generated(upgrade, backup, receipt, local=local)


def validate_generated(upgrade: Any, backup: dict[str, Any], receipt: dict[str, Any], *, local: bool) -> dict[str, Any]:
    if not local:
        validate_restore(upgrade, backup, receipt)
    return receipt


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    for name in (
        "request",
        "backup",
        "dump",
        "backup-ledger",
        "ledger",
        "candidate-source",
        "candidate-python",
        "pg-restore",
    ):
        result.add_argument("--" + name, required=True, type=Path)
    for name in ("ledger-sha256", "database", "pg-restore-sha256"):
        result.add_argument("--" + name, required=True)
    result.add_argument("--local-drill", action="store_true")
    result.add_argument("--apply", action="store_true")
    result.add_argument("--quiesced", action="store_true")
    result.add_argument("--output", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    fields = {key: value for key, value in vars(args).items() if key not in {"apply", "quiesced", "output"}}
    try:
        request = ProofRequest(**fields)
        request.validate()
        if not args.apply:
            print(
                json.dumps(
                    {"valid": True, "apply": False, "database_connections": 0, "model_calls": 0, "external_sends": 0}
                )
            )
            return 0
        require(args.quiesced and args.output is not None, "EXPLICIT_QUIESCED_APPLY_REQUIRED")
        output_preflight(args.output, local=request.local_drill)
        receipt = generate(request)
        protected_output(args.output, receipt)
        print(
            json.dumps(
                {
                    "ok": True,
                    "schema": receipt["schema"],
                    "admissible": receipt["admissible"],
                    "model_calls": 0,
                    "external_sends": 0,
                }
            )
        )
        return 0
    except (ReplayRejected, UpgradeRejected) as error:
        code = str(error)
    except Exception:
        code = "RESTORE_PROOF_FAILED"
    print(json.dumps({"ok": False, "code": code, "model_calls": 0, "external_sends": 0}), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
