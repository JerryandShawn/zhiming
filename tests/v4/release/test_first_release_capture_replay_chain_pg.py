"""One actual prefix7 capture/original-restore/upgrade/native-replay chain; all seeds are synthetic."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import uuid
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace

import psycopg
import pytest
from first_release_support import ROOT, write_json
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from test_first_release_candidate_replay_pg import observe
from test_first_release_capture_binding_pg import captured as shared_captured
from test_first_release_incremental_backup_pg import existing as shared_existing
from test_first_release_source_span_pg import NATIVE

from tools import first_release_candidate_process as process
from tools import first_release_local_restore as restore
from tools.first_release_candidate_process import CandidateReplay
from tools.first_release_incremental import file_hash
from tools.first_release_incremental_pg import snapshot

CANDIDATE = "206f43f0dd05b1c2c87f12b0bf7d27fce703208e"


@pytest.fixture(scope="module")
def archive():
    environment = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP") if key in os.environ}
    actual = (
        subprocess.run(["git", "rev-parse", CANDIDATE], cwd=ROOT, env=environment, capture_output=True, check=True)
        .stdout.decode()
        .strip()
    )
    assert actual == CANDIDATE
    content = subprocess.run(
        ["git", "archive", "--format=tar", actual], cwd=ROOT, env=environment, capture_output=True, check=True
    ).stdout
    return actual, content


@pytest.fixture(name="existing")
def source_fixture(request, archive):
    yield from shared_existing.__wrapped__(request, archive)


def native(source, dsn, action, state=None, *, root=None):
    inputs = source.inputs
    payload = {
        "worker": str(process.WORKER),
        "python": str(inputs.python),
        "root": str(root or inputs.candidate_source),
        "core_lock_sha256": dict(inputs.release.locks)["requirements-core.lock"],
        "pin": {
            "candidate": inputs.release.candidate,
            "manifest_sha256": inputs.release.manifest_sha256,
            "python_sha256": inputs.python_sha256,
            "worker_sha256": file_hash(process.WORKER),
        },
        "action": action,
        "state": state,
    }
    environment = process._environment(dsn)
    environment["NATIVE_LOCAL_DSN"] = dsn
    result = subprocess.run(
        [str(inputs.python), "-I", "-B", "-X", "pycache_prefix=" + os.path.abspath(os.devnull), "-c", NATIVE],
        input=json.dumps(payload),
        env=environment,
        capture_output=True,
        encoding="utf-8",
        timeout=120,
        shell=False,
    )
    assert result.returncode == 0, "NATIVE_CAPTURE_REPLAY_SEED_FAILED_PRIVATE_DETAILS_WITHHELD"
    value = json.loads(result.stdout)
    assert value["candidate"] == CANDIDATE and value["candidate_modules_checked"] > 0
    return value


def source_state(source):
    with psycopg.connect(source.environment["FIRST_INCREMENTAL_OWNER_DSN"], row_factory=dict_row) as connection:
        return snapshot(connection)


def seed_blob_checkpoint(dsn, state):
    # Explicit synthetic SDK fixture: primitives are inline, so they cannot prove blob capture/purge.
    config = {"configurable": {"thread_id": state["run"] + ":e0", "checkpoint_ns": ""}}
    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row, prepare_threshold=0) as connection:
        saver = PostgresSaver(connection)
        previous = saver.get_tuple(config)
        assert previous is not None and previous.checkpoint["channel_values"]["private"] == "SYNTHETIC_CHECKPOINT_BODY"
        checkpoint = dict(previous.checkpoint)
        checkpoint["channel_values"] = {"private": {"synthetic_body": ["SYNTHETIC_CHECKPOINT_BODY"]}}
        checkpoint["channel_versions"] = {"private": "2"}
        saver.put(config, checkpoint, previous.metadata, {"private": "2"})
        counts = [
            connection.execute(
                "SELECT count(*) AS n FROM public." + table + " WHERE thread_id=%s", (state["run"] + ":e0",)
            ).fetchone()["n"]
            for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes")
        ]
        assert counts == [1, 1, 1]


def fact_state(dsn, state):
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET LOCAL TimeZone='UTC'")
        old = connection.execute(
            "SELECT status,data FROM mingjing_core.core_entities WHERE owner='alice' AND kind='fact' AND id=%s",
            (state["night"],),
        ).fetchone()
        corrected = connection.execute(
            "SELECT status,encode(sha256(convert_to(to_jsonb(e)::text,'UTF8')),'hex') AS sha256 "
            "FROM mingjing_core.core_entities e WHERE owner='alice' AND kind='fact' AND id=%s",
            (state["corrected"],),
        ).fetchone()
        run = connection.execute(
            "SELECT status,error,request,result,checkpoint,lease_token,lease_until FROM mingjing_core.core_runs "
            "WHERE owner='alice' AND id=%s",
            (state["run"],),
        ).fetchone()
        outbox = connection.execute(
            "SELECT status,payload,claim_token,lease_until FROM mingjing_core.delivery_outbox "
            "WHERE owner='alice' AND id='synthetic-span-pending'"
        ).fetchone()
        checkpoints = [
            connection.execute(
                "SELECT count(*) AS n FROM public." + table + " WHERE thread_id=%s", (state["run"] + ":e0",)
            ).fetchone()["n"]
            for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes")
        ]
        busy = connection.execute(
            "SELECT count(*) AS n FROM mingjing_core.core_runs "
            "WHERE status IN ('queued','running') OR lease_until>now()"
        ).fetchone()["n"]
        prefix = connection.execute("SELECT max(version) AS v FROM mingjing_core.schema_migrations").fetchone()["v"]
    return {
        "old_status": old["status"],
        "old_body_present": bool(old["data"].get("content")),
        "old_data_empty": old["data"] == {},
        "corrected": corrected,
        "run_status": run["status"],
        "run_error": run["error"],
        "run_request_matches_original": run["request"]
        == {"source_message_id": state["source"], "message": "我不能上夜班。我喜欢周末徒步。"},
        "run_request_empty": run["request"] == {},
        "run_request_sha256": hashlib.sha256(json.dumps(run["request"], sort_keys=True).encode()).hexdigest(),
        "run_outputs_cleared": run["checkpoint"] == {}
        and run["result"] is run["lease_token"] is run["lease_until"] is None,
        "checkpoint_counts": checkpoints,
        "outbox_status": outbox["status"],
        "outbox_outputs_cleared": outbox["payload"] == {} and outbox["claim_token"] is outbox["lease_until"] is None,
        "busy": busy,
        "prefix": prefix,
    }


@pytest.fixture
def chain(existing):
    source = existing
    dsn = source.environment["FIRST_INCREMENTAL_OWNER_DSN"]
    # Build the legal migration profile before capture, rather than bypassing M2's relation/ACL checks.
    with psycopg.connect(dsn) as connection:
        connection.execute("DROP SEQUENCE mingjing_core.synthetic_backup_seq")
    initial = native(source, dsn, "seed")
    seed_blob_checkpoint(dsn, initial["state"])
    latest = native(source, dsn, "correct", initial["state"])
    state = latest["state"]
    with psycopg.connect(dsn) as connection:
        owners = tuple(row[0] for row in connection.execute("SELECT id FROM mingjing_core.core_owners ORDER BY id"))
    assert owners == ("alice", "bob", "synthetic")
    source.inputs = replace(source.inputs, source=replace(source.inputs.source, owners=owners))
    before = source_state(source)
    original = fact_state(dsn, state)
    folder = ROOT / "private" / ("capture-replay-chain-" + uuid.uuid4().hex)
    folder.mkdir(parents=True)
    write_json(folder / "metadata.json", dict(candidate=CANDIDATE, before=original, real_models=0, servers=0))
    assert state["old_status"] == original["old_status"] == "superseded" and original["old_body_present"]
    assert original["prefix"] == 7 and original["busy"] == 0
    assert original["corrected"]["status"] == "active"
    assert original["run_status"] == original["outbox_status"] == "stale" and original["run_error"] == "STALE_INPUT"
    assert original["run_request_matches_original"] is original["run_outputs_cleared"] is True
    assert original["outbox_outputs_cleared"] is True and original["checkpoint_counts"] == [1, 1, 1]
    with contextmanager(shared_captured.__wrapped__)(source, SimpleNamespace()) as case:
        captured = json.loads((source.inputs.operation_dir / "backup-receipt.json").read_text())
        assert captured["source_snapshots"]["before"] == captured["source_snapshots"]["after"] == before
        assert source_state(source) == before
        yield case, state, original, before, captured, folder


def replay_request(case):
    inputs, source = case.inputs, case.source.inputs
    path = inputs.contract.candidate_source.parent / "latest-withdrawals.json"
    original = source.operation_dir / "latest-withdrawals.json"
    path.write_bytes(original.read_bytes())
    assert file_hash(path) == case.binding.pin.ledger_sha256
    return CandidateReplay.parse(
        source.python,
        path,
        {
            "schema": "first-release-local-replay-pin-v1",
            "candidate": inputs.release.candidate,
            "manifest_sha256": inputs.release.manifest_sha256,
            "dump_sha256": inputs.dump_pin.dump_sha256,
            "ledger_sha256": file_hash(path),
            "python_sha256": source.python_sha256,
            "worker_sha256": file_hash(process.WORKER),
            "effects_sha256": file_hash(process.EFFECTS),
        },
    )


def assert_proofs(case, captured, result):
    binding, replay = result["capture_binding"], result["withdrawals_replay"]
    assert binding["source_operation_id"] == case.source.inputs.operation_id
    assert binding["target_operation_id"] == case.inputs.contract.operation_id
    assert case.inputs.contract.database != case.source.inputs.source.database
    assert binding["source_state_sha256"] == captured["source_state_sha256"]
    assert binding["local_original_content_verified"] is binding["local_capture_binding_verified"] is True
    assert binding["source_projection"] == "postgres-jsonb-utc-v1" and binding["tables_checked"] > 10
    assert captured["dump_sha256"] == case.inputs.dump_pin.dump_sha256 == case.binding.pin.dump_sha256
    assert captured["ledger_sha256"] == case.binding.pin.ledger_sha256
    assert result["local_upgrade_completed"] is result["latest_withdrawals_replayed"] is True
    assert result["original_prefix"] == dict(case.inputs.dump_pin.source_migrations)
    assert result["upgraded_migrations"] == dict(case.inputs.release.migrations)
    assert result["database_connections"] == 10
    assert replay["state_first_sha256"] == replay["state_second_sha256"]
    assert replay["export_first_sha256"] == replay["export_second_sha256"]
    assert replay["checks"]["span_sources_checked"] == replay["checks"]["span_facts_checked"] == 1
    assert replay["checks"]["span_preserved_facts_checked"] == 1
    for proof in (result, binding, replay):
        for key in ("source_restore_content_verified", "native_restore_completed", "linux_attestation", "publication"):
            if key in proof:
                assert proof[key] is False


def assert_actual_state(case, state, original, before, snapshots):
    dsn = case.environment["FIRST_RELEASE_OWNER_DSN"]
    actual = fact_state(dsn, state)
    assert actual["prefix"] == 8 and actual["busy"] == 0
    assert actual["old_status"] == "deleted" and actual["old_body_present"] is False
    assert actual["old_data_empty"] is actual["run_outputs_cleared"] is actual["run_request_empty"] is True
    assert actual["run_status"] == "revoked" and actual["run_error"] == "SOURCE_REVOKED"
    assert actual["outbox_status"] == "cancelled" and actual["outbox_outputs_cleared"] is True
    assert actual["checkpoint_counts"] == [0, 0, 0]
    assert actual["corrected"] == original["corrected"]
    observed = native(case.source, dsn, "observe", state, root=case.inputs.contract.candidate_source)["observed"]
    assert observed["raw_status"] == "active" and observed["fts_night"] is False
    assert observed["corrected_present"] is True
    assert all(value is True for name, value in observed.items() if name not in {"raw_status", "fts_night"})
    assert snapshots[0] == snapshots[1]
    assert source_state(case.source) == before
    assert fact_state(case.source.environment["FIRST_INCREMENTAL_OWNER_DSN"], state) == original
    return actual, observed


@pytest.mark.parametrize("existing", [7], indirect=True)
def test_actual_m1_capture_m2_original_compare_upgrade_and_native_double_replay_share_one_chain(chain, monkeypatch):
    case, state, original, before, captured, folder = chain
    request = replay_request(case)
    snapshots = []
    observe(monkeypatch, snapshots, {"id": state["bob_run"]})
    evidence = dict(
        candidate=CANDIDATE,
        before=original,
        real_models=0,
        external_sends=0,
        servers=0,
        correction_before_capture=True,
        explicit_nonprimitive_checkpoint_fixture=True,
    )
    write_json(folder / "metadata.json", evidence)
    try:
        result = restore.execute(
            case.inputs,
            apply_local=True,
            upgrade_local=True,
            capture_binding=case.binding,
            withdrawals_replay=request,
            environment=case.environment,
        )
        assert_proofs(case, captured, result)
        actual, observed = assert_actual_state(case, state, original, before, snapshots)
    except BaseException as error:
        write_json(folder / "metadata.json", dict(evidence, failure=type(error).__name__))
        raise
    write_json(
        folder / "metadata.json",
        dict(
            evidence,
            capture=captured,
            result=result,
            actual=actual,
            observed=observed,
            source_unchanged=True,
            other_owner_unchanged=snapshots[0] == snapshots[1],
            run_stale_before_capture=original["run_status"] == "stale",
            checkpoint_counts_before_capture=original["checkpoint_counts"],
        ),
    )
