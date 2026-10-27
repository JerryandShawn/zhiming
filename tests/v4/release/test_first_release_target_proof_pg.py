"""Actual held-target proof lifecycle and current physical-state rejection, on disposable PG15."""

from __future__ import annotations

import copy
import json
import pickle
from contextlib import contextmanager, suppress
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row
from test_first_release_capture_binding_pg import captured as shared_captured
from test_first_release_capture_binding_pg import source_document
from test_first_release_incremental_backup_pg import archive as archive
from test_first_release_incremental_backup_pg import existing as existing

from tools import first_release_candidate_process as process
from tools import first_release_incremental_pg as incremental_pg
from tools import first_release_local_pg as local_pg
from tools import first_release_local_restore as restore
from tools import first_release_target_proof as proof_module
from tools.first_release_candidate_process import CandidateReplay
from tools.first_release_contracts import RestoreRejected
from tools.first_release_incremental import BackupInputs, file_hash
from tools.first_release_incremental_pg import snapshot
from tools.first_release_target_proof import TargetProof, TargetProofPin, consume_target_proof, target_binding


@pytest.fixture
def observe_ledger_sessions(request, monkeypatch):
    if request.node.name != "test_actual_ledger_bytes_after_mint_are_rechecked_and_never_replayed_again":
        return
    original = incremental_pg.sessions

    def checked(connection, allowed):
        try:
            original(connection, allowed)
        except RestoreRejected as error:
            if str(error) != "INCREMENTAL_OTHER_SOURCE_SESSION":
                raise
            record = dict(observation="after_rejection_current", code=str(error), allowed_pids=sorted(allowed))
            try:
                connection.execute("SELECT pg_stat_clear_snapshot()")
                record["current_after_rejection"] = connection.execute(
                    "SELECT pid,backend_type FROM pg_stat_activity WHERE datname=current_database() ORDER BY pid"
                ).fetchall()
            except Exception:
                record["observation_failed"] = True
            # Observation must never replace the original strict, body-free safety rejection.
            with suppress(Exception):
                folder = proof_module.ROOT / "private" / ("target-proof-session-observation-" + uuid4().hex)
                folder.mkdir(parents=True)
                (folder / "diagnostic.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
            raise

    monkeypatch.setattr(incremental_pg, "sessions", checked)


@pytest.fixture
def proof_case(existing, observe_ledger_sessions):  # noqa: F811
    existing.inputs = BackupInputs.parse(source_document(existing.inputs), existing.inputs.workspace)
    with psycopg.connect(existing.environment["FIRST_INCREMENTAL_OWNER_DSN"]) as owner:
        owner.execute(
            "INSERT INTO mingjing_core.core_revocations(owner,kind,entity_id,operation,revision) "
            "VALUES('synthetic','message','synthetic-message','synthetic-proof-revocation',2)"
        )
    with contextmanager(shared_captured.__wrapped__)(existing, SimpleNamespace(param="core-only")) as case:
        source = case.source.inputs
        ledger = case.inputs.contract.candidate_source.parent / "latest-withdrawals.json"
        ledger.write_bytes((source.operation_dir / "latest-withdrawals.json").read_bytes())
        replay = CandidateReplay.parse(
            source.python,
            ledger,
            dict(
                schema="first-release-local-replay-pin-v1",
                candidate=case.inputs.release.candidate,
                manifest_sha256=case.inputs.release.manifest_sha256,
                dump_sha256=case.inputs.dump_pin.dump_sha256,
                ledger_sha256=file_hash(ledger),
                python_sha256=source.python_sha256,
                worker_sha256=file_hash(process.WORKER),
                effects_sha256=file_hash(process.EFFECTS),
            ),
        )
        pin = TargetProofPin(
            target_binding(case.inputs, case.binding, replay),
            tuple(sorted((name, file_hash(proof_module.ROOT / name)) for name in proof_module.CONTROLS)),
        )
        yield SimpleNamespace(case=case, replay=replay, pin=pin, source=source)


def held(value, **changes):
    arguments = dict(
        apply_local=True,
        upgrade_local=True,
        capture_binding=value.case.binding,
        withdrawals_replay=value.replay,
        target_proof_pin=value.pin,
        environment=value.case.environment,
    )
    return restore._proved_target(value.case.inputs, **dict(arguments, **changes))


def state(dsn):
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        return snapshot(connection)


def test_actual_candidate_chain_yields_opaque_once_only_current_proof_and_never_source_authority(proof_case):
    value = proof_case
    before = state(value.case.source.environment["FIRST_INCREMENTAL_OWNER_DSN"])
    with held(value) as proof:
        assert type(proof) is TargetProof and repr(proof) == "<TargetProof>"
        with pytest.raises(RestoreRejected, match="TARGET_PROOF_NOT_CONSTRUCTIBLE"):
            TargetProof()
        for serializer in (copy.copy, pickle.dumps):
            with pytest.raises(RestoreRejected, match="TARGET_PROOF_NOT_SERIALIZABLE"):
                serializer(proof)
        for fake in ({"target_proof_consumed": True}, object.__new__(TargetProof)):
            with pytest.raises(RestoreRejected, match="TARGET_PROOF_(OPAQUE_INSTANCE_REQUIRED|EXPIRED_OR_CONSUMED)"):
                consume_target_proof(fake, source=value.source)
        result = consume_target_proof(proof, source=value.source)
        assert result["target_proof_consumed"] is True and result["target_database_connections"] == 16
        assert result["final_target_database_connections"] == 6 and len(result["target_state_sha256"]) == 64
        for key in (
            "source_write_authorized",
            "controller_runtime_verified",
            "source_restore_content_verified",
            "native_restore_completed",
            "runtime_verified",
            "central_binding_verified",
            "linux_attestation",
            "publication",
            "global_quiescence_verified",
        ):
            assert result[key] is False
        with pytest.raises(RestoreRejected, match="TARGET_PROOF_EXPIRED_OR_CONSUMED"):
            consume_target_proof(proof, source=value.source)
        with psycopg.connect(value.case.environment["FIRST_RELEASE_OWNER_DSN"]) as owner:
            assert owner.execute(
                "SELECT status,data FROM mingjing_core.core_entities WHERE owner='synthetic' "
                "AND kind='message' AND id='synthetic-message'"
            ).fetchone() == ("deleted", {})
    assert state(value.case.source.environment["FIRST_INCREMENTAL_OWNER_DSN"]) == before


def test_context_exit_revokes_unconsumed_proof_without_removing_restored_database(proof_case):
    with held(proof_case) as proof:
        assert type(proof) is TargetProof
    with pytest.raises(RestoreRejected, match="TARGET_PROOF_EXPIRED_OR_CONSUMED"):
        consume_target_proof(proof, source=proof_case.source)
    with psycopg.connect(proof_case.case.environment["FIRST_RELEASE_OWNER_DSN"]) as owner:
        assert owner.execute("SELECT max(version) FROM mingjing_core.schema_migrations").fetchone() == (8,)


def test_same_name_recreated_database_is_not_the_process_registered_birth(proof_case):
    value = proof_case
    with held(value) as proof:
        with psycopg.connect(value.case.environment["FIRST_RELEASE_ADMIN_DSN"], autocommit=True) as admin:
            database = sql.Identifier(value.case.inputs.contract.database)
            admin.execute(sql.SQL("DROP DATABASE {}").format(database))
            admin.execute(
                sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0").format(
                    database, sql.Identifier(value.case.inputs.contract.database + "_owner")
                )
            )
        with pytest.raises(RestoreRejected, match="TARGET_PROOF_CREATED_IDENTITY_CHANGED"):
            consume_target_proof(proof, source=value.source)
        with pytest.raises(RestoreRejected, match="TARGET_PROOF_EXPIRED_OR_CONSUMED"):
            consume_target_proof(proof, source=value.source)


