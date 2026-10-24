"""A real retained-source forward/replay/backfill chain; no reconstructed authority."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from test_first_release_capture_replay_chain_pg import fact_state
from test_first_release_incremental_backup_pg import archive as shared_archive
from test_first_release_incremental_backup_pg import state
from test_first_release_incremental_forward_pg import materials
from test_first_release_source_replay_chain_pg import native_observation, owner_rows
from test_first_release_source_replay_chain_pg import source_fixture as shared_existing
from test_first_release_source_replay_pg import proposal_fixture as shared_proposal
from test_first_release_source_replay_pg import reviewed_pin

from mingjing_core.repositories.postgres import PostgresRepository, fingerprint
from tests.v4.test_p2_threads_backfill import seed_historical_runs
from tools import first_release_incremental_forward as forward
from tools import first_release_source_backfill_process as backfill_process
from tools import first_release_source_process as replay_process
from tools.first_release_contracts import RestoreRejected
from tools.first_release_incremental import file_hash
from tools.first_release_source_backfill_pin import SourceBackfillPin, controls


@pytest.fixture(scope="module", name="archive")
def archive_fixture():
    return shared_archive.__wrapped__()


@pytest.fixture(name="existing")
def source_fixture(request, archive):
    for source in shared_existing.__wrapped__(request, archive):
        # Before M1 capture: real independent successful legacy runs, not effect receipts.
        dsn = source.environment["FIRST_INCREMENTAL_OWNER_DSN"]
        repo = PostgresRepository(make_conninfo(dsn, options="-c TimeZone=UTC"), initialize=False, max_size=1)
        try:
            seed_historical_runs(repo, 2)
            with repo.transaction("alice") as connection:
                history = connection.execute(
                    sql.SQL(
                        "SELECT id,status,result,request FROM {} WHERE owner='alice' "
                        "AND operation_id IN ('historical:0','historical:1') ORDER BY operation_id"
                    ).format(repo.table("core_runs"))
                ).fetchall()
            assert len(history) == 2 and all(row["status"] == "succeeded" and row["result"] for row in history)
            source.backfill_runs = [row["id"] for row in history]
            source.backfill_sources = [row["request"]["source_message_id"] for row in history]
        finally:
            repo.close()
        yield source


@pytest.fixture(name="proposal")
def proposal_fixture(existing):
    yield from shared_proposal.__wrapped__(existing)


def backfill_pin(request: Any, replay_pin: Any) -> SourceBackfillPin:
    source = request.source
    return SourceBackfillPin(
        request.pin.binding_sha256,
        replay_process._digest(asdict(request.pin)),
        replay_process._digest(asdict(replay_pin)),
        source.release.candidate,
        source.release.manifest_sha256,
        tuple(sorted(source.release.locks)),
        request.capture.pin.ledger_sha256,
        source.python_sha256,
        tuple(sorted(controls(request, replay_pin).items())),
    )


def candidate_paths(request: Any, pin: SourceBackfillPin) -> None:
    root = request.source.candidate_source
    document = json.loads((root / "__release_manifest__.json").read_bytes())
    assert document["commit"] == pin.candidate
    paths = (
        "tools/first_release_backfill_expected.py",
        "tools/first_release_backfill_effects.py",
        "mingjing_core/memory/backfill.py",
        "mingjing_core/application/memory.py",
        "mingjing_core/memory/projections.py",
    )
    for relative in paths:
        actual = file_hash(root / relative)
        assert document["files"][relative]["sha256"] == actual
        if relative.startswith("tools/"):
            assert dict(pin.controls)[relative] == actual


def watch_peers(monkeypatch: pytest.MonkeyPatch, observed: list[dict]) -> None:
    for module, stage in ((replay_process, "replay"), (backfill_process, "backfill")):
        original = module._peer

        def checked(parent, payload, value, *, native=original, label=stage):
            native(parent, payload, value)
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
                    stage=label,
                    event=value["event"],
                    pid=actual["pid"],
                    generation=actual["generation"],
                    parent_pid=parent.info.backend_pid,
                    state_sha256=replay_process._state(parent),
                )
            )

        monkeypatch.setattr(module, "_peer", checked)


def assert_peer_chain(peers: list[dict], result: dict) -> None:
    assert [(peer["stage"], peer["event"]) for peer in peers] == [
        ("replay", "ready_ro"),
        ("replay", "final_live"),
        ("backfill", "ready_ro"),
        ("backfill", "final_live"),
    ]
    assert len({peer["parent_pid"] for peer in peers}) == 1
    for pair, receipt in ((peers[:2], result["source_replay"]), (peers[2:], result["source_backfill"])):
        assert pair[0]["pid"] == pair[1]["pid"] == receipt["pid"]
        assert pair[0]["generation"] == pair[1]["generation"] == receipt["generation"]
        assert pair[0]["state_sha256"] == receipt["state_before_sha256"]
    assert peers[1]["state_sha256"] == result["source_replay"]["state_second_sha256"]
    assert peers[2]["state_sha256"] == peers[1]["state_sha256"]
    assert peers[3]["state_sha256"] == result["source_backfill"]["state_after_sha256"]


def assert_history(source: Any) -> None:
    with psycopg.connect(source.environment["FIRST_INCREMENTAL_OWNER_DSN"], row_factory=dict_row) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        rows = connection.execute(
            "SELECT id,data FROM mingjing_core.core_entities WHERE owner='alice' AND kind='message' "
            "AND data->>'role'='assistant' AND data->>'run_id'=ANY(%s)",
            (source.backfill_runs,),
        ).fetchall()
        assert len(rows) == 2
        for row in rows:
            assert row["id"] == "msg_" + fingerprint(["alice", "assistant", row["data"]["run_id"]])[:32]
            assert row["data"]["source_ids"] and set(row["data"]["source_ids"]) <= set(source.backfill_sources)
            assert row["data"]["policy"] == {"origin": "system", "run_context": False}
        sources = connection.execute(
            "SELECT data FROM mingjing_core.core_entities WHERE owner='alice' AND kind='message' AND id=ANY(%s)",
            (source.backfill_sources,),
        ).fetchall()
        assert len(sources) == 2 and all(
            row["data"]["thread_id"] == "life:self"
            and row["data"]["origin_conversation_id"] == "old-topic"
            and isinstance(row["data"]["at_ms"], int)
            and row["data"]["search_tokens"]
            for row in sources
        )


def assert_privacy_and_closed(source: Any, prior: dict, bob: dict, result: dict) -> None:
    actual = fact_state(source.environment["FIRST_INCREMENTAL_OWNER_DSN"], source.native_state)
    assert actual["prefix"] == 8 and actual["busy"] == 0
    assert actual["old_status"] == "deleted" and actual["old_data_empty"] and not actual["old_body_present"]
    assert actual["run_status"] == "revoked" and actual["run_error"] == "SOURCE_REVOKED"
    assert actual["run_request_empty"] and actual["run_outputs_cleared"] and actual["checkpoint_counts"] == [0, 0, 0]
    assert actual["outbox_status"] == "cancelled" and actual["outbox_outputs_cleared"]
    assert (
        actual["corrected"] == prior["corrected"]
        and owner_rows(source.environment["FIRST_INCREMENTAL_OWNER_DSN"], "bob") == bob
    )
    native = native_observation(source, source.native_state)
    assert native["observed"]["raw_status"] == "active" and native["observed"]["fts_night"] is False
    assert all(
        value is True for name, value in native["observed"].items() if name not in {"raw_status", "fts_night"}
    ), {
        name: native["observed"].get(name) is True
        for name in (
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
    }
    assert replay_process._digest(native["document"]) == result["source_replay"]["export_second_sha256"]
    current = state(source)
    assert replay_process._digest(current) == result["source_backfill"]["state_after_sha256"]
    for table in ("accounts", "batches", "authorizations", "usage"):
        assert current["tables"]["mingjing_core.core_model_" + table] == hashlib.sha256(b"[]").hexdigest()
    assert current["sequences"]["mingjing_core.core_model_usage_id_seq"] == dict(
        last_value=1, log_cnt=0, is_called=False
    )
    for receipt in (result, result["source_replay"], result["source_backfill"]):
        for key in (
            "source_upgraded",
            "source_write_authorized",
            "native_restore_completed",
            "runtime_verified",
            "central_binding_verified",
            "linux_attestation",
            "global_quiescence_verified",
            "publication",
        ):
            assert receipt[key] is False


def record_stopped(record_property: Any, error: forward.SourceForwardStopped, peers: list[dict]) -> None:
    phases = (
        {
            "source_checks",
            "authorized",
            "core_transaction_started",
            "core_transaction_rejected",
            "core_commit_outcome_unknown",
            "core_committed",
            "core_verified",
            "checkpoint_started",
            "checkpoint_completed",
            "grant_started",
            "grant_commit_outcome_unknown",
            "grant_rolled_back",
            "grant_committed",
            "source_forward_completed",
            "source_replay_preflight",
            "ready_ro",
            "source_replay_completed",
            "source_backfill_preflight",
            "backfill_ready_ro",
            "source_backfill_completed",
        }
        | set(replay_process.PHASES)
        | {f"source_backfill_{index}_{phase}" for index in range(1, 4) for phase in ("owner_started", "owner_verified")}
    )
    events = [
        (row["stage"], row["event"])
        for row in peers[:4]
        if row["stage"] in {"replay", "backfill"} and row["event"] in {"ready_ro", "final_live"}
    ]
    record_property("stopped_phase", error.phase if error.phase in phases else "unrecognized")
    record_property("session_restored", error.session_restored is True)
    record_property("observed_peer_events", json.dumps(events, separators=(",", ":")))


@pytest.mark.parametrize("existing", [7], indirect=True)
def test_m1_proof_runtime_forward_privacy_and_nonempty_candidate_backfill_one_live_scope(
    proposal, monkeypatch, record_property
):
    source = proposal.case.source
    before = fact_state(source.environment["FIRST_INCREMENTAL_OWNER_DSN"], source.native_state)
    assert before["prefix"] == 7 and before["run_status"] == "stale" and before["checkpoint_counts"] == [1, 1, 1]
    bob, material, peers = (
        owner_rows(source.environment["FIRST_INCREMENTAL_OWNER_DSN"], "bob"),
        materials(proposal.case),
        [],
    )
    replay = reviewed_pin(proposal.request)
    pin = backfill_pin(proposal.request, replay)
    candidate_paths(proposal.request, pin)
    watch_peers(monkeypatch, peers)
    record_property("actual_candidate", source.inputs.release.candidate)
    try:
        result = forward.execute(proposal.request, apply_source=True, source_replay_pin=replay, source_backfill_pin=pin)
    except forward.SourceForwardStopped as error:
        record_stopped(record_property, error, peers)
        raise
    assert result["phase"] == "source_backfill_completed" and result["source_forward_completed"] is True
    assert result["privacy_replay_pending"] is result["backfill_pending"] is False
    assert (
        result["target_proof"]["target_proof_consumed"]
        is result["controller_runtime"]["controller_runtime_verified"]
        is True
    )
    actual = result["source_backfill"]
    assert actual["source_backfill_completed"] is actual["parent_final_state_verified"] is True
    assert actual["all_owners_verified"] is actual["central_unchanged"] is True and actual["physical_connections"] == 1
    assert (
        actual["candidate"] == source.inputs.release.candidate
        and actual["source_operation_id"] == source.inputs.operation_id
    )
    assert actual["preview"]["assistant_created"] == actual["first"]["assistant_created"] == 2
    assert actual["first"]["message_metadata"] >= 2 and actual["first"]["search_tokens"] >= 2
    assert all(actual["second"][key] == 0 for key in ("message_metadata", "search_tokens", "assistant_created"))
    assert actual["state_before_sha256"] != actual["state_after_sha256"]
    assert_peer_chain(peers, result)
    assert_history(source)
    assert_privacy_and_closed(source, before, bob, result)
    assert materials(proposal.case) == material and source.inputs.maintenance.is_file()
    record_property("native_history_backfilled", 2)
    record_property("candidate_helpers_verified", 2)
    record_property("actual_live_stages", "M1/TargetProof/Runtime/Forward/source_replay/source_backfill")
    record_property("native_checkpoint_counts", "1/1/1->0/0/0")


@pytest.mark.parametrize("existing", [7], indirect=True)
def test_backfill_pin_default_and_invalid_inputs_have_zero_effects_and_keep_original_source(proposal, monkeypatch):
    source = proposal.case.source
    before, material = state(source), materials(proposal.case)
    replay = reviewed_pin(proposal.request)
    pin, attempts, path_open = backfill_pin(proposal.request, replay), [], Path.open

    def forbidden(*args, **kwargs):
        attempts.append(True)
        pytest.fail("BACKFILL_DEFAULT_OR_INVALID_PIN_MUST_NOT_PERFORM_IO")

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
        for name in ("mkdir", "write_text", "write_bytes"):
            patch.setattr(Path, name, forbidden)
        result = forward.execute(proposal.request, source_replay_pin=replay, source_backfill_pin=pin)
        assert result["database_connections"] == result["processes"] == result["file_writes"] == 0
        assert result["source_forward_completed"] is False and result["backfill_pending"] is True
        with pytest.raises(RestoreRejected, match="SOURCE_BACKFILL_TYPED_PIN"):
            forward.execute(proposal.request, apply_source=True, source_replay_pin=replay, source_backfill_pin={})
        with pytest.raises(RestoreRejected, match="SOURCE_BACKFILL_REVIEW_BINDING"):
            forward.execute(
                proposal.request,
                apply_source=True,
                source_replay_pin=replay,
                source_backfill_pin=replace(pin, candidate="0" * 40),
            )
        with pytest.raises(RestoreRejected, match="SOURCE_BACKFILL"):
            forward.execute(proposal.request, apply_source=True, source_backfill_pin=pin)
    assert attempts == [] and state(source) == before == proposal.before
    assert materials(proposal.case) == material and source.inputs.maintenance.is_file()
