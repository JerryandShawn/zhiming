"""Real M1/target-proof/runtime/source-forward/native-replay chain; no reconstructed authority."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import replace
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from test_first_release_capture_replay_chain_pg import fact_state, seed_blob_checkpoint
from test_first_release_incremental_backup_pg import archive as shared_archive
from test_first_release_incremental_backup_pg import existing as shared_existing
from test_first_release_incremental_backup_pg import state
from test_first_release_incremental_forward_pg import materials
from test_first_release_source_replay_pg import native_seed, reviewed_pin
from test_first_release_source_replay_pg import proposal_fixture as shared_proposal
from test_first_release_source_span_pg import NATIVE

from tools import first_release_candidate_process as candidate
from tools import first_release_incremental_forward as forward
from tools import first_release_source_process as process
from tools.first_release_contracts import RestoreRejected
from tools.first_release_incremental import file_hash

OBSERVED_BOOLS = (
    "raw_unchanged",
    "projected_correct",
    "night_absent_context",
    "walk_present_context",
    "fts_walk",
    "night_deleted",
    "walk_unchanged",
    "note_deleted",
    "private_deleted",
    "run_revoked",
    "outbox_cancelled",
    "corrected_present",
    "preserved_embedding_only",
)


@pytest.fixture(scope="module", name="archive")
def archive_fixture():
    # Actual current committed archive; no old fixed candidate or control-tree business substitution.
    return shared_archive.__wrapped__()


@pytest.fixture(name="existing")
def source_fixture(request, archive):
    for source in shared_existing.__wrapped__(request, archive):
        assert len(source.inputs.source.migrations) == 7
        utc_dsn = make_conninfo(source.environment["FIRST_INCREMENTAL_OWNER_DSN"], options="-c TimeZone=UTC")
        with psycopg.connect(utc_dsn) as connection:
            zone = connection.execute("SHOW TimeZone").fetchone()[0]
            assert zone == "UTC"
        proxy = replace(source, environment=dict(source.environment, FIRST_INCREMENTAL_OWNER_DSN=utc_dsn))
        seeded = native_seed(proxy, "seed")
        seed_blob_checkpoint(utc_dsn, seeded)
        source.native_state = native_seed(proxy, "correct", seeded)
        source.native_seed_timezone = zone
        source.inputs = replace(
            source.inputs, source=replace(source.inputs.source, owners=("alice", "bob", "synthetic"))
        )
        yield source


@pytest.fixture(name="proposal")
def proposal_fixture(existing):
    yield from shared_proposal.__wrapped__(existing)


def owner_rows(dsn, owner):
    """All original fields of owner-scoped Core relations, not only row counts."""
    result = {}
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        connection.execute("SET LOCAL TimeZone='UTC'")
        names = connection.execute(
            "SELECT c.relname FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='mingjing_core' AND c.relkind='r' AND EXISTS(SELECT 1 FROM pg_catalog.pg_attribute a "
            "WHERE a.attrelid=c.oid AND a.attname='owner' AND a.attnum>0 AND NOT a.attisdropped) ORDER BY c.relname"
        ).fetchall()
        for row in names + [{"relname": "core_owners"}]:
            field = "id" if row["relname"] == "core_owners" else "owner"
            query = sql.SQL(
                "SELECT encode(sha256(convert_to(coalesce(jsonb_agg(to_jsonb(t) ORDER BY "
                "to_jsonb(t)::text COLLATE \"C\"),'[]'::jsonb)::text,'UTF8')),'hex') AS sha256 "
                "FROM mingjing_core.{} t WHERE {}=%s"
            ).format(sql.Identifier(row["relname"]), sql.Identifier(field))
            result[row["relname"]] = connection.execute(query, (owner,)).fetchone()["sha256"]
    return result


def native_observation(source, native_state):
    """Read real candidate MemoryService/export from the same reviewed archive in a fresh interpreter."""
    inputs = source.inputs
    payload = dict(
        worker=str(candidate.WORKER),
        python=str(inputs.python),
        root=str(inputs.candidate_source),
        core_lock_sha256=dict(inputs.release.locks)["requirements-core.lock"],
        action="observe",
        state=native_state,
        pin=dict(
            candidate=inputs.release.candidate,
            manifest_sha256=inputs.release.manifest_sha256,
            python_sha256=inputs.python_sha256,
            worker_sha256=file_hash(candidate.WORKER),
        ),
    )
    dsn = source.environment["FIRST_INCREMENTAL_OWNER_DSN"]
    env = candidate._environment(dsn)
    # M1 intentionally changes the source role default to Tokyo; compare the seed's full row in UTC.
    env["NATIVE_LOCAL_DSN"] = make_conninfo(dsn, options="-c TimeZone=UTC -c default_transaction_read_only=on")
    result = subprocess.run(
        [str(inputs.python), "-I", "-B", "-X", "pycache_prefix=" + os.path.abspath(os.devnull), "-c", NATIVE],
        input=json.dumps(payload),
        env=env,
        capture_output=True,
        encoding="utf-8",
        timeout=120,
        shell=False,
    )
    assert result.returncode == 0, "SOURCE_CHAIN_NATIVE_OBSERVATION_FAILED_PRIVATE_DETAILS_WITHHELD"
    value = json.loads(result.stdout)
    assert value["candidate"] == inputs.release.candidate and value["candidate_modules_checked"] > 0
    return value


def watch_live_peers(monkeypatch, observed):
    original = process._peer

    def checked(parent, payload, value):
        # Observe only after the original real gate; never replace a decision, PG row, proof, or result.
        original(parent, payload, value)
        actual = parent.execute(
            "SELECT pid,datid,usesysid,extract(epoch FROM backend_start)::text AS generation "
            "FROM pg_catalog.pg_stat_activity WHERE pid=%s",
            (value["pid"],),
        ).fetchone()
        assert actual == dict(
            pid=value["pid"],
            datid=payload["source"]["database_oid"],
            usesysid=payload["source"]["owner_oid"],
            generation=value["generation"],
        )
        assert actual["pid"] != parent.info.backend_pid
        observed.append(
            dict(
                event=value["event"],
                pid=actual["pid"],
                generation=actual["generation"],
                state_sha256=process._state(parent),
                parent_pid=parent.info.backend_pid,
            )
        )

    monkeypatch.setattr(process, "_peer", checked)


def assert_formal_closed(result):
    for receipt in (result, result["source_replay"]):
        for flag in (
            "source_upgraded",
            "source_write_authorized",
            "native_restore_completed",
            "runtime_verified",
            "central_binding_verified",
            "linux_attestation",
            "global_quiescence_verified",
            "publication",
        ):
            assert receipt[flag] is False
        assert receipt["backfill_pending"] is True
    assert result["source_restore_content_verified"] is False
    assert result["source_replay"]["model_calls"] == result["source_replay"]["external_sends"] == 0


def assert_privacy(source, native_state, before, bob_before, result, record_property):
    dsn = source.environment["FIRST_INCREMENTAL_OWNER_DSN"]
    actual = fact_state(dsn, native_state)
    assert actual["prefix"] == 8 and actual["busy"] == 0
    assert actual["old_status"] == "deleted" and actual["old_data_empty"] and not actual["old_body_present"]
    assert actual["run_status"] == "revoked" and actual["run_error"] == "SOURCE_REVOKED"
    assert actual["run_request_empty"] and actual["run_outputs_cleared"]
    assert actual["outbox_status"] == "cancelled" and actual["outbox_outputs_cleared"]
    assert actual["checkpoint_counts"] == [0, 0, 0] and actual["corrected"] == before["corrected"]
    assert owner_rows(dsn, "bob") == bob_before
    native = native_observation(source, native_state)
    observed = native["observed"]
    assert observed["raw_status"] == "active" and observed["fts_night"] is False
    diagnostic = {name: observed.get(name) is True for name in OBSERVED_BOOLS}
    record_property("source_observation_bools", json.dumps(diagnostic, sort_keys=True))
    assert all(value is True for name, value in observed.items() if name not in {"raw_status", "fts_night"}), (
        "SOURCE_OBSERVATION_BOOLS:" + json.dumps(diagnostic, sort_keys=True)
    )
    replay = result["source_replay"]
    assert process._digest(native["document"]) == replay["export_first_sha256"] == replay["export_second_sha256"]
    final = state(source)
    assert process._digest(final) == replay["state_first_sha256"] == replay["state_second_sha256"]
    for name in ("accounts", "batches", "authorizations", "usage"):
        assert final["tables"]["mingjing_core.core_model_" + name] == hashlib.sha256(b"[]").hexdigest()
    assert final["sequences"]["mingjing_core.core_model_usage_id_seq"] == dict(last_value=1, log_cnt=0, is_called=False)


@pytest.mark.parametrize("existing", [7], indirect=True)
def test_real_nonempty_m1_target_proof_runtime_forward_and_live_source_replay_are_one_call(
    proposal,
    monkeypatch,
    record_property,
):
    source = proposal.case.source
    record_property("fixture_seed_timezone", source.native_seed_timezone)
    assert len(proposal.request.source.source.migrations) == 7
    native_state = source.native_state
    dsn = source.environment["FIRST_INCREMENTAL_OWNER_DSN"]
    before = fact_state(dsn, native_state)
    assert before["prefix"] == 7 and before["old_status"] == "superseded" and before["old_body_present"]
    assert before["run_status"] == "stale" and before["checkpoint_counts"] == [1, 1, 1]
    bob_before, material_before, peers = owner_rows(dsn, "bob"), materials(proposal.case), []
    pin = reviewed_pin(proposal.request)
    watch_live_peers(monkeypatch, peers)
    result = forward.execute(proposal.request, apply_source=True, source_replay_pin=pin)
    assert result["phase"] == "source_replay_completed" and result["source_forward_completed"] is True
    assert result["privacy_replay_pending"] is False
    assert result["target_proof"]["target_proof_consumed"] is True
    assert result["controller_runtime"]["controller_runtime_verified"] is True
    assert proposal.request.target.contract.database != proposal.request.source.source.database
    replay = result["source_replay"]
    assert replay["source_replay_completed"] is replay["parent_final_state_verified"] is True
    assert replay["second_apply_unchanged"] is replay["central_unchanged"] is True
    assert replay["physical_connections"] == 1
    assert replay["candidate"] == proposal.request.source.release.candidate
    assert replay["source_operation_id"] == proposal.request.source.operation_id
    assert [peer["event"] for peer in peers] == ["ready_ro", "final_live"]
    assert peers[0]["pid"] == peers[1]["pid"] == replay["pid"]
    assert peers[0]["generation"] == peers[1]["generation"] == replay["generation"]
    assert peers[0]["parent_pid"] == peers[1]["parent_pid"]
    assert peers[0]["state_sha256"] == replay["state_before_sha256"]
    assert peers[1]["state_sha256"] == replay["state_second_sha256"]
    assert replay["checks"]["checkpoint_ranges_checked"] >= 3
    assert_privacy(source, native_state, before, bob_before, result, record_property)
    assert materials(proposal.case) == material_before and source.inputs.maintenance.is_file()
    assert_formal_closed(result)
    record_property("actual_candidate", proposal.request.source.release.candidate)
    record_property("real_source_witness_path", "M1/TargetProof/ControllerRuntime/Forward/source_replay")
    record_property("original_source_prefix", 7)
    record_property("native_checkpoint_counts", "1/1/1->0/0/0")


@pytest.mark.parametrize("existing", [7], indirect=True)
def test_valid_replay_pin_default_is_readonly_and_wrong_type_or_candidate_never_reaches_effects(proposal, monkeypatch):
    source = proposal.case.source
    before, material_before = state(source), materials(proposal.case)
    pin = reviewed_pin(proposal.request)
    path_open, attempted = Path.open, []

    def forbidden(*args, **kwargs):
        attempted.append(True)
        pytest.fail("SOURCE_REPLAY_DEFAULT_OR_INVALID_PIN_MUST_NOT_PERFORM_EFFECTS")

    def read_only_open(path, mode="r", *args, **kwargs):
        if any(flag in mode for flag in "wax+"):
            forbidden()
        return path_open(path, mode, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(psycopg, "connect", forbidden)
        patch.setattr(subprocess, "run", forbidden)
        patch.setattr(subprocess, "Popen", forbidden)
        patch.setattr(os, "open", forbidden)
        patch.setattr(Path, "open", read_only_open)
        patch.setattr(Path, "mkdir", forbidden)
        patch.setattr(Path, "write_text", forbidden)
        patch.setattr(Path, "write_bytes", forbidden)
        result = forward.execute(proposal.request, source_replay_pin=pin)
        assert result["database_connections"] == result["processes"] == result["file_writes"] == 0
        assert result["source_forward_completed"] is result["source_upgraded"] is False
        assert result["privacy_replay_pending"] is result["backfill_pending"] is True
        with pytest.raises(RestoreRejected, match="SOURCE_REPLAY_TYPED_PIN"):
            forward.execute(proposal.request, apply_source=True, source_replay_pin={"source_replay_completed": True})
        with pytest.raises(RestoreRejected, match="SOURCE_REPLAY_REVIEW_BINDING"):
            forward.execute(proposal.request, apply_source=True, source_replay_pin=replace(pin, candidate="0" * 40))
    assert attempted == [] and state(source) == before and before == proposal.before
    assert materials(proposal.case) == material_before and source.inputs.maintenance.is_file()