def test_actual_target_dml_after_mint_rejects_stale_proof_and_burns_the_token(proof_case):
    value = proof_case
    with held(value) as proof:
        with psycopg.connect(value.case.environment["FIRST_RELEASE_OWNER_DSN"]) as owner:
            owner.execute(
                "UPDATE mingjing_core.core_subjects SET label='synthetic-target-drift' "
                "WHERE owner='synthetic' AND id='self'"
            )
        changed = state(value.case.environment["FIRST_RELEASE_OWNER_DSN"])
        with pytest.raises(RestoreRejected, match="TARGET_PROOF_TARGET_STATE_CHANGED"):
            consume_target_proof(proof, source=value.source)
        assert state(value.case.environment["FIRST_RELEASE_OWNER_DSN"]) == changed
        with pytest.raises(RestoreRejected, match="TARGET_PROOF_EXPIRED_OR_CONSUMED"):
            consume_target_proof(proof, source=value.source)


def test_actual_ledger_bytes_after_mint_are_rechecked_and_never_replayed_again(proof_case):
    value = proof_case
    with held(value) as proof:
        before = state(value.case.environment["FIRST_RELEASE_OWNER_DSN"])
        value.replay.preflight.ledger.write_bytes(value.replay.preflight.ledger.read_bytes() + b" ")
        with pytest.raises(RestoreRejected, match="PREFLIGHT_REVIEWED_FILE_CHANGED"):
            consume_target_proof(proof, source=value.source)
        assert state(value.case.environment["FIRST_RELEASE_OWNER_DSN"]) == before
        with pytest.raises(RestoreRejected, match="TARGET_PROOF_EXPIRED_OR_CONSUMED"):
            consume_target_proof(proof, source=value.source)


