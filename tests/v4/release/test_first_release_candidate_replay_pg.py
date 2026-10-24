"""Native replay comes from real committed candidates, including an actually unfixed negative."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import replace

import psycopg
import pytest
from first_release_support import ROOT, write_json
from test_first_release_candidate_preflight_pg import assert_retained
from test_first_release_candidate_preflight_pg import candidate as candidate
from test_first_release_local_restore_pg import sample as sample
from test_first_release_replay_idempotence_pg import assert_erased, complete_state, seed_owner

from mingjing_core.adapters.tarot import TarotService
from mingjing_core.application.memory import MemoryService
from mingjing_core.repositories.postgres import PostgresRepository
from tools import first_release_candidate_process as process
from tools import first_release_local_restore as restore
from tools.deploy_core import export_withdrawals
from tools.first_release_candidate_process import CandidateReplay
from tools.first_release_contracts import RestoreRejected
from tools.first_release_local_inputs import file_hash

GOOD = "90a27fbcb5375fd881c3fea9494b000babc6fd74"
OLD = "7e3d098"


@pytest.fixture(scope="module")
def archives():
    environment = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP") if key in os.environ}
    result = {}
    for ref in (GOOD, OLD):
        head = (
            subprocess.run(["git", "rev-parse", ref], cwd=ROOT, env=environment, capture_output=True, check=True)
            .stdout.decode()
            .strip()
        )
        archive = subprocess.run(
            ["git", "archive", "--format=tar", head], cwd=ROOT, env=environment, capture_output=True, check=True
        ).stdout
        result[ref] = head, archive
    return result


@pytest.fixture
def canonical_source(request, archives):
    return archives[getattr(request, "param", GOOD)]


def pinned(candidate, document):
    sample, base = candidate
    write_json(base.ledger, document)
    pin = dict(base.pin)
    pin.update(
        schema="first-release-local-replay-pin-v1",
        effects_sha256=file_hash(process.EFFECTS),
        ledger_sha256=file_hash(base.ledger),
        dump_sha256=sample.inputs.dump_pin.dump_sha256,
    )
    return CandidateReplay.parse(base.python, base.ledger, pin)


def prepare(candidate):
    sample, _ = candidate
    repo = PostgresRepository(sample.source, initialize=False, max_size=1)
    try:
        source, fact, run = seed_owner(repo, "alice")
        _, _, bob = seed_owner(repo, "bob")
        draws = {}
        for owner in ("alice", "bob"):
            case = MemoryService(repo).create_case(owner, "self", "SYNTHETIC_DRAW", operation_id="case-" + owner)
            draws[owner] = TarotService(repo).create_draw(
                owner, subject_id="self", case_id=case["id"], question="SYNTHETIC_DRAW", idempotency_key="draw-" + owner
            )["draw"]["id"]
        sample.dump()
        MemoryService(repo).retire_fact("alice", fact["id"], expected_revision=fact["revision"], scope="source")
        repo.mutation_request(
            "alice",
            "tarot-delete:" + draws["alice"],
            "synthetic-delete",
            {},
            lambda: TarotService(repo).delete("alice", draws["alice"]),
        )
        with repo.transaction("alice") as connection:
            connection.execute(
                "UPDATE mingjing_core.delivery_outbox SET status='sent',receipt='om_synthetic_sent',"
                "attempts=1 WHERE id='alice-sent'"
            )
            connection.execute(
                "UPDATE mingjing_core.delivery_outbox SET status='sending',attempts=1 WHERE id='alice-uncertain'"
            )
        document = export_withdrawals(repo)
        assert any(row["revocations"] for row in document["owners"]) and document["deleted_draws"]
        return pinned(candidate, document), (source, fact, run, bob, draws)
    finally:
        repo.close()


def apply(candidate, request):
    sample, _ = candidate
    return restore.execute(
        sample.inputs, apply_local=True, upgrade_local=True, withdrawals_replay=request, environment=sample.environment
    )


def observe(monkeypatch, snapshots, bob=None):
    original = process.candidate_replay

    def observed(request, inputs, dsns, creator):
        repo = PostgresRepository(dsns["owner"], initialize=False, max_size=1)
        try:
            snapshots.append(complete_state(repo, owner="bob", run_id=bob["id"]) if bob else complete_state(repo))
            try:
                return original(request, inputs, dsns, creator)
            finally:
                snapshots.append(complete_state(repo, owner="bob", run_id=bob["id"]) if bob else complete_state(repo))
        finally:
            repo.close()

    monkeypatch.setattr(process, "candidate_replay", observed)


def closed(proof):
    for key in (
        "central_binding_verified",
        "runtime_verified",
        "native_restore_completed",
        "linux_attestation",
        "publication",
    ):
        assert proof[key] is False
    assert proof["model_calls"] == proof["external_sends"] == 0


@pytest.mark.parametrize("sample", [7], indirect=True)
def test_real_committed_candidate_replays_nonempty_ledger_twice_and_preserves_other_owner(candidate, monkeypatch):
    request, (source, fact, run, bob, draws) = prepare(candidate)
    snapshots = []
    observe(monkeypatch, snapshots, bob)
    result = apply(candidate, request)
    proof = result["withdrawals_replay"]
    closed(proof)
    assert result["database_connections"] == 9 and proof["database_connections"] == 2
    assert proof["preflight"]["candidate"] == GOOD
    assert proof["latest_withdrawals_replayed"] is proof["second_apply_unchanged"] is proof["central_unchanged"] is True
    assert proof["state_before_sha256"] != proof["state_first_sha256"] == proof["state_second_sha256"]
    assert proof["export_first_sha256"] == proof["export_second_sha256"]
    assert proof["first_counts"]["draw_tombstones_added"] == 1
    assert proof["second_counts"]["draw_tombstones_added"] == proof["second_counts"]["deleted_draws"] == 0
    assert proof["checks"]["checkpoint_ranges_checked"] >= 6 and snapshots[0] == snapshots[1]
    sample, _ = candidate
    repo = PostgresRepository(sample.environment["FIRST_RELEASE_OWNER_DSN"], initialize=False, max_size=1)
    try:
        assert_erased(repo, source, fact, run)
        assert TarotService(repo).get("bob", draws["bob"])["question"] == "SYNTHETIC_DRAW"
        assert export_withdrawals(repo) == json.loads(request.preflight.ledger.read_text(encoding="utf-8"))
    finally:
        repo.close()


def test_prefix_four_empty_replay_remains_local_and_is_idempotent(candidate):
    sample, base = candidate
    request = pinned(candidate, json.loads(base.ledger.read_text(encoding="utf-8")))
    proof = apply(candidate, request)["withdrawals_replay"]
    closed(proof)
    assert len(sample.inputs.dump_pin.source_migrations) == 4
    assert proof["state_before_sha256"] == proof["state_first_sha256"] == proof["state_second_sha256"]


@pytest.mark.parametrize("sample", [7], indirect=True)
@pytest.mark.parametrize("canonical_source", [OLD], indirect=True)
def test_real_old_candidate_does_not_borrow_controller_idempotence_fix(candidate):
    request, (source, fact, run, _, _) = prepare(candidate)
    assert candidate[0].inputs.release.candidate != GOOD
    with pytest.raises(RestoreRejected, match="REPLAY_SECOND_STATE_CHANGED"):
        apply(candidate, request)
    assert_retained(candidate)
    repo = PostgresRepository(candidate[0].environment["FIRST_RELEASE_OWNER_DSN"], initialize=False, max_size=1)
    try:
        assert_erased(repo, source, fact, run)
    finally:
        repo.close()


def test_replay_requires_explicit_pin_and_same_call_before_any_connection(candidate, monkeypatch):
    sample, base = candidate
    request = pinned(candidate, json.loads(base.ledger.read_text(encoding="utf-8")))

    def forbidden(*args, **kwargs):
        pytest.fail("REPLAY_GATE_MUST_PRECEDE_ANY_CONNECTION_OR_PROCESS")

    monkeypatch.setattr(psycopg, "connect", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    for invalid, code in ((True, "EXPLICIT_REPLAY_PIN_REQUIRED"), (request, "REPLAY_REQUIRES_SAME_CALL_APPLY_UPGRADE")):
        with pytest.raises(RestoreRejected, match=code):
            restore.execute(sample.inputs, withdrawals_replay=invalid, environment=sample.environment)


def test_changed_effects_pin_is_refused_before_creating_any_target(candidate):
    sample, base = candidate
    request = replace(pinned(candidate, json.loads(base.ledger.read_text(encoding="utf-8"))), effects_sha256="0" * 64)
    with pytest.raises(RestoreRejected, match="REPLAY_HELPER_CHANGED"):
        apply(candidate, request)
    assert sample.present() == (False, 0)


@pytest.mark.parametrize("sample", [7], indirect=True)
def test_stale_latest_ledger_refuses_before_first_apply_and_preserves_full_state(candidate, monkeypatch):
    request, _ = prepare(candidate)
    sample, _ = candidate
    sample.dump()  # Backup now includes actual newer native revocations and external receipts.
    document = json.loads(request.preflight.ledger.read_text(encoding="utf-8"))
    for owner in document["owners"]:
        owner["revocations"] = []
    document["deleted_draws"] = []
    document["delivery_receipts"] = []
    request = pinned(candidate, document)
    snapshots = []
    observe(monkeypatch, snapshots)
    with pytest.raises(RestoreRejected, match="REPLAY_STALE_LEDGER"):
        apply(candidate, request)
    assert_retained(candidate)
    assert snapshots[0] == snapshots[1]


@pytest.mark.parametrize("sample", [7], indirect=True)
def test_owner_collision_rolls_back_whole_first_apply_and_never_runs_second(candidate, monkeypatch):
    request, (_, _, _, _, draws) = prepare(candidate)
    document = json.loads(request.preflight.ledger.read_text(encoding="utf-8"))
    document["deleted_draws"].append({"owner": "bob", "draw_id": draws["alice"]})
    request = pinned(candidate, document)
    snapshots = []
    observe(monkeypatch, snapshots)
    with pytest.raises(RestoreRejected, match="REPLAY_FIRST_APPLY_FAILED"):
        apply(candidate, request)
    assert_retained(candidate)
    assert snapshots[0] == snapshots[1], "FAILED_WHOLE_OWNER_TRANSACTION_MUST_PRESERVE_COMPLETE_STATE"
