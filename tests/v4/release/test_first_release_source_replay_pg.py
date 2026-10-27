"""Real candidate/source-worker components, never a forged SourceWitness/controller admission chain."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict, replace
from types import SimpleNamespace

import psycopg
import pytest
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import sql
from psycopg.rows import dict_row
from test_first_release_capture_replay_chain_pg import fact_state, seed_blob_checkpoint
from test_first_release_incremental_backup_pg import archive as shared_archive
from test_first_release_incremental_backup_pg import existing as shared_existing
from test_first_release_incremental_forward_pg import proposal as shared_proposal
from test_first_release_source_span_pg import NATIVE

from tools import first_release_candidate_process as candidate
from tools import first_release_source_process as process
from tools.first_release_contracts import RestoreRejected, require
from tools.first_release_incremental import file_hash
from tools.first_release_incremental_pg import snapshot
from tools.first_release_migration_steps import forward_core, grant_new_runtime, history, load_bundle
from tools.first_release_source_profile import verify_source_profile
from tools.first_release_writer_fence import file_lock, pg_lock


@pytest.fixture(scope="module", name="archive")
def archive_fixture():
    return shared_archive.__wrapped__()


def native_seed(source, action, state=None):
    inputs = source.inputs
    payload = dict(
        worker=str(candidate.WORKER),
        python=str(inputs.python),
        root=str(inputs.candidate_source),
        core_lock_sha256=dict(inputs.release.locks)["requirements-core.lock"],
        action=action,
        state=state,
        pin=dict(
            candidate=inputs.release.candidate,
            manifest_sha256=inputs.release.manifest_sha256,
            python_sha256=inputs.python_sha256,
            worker_sha256=file_hash(candidate.WORKER),
        ),
    )
    dsn = source.environment["FIRST_INCREMENTAL_OWNER_DSN"]
    env = candidate._environment(dsn)
    env["NATIVE_LOCAL_DSN"] = dsn
    result = subprocess.run(
        [str(inputs.python), "-I", "-B", "-X", "pycache_prefix=" + os.path.abspath(os.devnull), "-c", NATIVE],
        input=json.dumps(payload),
        env=env,
        capture_output=True,
        encoding="utf-8",
        timeout=120,
        shell=False,
    )
    assert result.returncode == 0, "SOURCE_COMPONENT_NATIVE_FIXTURE_FAILED_PRIVATE_DETAILS_WITHHELD"
    value = json.loads(result.stdout)
    assert value["candidate"] == inputs.release.candidate and value["candidate_modules_checked"] > 0
    return value["state"]


@pytest.fixture(name="existing")
def source_fixture(request, archive):
    for source in shared_existing.__wrapped__(request, archive):
        source.native_state = None
        if len(source.inputs.source.migrations) == 7:
            seeded = native_seed(source, "seed")
            seed_blob_checkpoint(source.environment["FIRST_INCREMENTAL_OWNER_DSN"], seeded)
            source.native_state = native_seed(source, "correct", seeded)
            source.inputs = replace(
                source.inputs, source=replace(source.inputs.source, owners=("alice", "bob", "synthetic"))
            )
        yield source


@pytest.fixture(name="proposal")
def proposal_fixture(existing):
    yield from shared_proposal.__wrapped__(existing)


def reviewed_pin(request):
    return process.SourceReplayPin(
        request.pin.binding_sha256,
        process._digest(asdict(request.pin)),
        request.source.release.candidate,
        request.source.release.manifest_sha256,
        tuple(sorted(request.source.release.locks)),
        request.capture.pin.ledger_sha256,
        request.source.python_sha256,
        tuple(sorted(process.controls(request).items())),
    )


def neutral_upgrade(parent, proposal):
    """Real component preparation, explicitly not the opaque full Forward/controller path."""
    source = proposal.request.source

    def locked(connection):
        for name in sorted(proposal.before["tables"]):
            connection.execute(
                sql.SQL("LOCK TABLE {} IN ACCESS EXCLUSIVE MODE NOWAIT").format(sql.Identifier(*name.split(".")))
            )
        verify_source_profile(connection, source, "owner")
        assert snapshot(connection) == proposal.before

    bundle = load_bundle(source.release, source.candidate_source)
    assert forward_core(parent, bundle, source.source.migrations, prepare_locked_source=locked) == list(
        range(len(source.source.migrations) + 1, 9)
    )
    parent.execute("SET search_path=public")
    PostgresSaver(parent).setup()
    parent.execute("SET search_path=pg_catalog")
    grant_new_runtime(parent, source.source.database + "_writer")
    assert history(parent) == {int(v): sha for v, sha in source.release.migrations}


@pytest.fixture
def component(proposal):
    source = proposal.request.source
    dsn = proposal.case.source.environment["FIRST_INCREMENTAL_OWNER_DSN"]
    with (
        file_lock(source.fence_path, exclusive=True, existing_only=True, return_handle=True),
        psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as parent,
        pg_lock(parent, source.fence_key, exclusive=True),
    ):
        parent.execute("SET search_path=pg_catalog")
        neutral_upgrade(parent, proposal)
        parent.execute("SET default_transaction_read_only=on")
        pin = reviewed_pin(proposal.request)
        payload = process._payload(proposal.request, pin, parent.info.backend_pid)
        yield SimpleNamespace(
            proposal=proposal,
            source=source,
            parent=parent,
            dsn=dsn,
            pin=pin,
            payload=payload,
            native_state=proposal.case.source.native_state,
            phases=[],
            ready_seen=[],
            final_seen=[],
        )


def checked_ready(value, hello):
    process._peer(value.parent, value.payload, hello)
    require(process._state(value.parent) == hello["state_sha256"], "SOURCE_REPLAY_READY_STATE_CHANGED")
    value.ready_seen.append(hello)


def checked_final(value, result):
    process._peer(value.parent, value.payload, result)
    require(process._state(value.parent) == result["state_second_sha256"], "SOURCE_REPLAY_FINAL_STATE_CHANGED")
    value.final_seen.append(result)


def exchange(value, ready=None, final=None):
    return process._exchange(
        value.payload,
        value.source.python,
        value.dsn,
        ready or (lambda hello: checked_ready(value, hello)),
        final or (lambda result: checked_final(value, result)),
        value.phases.append,
    )


def mutate(parent):
    with parent.transaction():
        parent.execute("SET TRANSACTION READ WRITE")
        parent.execute(
            "UPDATE mingjing_core.core_entities SET updated_at=updated_at+interval '1 second' WHERE owner='synthetic'"
        )


def test_real_candidate_nonempty_native_double_replay_keeps_one_live_lease_until_parent_done(
    component, record_property
):
    value = component
    before = fact_state(value.dsn, value.native_state)
    before_hash = process._state(value.parent)
    assert before["old_status"] == "superseded" and before["old_body_present"]
    assert before["checkpoint_counts"] == [1, 1, 1] and before["run_status"] == "stale"
    result = exchange(value)
    assert value.phases == list(process.PHASES) and len(value.ready_seen) == len(value.final_seen) == 1
    assert result["physical_connections"] == 1 and result["state_before_sha256"] == before_hash
    assert result["state_first_sha256"] == result["state_second_sha256"] == process._state(value.parent)
    assert result["export_first_sha256"] == result["export_second_sha256"]
    assert result["central_unchanged"] is result["second_apply_unchanged"] is True
    assert result["checks"]["checkpoint_ranges_checked"] >= 3
    after = fact_state(value.dsn, value.native_state)
    assert after["old_status"] == "deleted" and after["old_data_empty"]
    assert after["run_status"] == "revoked" and after["run_outputs_cleared"]
    assert after["checkpoint_counts"] == [0, 0, 0] and after["outbox_outputs_cleared"]
    assert value.source.maintenance.is_file()
    record_property("source_fixture_admission", "neutral-real-prefix7-to8-component-only")
    record_property("source_witness_controller_chain_verified", False)
    record_property("actual_child_alive_during_parent_final_state_observation", True)


@pytest.mark.parametrize("existing", [4], indirect=True)
def test_no_parent_write_ack_preserves_actual_prefix4_component_source(component):
    value = component
    before = process._state(value.parent)

    def reject(hello):
        checked_ready(value, hello)
        raise RestoreRejected("SYNTHETIC_PARENT_NO_WRITE_ACK")

    with pytest.raises(RestoreRejected, match="SYNTHETIC_PARENT_NO_WRITE_ACK"):
        exchange(value, ready=reject)
    assert len(value.ready_seen) == 1 and not value.phases and not value.final_seen
    assert process._state(value.parent) == before and value.source.maintenance.is_file()


def test_actual_persistent_drift_in_ready_ack_gap_is_rejected_before_first_native_apply(component):
    value = component
    before = process._state(value.parent)
    changed = []

    def drift(hello):
        checked_ready(value, hello)
        mutate(value.parent)
        changed.append(process._state(value.parent))

    with pytest.raises(RestoreRejected, match="SOURCE_REPLAY_WORKER_REJECTED"):
        exchange(value, ready=drift)
    assert changed and changed[0] != before and process._state(value.parent) == changed[0]
    assert not value.phases and not value.final_seen
    actual = fact_state(value.dsn, value.native_state)
    assert actual["old_status"] == "superseded" and actual["old_body_present"]
    assert actual["checkpoint_counts"] == [1, 1, 1] and actual["run_status"] == "stale"


def test_forged_authority_is_closed_and_actual_final_drift_with_live_child_never_gets_done_ack(component, monkeypatch):
    value = component

    def forbidden(*args, **kwargs):
        pytest.fail("UNAUTHORIZED_SOURCE_REPLAY_MUST_NOT_START_A_PROCESS")

    with monkeypatch.context() as patch:
        patch.setattr(subprocess, "Popen", forbidden)
        with pytest.raises(RestoreRejected, match="SOURCE_FORWARD_OPAQUE_WITNESS_REQUIRED"):
            process.source_replay({"source_forward_completed": True}, value.pin)
        with pytest.raises(RestoreRejected, match="SOURCE_REPLAY_REVIEW_BINDING"):
            replace(value.pin, candidate="0" * 40).validate(value.proposal.request)
    changed = []

    def drift(result):
        checked_final(value, result)
        mutate(value.parent)
        changed.append(process._state(value.parent))
        checked_final(value, result)

    with pytest.raises(RestoreRejected, match="SOURCE_REPLAY_FINAL_STATE_CHANGED"):
        exchange(value, final=drift)
    assert value.phases == list(process.PHASES) and len(value.final_seen) == 1
    assert changed and process._state(value.parent) == changed[0]
    assert changed[0] != value.final_seen[0]["state_second_sha256"]
    actual = fact_state(value.dsn, value.native_state)
    assert actual["old_data_empty"] and actual["checkpoint_counts"] == [0, 0, 0]
    assert value.source.maintenance.is_file()  # Native work remains; there is no rollback/repair/retry.