def pollute_after_real_replay(value, monkeypatch, mutation):
    original = process.candidate_replay

    def actual_then_pollute(*arguments):
        result = original(*arguments)
        with psycopg.connect(value.case.environment["FIRST_RELEASE_OWNER_DSN"]) as owner:
            owner.execute(mutation)
        return result

    monkeypatch.setattr(process, "candidate_replay", actual_then_pollute)


def test_real_post_replay_acl_change_is_rejected_before_any_proof_yield(proof_case, monkeypatch):
    value = proof_case
    writer = sql.Identifier(value.case.inputs.contract.database + "_writer")
    pollute_after_real_replay(
        value, monkeypatch, sql.SQL("GRANT DELETE ON mingjing_core.core_model_authorizations TO {}").format(writer)
    )
    with pytest.raises(RestoreRejected, match="EXACT_TABLE_ACL_MISMATCH"), held(value):
        pytest.fail("PROOF_MUST_NOT_YIELD_AFTER_POST_REPLAY_ACL_POLLUTION")


def test_real_post_replay_sequence_use_is_rejected_before_any_proof_yield(proof_case, monkeypatch):
    pollute_after_real_replay(proof_case, monkeypatch, "SELECT nextval('mingjing_core.core_model_usage_id_seq')")
    with pytest.raises(RestoreRejected, match="TARGET_PROOF_CENTRAL_SEQUENCE_USED"), held(proof_case):
        pytest.fail("PROOF_MUST_NOT_YIELD_AFTER_CENTRAL_SEQUENCE_USE")


def test_default_public_json_and_missing_flags_are_zero_target_effects_and_birth_requires_live_creator(
    proof_case,
    monkeypatch,
):
    value = proof_case

    def forbidden(*arguments, **keywords):
        pytest.fail("DEFAULT_VALIDATION_MUST_NOT_CONNECT_OR_SPAWN")

    with monkeypatch.context() as patch:
        patch.setattr(psycopg, "connect", forbidden)
        patch.setattr(restore.subprocess, "run", forbidden)
        result = restore.execute(value.case.inputs)
        assert result["database_connections"] == result["mutations"] == 0
        with (
            pytest.raises(RestoreRejected, match="TARGET_PROOF_EXPLICIT_APPLY_UPGRADE_REQUIRED"),
            held(
                value,
                apply_local=False,
            ),
        ):
            pytest.fail("MISSING_EXPLICIT_FLAGS_MUST_NOT_YIELD")
    dsns = value.case.inputs.connections(value.case.environment)
    with (
        psycopg.connect(dsns["admin"], autocommit=True) as unknown,
        pytest.raises(RestoreRejected, match="LOCAL_TARGET_LIVE_CREATION_REQUIRED"),
    ):
        local_pg._birth_identity(value.case.inputs, unknown)
    with local_pg.new_target(value.case.inputs, dsns) as creator:
        assert local_pg._birth_identity(value.case.inputs, creator).creator is creator
        creator.close()
        with pytest.raises(RestoreRejected, match="LOCAL_TARGET_LIVE_CREATION_REQUIRED"):
            local_pg._birth_identity(value.case.inputs, creator)
    with pytest.raises(RestoreRejected, match="LOCAL_TARGET_LIVE_CREATION_REQUIRED"):
        local_pg._birth_identity(value.case.inputs, creator)
