"""Real target activity predicates retain the exact failing observation, without retries."""

from __future__ import annotations

import json

import psycopg
import pytest
from test_first_release_target_proof_pg import archive as archive
from test_first_release_target_proof_pg import existing as existing
from test_first_release_target_proof_pg import held
from test_first_release_target_proof_pg import observe_ledger_sessions as observe_ledger_sessions
from test_first_release_target_proof_pg import proof_case as proof_case

from tools import first_release_target_proof as native
from tools.first_release_contracts import RestoreRejected


def _diagnostic(error, record):
    assert str(error) == "TARGET_PROOF_ACTIVE_OR_OTHER_SESSION"
    value = error.session_diagnostic
    assert value["schema"] == "target-proof-activity-gate-v1" and value["observation"] == "at_failed_gate"
    assert value["database_oid"] == record.birth[0]
    assert value["allowed_count"] == len(value["allowed_pids"]) == 1 and value["truncated"] is False
    assert value["actual_count"] == len(value["actual_backends"])
    assert error.__notes__ == [json.dumps(value, sort_keys=True)]
    return value


def test_real_foreign_session_then_live_lease_have_distinct_original_gate_diagnostics(proof_case):  # noqa: F811
    value = proof_case
    with held(value) as proof:
        record = native._PROOFS[proof]
        with psycopg.connect(value.case.environment["FIRST_RELEASE_OWNER_DSN"], autocommit=True) as foreign:
            assert foreign.execute("SELECT pg_backend_pid()").fetchone() == (foreign.info.backend_pid,)
            with pytest.raises(RestoreRejected, match="^TARGET_PROOF_ACTIVE_OR_OTHER_SESSION") as stopped:
                native._check_target(record.inputs, value.source, record.dsns, record.creator)
            observed = _diagnostic(stopped.value, record)
            actual = {row["pid"]: row["backend_type"] for row in observed["actual_backends"]}
            assert observed["busy_run_count"] == 0 and observed["other_session"] is True
            assert observed["actual_count"] == 2
            assert set(actual) == set(observed["allowed_pids"]) | {foreign.info.backend_pid}
            assert set(actual.values()) == {"client backend"}
        # This explicit target-only fault is a real failed run with a live lease,
        # not an application effect or a repair of the original minted proof.
        with psycopg.connect(value.case.environment["FIRST_RELEASE_OWNER_DSN"]) as owner:
            owner.execute(
                "INSERT INTO mingjing_core.core_runs(id,owner,subject,operation_id,fingerprint,request,"
                "call_limit,status,lease_until) VALUES('synthetic-target-live-lease','synthetic','self',"
                "'synthetic-target-live-lease','synthetic','{}',2,'failed',clock_timestamp()+interval '1 hour')"
            )
        with pytest.raises(RestoreRejected, match="^TARGET_PROOF_ACTIVE_OR_OTHER_SESSION") as stopped:
            native.consume_target_proof(proof, source=value.source)
        observed = _diagnostic(stopped.value, record)
        assert observed["busy_run_count"] == 1 and observed["other_session"] is False
        assert observed["actual_count"] == 1
        assert {row["pid"] for row in observed["actual_backends"]} == set(observed["allowed_pids"])
        with pytest.raises(RestoreRejected, match="^TARGET_PROOF_EXPIRED_OR_CONSUMED$"):
            native.consume_target_proof(proof, source=value.source)
