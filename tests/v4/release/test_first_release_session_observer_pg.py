"""A real foreign-role client remains forbidden despite owner-hidden activity details."""

from __future__ import annotations

import psycopg
import pytest
from psycopg.rows import dict_row
from test_first_release_incremental_backup_pg import archive as archive
from test_first_release_incremental_backup_pg import existing as existing
from test_first_release_incremental_backup_pg import state

from tools.first_release_contracts import RestoreRejected
from tools.first_release_incremental import execute


def test_owner_hidden_foreign_client_has_visible_same_gate_type_and_is_still_rejected(existing):  # noqa: F811 - pytest fixture
    before = state(existing)
    with psycopg.connect(existing.environment["FIRST_INCREMENTAL_WRITER_DSN"], autocommit=True) as foreign:
        assert foreign.execute("SELECT pg_backend_pid()").fetchone() == (foreign.info.backend_pid,)
        with psycopg.connect(
            existing.environment["FIRST_INCREMENTAL_OWNER_DSN"], autocommit=True, row_factory=dict_row
        ) as owner:
            privilege = owner.execute(
                "SELECT rolsuper OR pg_has_role(current_user,'pg_read_all_stats','USAGE') AS full_stats "
                "FROM pg_roles WHERE rolname=current_user"
            ).fetchone()
            assert privilege == {"full_stats": False}
            owner.execute("SELECT pg_stat_clear_snapshot()")
            hidden = owner.execute(
                "SELECT pid,backend_type FROM pg_stat_activity WHERE pid=%s", (foreign.info.backend_pid,)
            ).fetchone()
            assert hidden == {"pid": foreign.info.backend_pid, "backend_type": None}
        with pytest.raises(RestoreRejected, match="^INCREMENTAL_OTHER_SOURCE_SESSION$") as stopped:
            execute(existing.inputs, backup_local=True, environment=existing.environment)
        diagnostic = stopped.value.session_diagnostic
        assert set(diagnostic) == {
            "schema",
            "observation",
            "allowed_pids",
            "allowed_count",
            "actual_backends",
            "actual_count",
            "truncated",
        }
        assert diagnostic["schema"] == "source-session-set-v1" and diagnostic["observation"] == "at_failed_gate"
        assert diagnostic["truncated"] is False and diagnostic["allowed_count"] == 1
        actual = {row["pid"]: row["backend_type"] for row in diagnostic["actual_backends"]}
        allowed = set(diagnostic["allowed_pids"])
        assert diagnostic["actual_count"] == len(actual) == 2
        assert set(actual) == allowed | {foreign.info.backend_pid}
        assert all(actual[pid] == "client backend" for pid in allowed)
        assert foreign.info.backend_pid not in diagnostic["allowed_pids"]
        assert actual[foreign.info.backend_pid] == "client backend"
        assert all(set(row) == {"pid", "backend_type"} for row in diagnostic["actual_backends"])
    assert state(existing) == before and not existing.inputs.maintenance.exists()
    assert not any(
        (existing.inputs.operation_dir / name).exists()
        for name in ("backup.dump", "latest-withdrawals.json", "backup-receipt.json", "backup-started.json")
    )
