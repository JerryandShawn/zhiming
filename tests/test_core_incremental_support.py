"""Body-free synthetic restore evidence shared by the offline controller tests."""

from __future__ import annotations

from typing import Any

from tools.core_incremental_contracts import MIGRATIONS, TARGET, Request, digest


def restore_for(request: Request, backup: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "b1-isolated-restore-proof-v1",
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
    }
