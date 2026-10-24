"""Synthetic Linux-shaped inputs; these are never evidence of a Linux run."""

from __future__ import annotations

from typing import Any

from tools.core_incremental_contracts import MIGRATIONS, TARGET, Request, digest


def restore_for(request: Request, backup: dict[str, Any]) -> dict[str, Any]:
    state = "b" * 64
    identity = {
        "database": request.restore_database,
        "host": "127.0.0.1",
        "port": 5432,
        "version_num": 150018,
    }
    replay = {
        "state_before_sha256": state,
        "state_after_sha256": state,
        "changed": False,
        "counts": {
            "owners": len(request.owners),
            "deleted_draws": 0,
            "tarot_tombstones": 0,
            "protected_receipts": 0,
            "model_calls": 0,
            "external_sends": 0,
        },
        "whole_revocations_checked": 0,
        "deleted_draws_checked": 0,
        "checkpoint_ranges_checked": 0,
    }
    return {
        "schema": "b1-isolated-restore-proof-v1",
        "platform": "linux",
        "admissible": True,
        "posix_permissions_verified": True,
        "operation_id": request.operation_id,
        "backup_sha256": digest(backup),
        "target": TARGET,
        "manifest_sha256": request.manifest_sha256,
        "database": request.restore_database,
        "checksums": MIGRATIONS,
        "actual_pg_restore": True,
        "latest_withdrawals_replayed": True,
        "sent_uncertain_protected": True,
        "runtime_safe": True,
        "model_calls": 0,
        "external_sends": 0,
        "generator_sha256": state,
        "candidate_python_sha256": state,
        "dump_sha256": backup["dump_sha256"],
        "latest_ledger_sha256": state,
        "empty_target_observed": dict(identity, role=request.restore_database + "_owner"),
        "pg_restore": {"executed": True, "exit_code": 0, "executable_sha256": state},
        "restored_schema4": {
            "state_sha256": backup["source_state_sha256"],
            "checksums": {key: MIGRATIONS[key] for key in ("1", "2", "3", "4")},
        },
        "migration": {"checksums": MIGRATIONS, "forward_migrations": [5, 6, 7]},
        "replay_first": dict(replay),
        "replay_second": dict(replay),
        "writer_permissions": {
            "identity": dict(identity, role=request.restore_database + "_writer"),
            "tables_checked": 24,
            "forbidden_probes_denied": 5,
        },
    }
