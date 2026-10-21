"""Only versioned case evidence enters the source/span/case closure and normal retention."""

from collections.abc import Iterator
from datetime import timedelta

import pytest
from psycopg import sql

from mingjing_core.application.agent_case_effect_marker import SCHEMA
from mingjing_core.application.memory import MemoryService
from mingjing_core.application.privacy_maintenance import PrivacyMaintenance
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import get_clock

from .case_effect_chain_support import prepare_chain
from .test_case_lifecycle_index_component_pg import legal_mutation_component
from .test_loop_cycle_support import cycle_repo as source_repo_fixture


@pytest.fixture(name="privacy_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


@pytest.mark.parametrize("target", ["message", "source_span", "case"])
def test_actual_privacy_replay_clears_case_evidence_without_broad_runtime_step_deletion(privacy_repo, target):
    case, source = legal_mutation_component(privacy_repo, "closed")
    effect = next(row for row in privacy_repo.list("alice", "runtime_step") if row.get("schema") == SCHEMA)
    assert source["id"] in effect["source_ids"] and case["id"] in effect["case_ids"]
    kept = privacy_repo.put(
        "alice",
        "runtime_step",
        "unrelated-old-protocol",
        {
            "schema": "synthetic-other-protocol",
            "run_id": "no-such-run",
            "output": {"text": "其它私有协议"},
            "source_ids": [source["id"]],
        },
    )
    metadata = {"message_id": source["id"], "start": 0, "end": 2} if target == "source_span" else {}
    ident = case["id"] if target == "case" else source["id"] if target == "message" else "synthetic-span"
    privacy_repo.apply_privacy(
        "alice",
        {
            "schema_version": "core3.0",
            "owner_user_id": "alice",
            "revocations": [
                {"kind": target, "entity_id": ident, "operation": "deleted", "metadata": metadata},
            ],
        },
    )
    cleared = privacy_repo.get("alice", "runtime_step", effect["id"], include_deleted=True)
    assert cleared["status"] == "deleted" and "output" not in cleared
    assert privacy_repo.get("alice", "runtime_step", kept["id"]) == kept


def test_unrelated_span_and_other_owner_leave_case_evidence_unchanged(privacy_repo):
    legal_mutation_component(privacy_repo, "closed")
    effect = next(row for row in privacy_repo.list("alice", "runtime_step") if row.get("schema") == SCHEMA)
    other = MemoryService(privacy_repo).receive(
        "alice", content="完全无关的原话片段", source_id="unrelated-span-source"
    )
    privacy_repo.apply_privacy(
        "alice",
        {
            "schema_version": "core3.0",
            "owner_user_id": "alice",
            "revocations": [
                {
                    "kind": "source_span",
                    "entity_id": "unrelated-span",
                    "operation": "deleted",
                    "metadata": {"message_id": other["id"], "start": 0, "end": 2},
                },
            ],
        },
    )
    privacy_repo.apply_privacy(
        "bob",
        {
            "schema_version": "core3.0",
            "owner_user_id": "bob",
            "revocations": [
                {"kind": "message", "entity_id": effect["source_ids"][0], "operation": "deleted", "metadata": {}},
            ],
        },
    )
    assert privacy_repo.get("alice", "runtime_step", effect["id"]) == effect


@pytest.mark.parametrize("complete", [False, True])
def test_new_private_effects_share_thirty_day_retention_without_expiring_published_result(
    privacy_repo, monkeypatch, complete
):
    prepared = prepare_chain(privacy_repo, monkeypatch)
    result = prepared.finish() if complete else None
    with privacy_repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET updated_at=%s WHERE id=%s").format(privacy_repo.table("core_runs")),
            (get_clock().now() - timedelta(days=31), prepared.run["id"]),
        )
    assert PrivacyMaintenance(privacy_repo).tick()["private_steps"] == int(complete)
    remaining = [row for row in privacy_repo.list("alice", "runtime_step") if row.get("schema") == SCHEMA]
    assert bool(remaining) is not complete
    if complete:
        assert privacy_repo.fetch_run("alice", prepared.run["id"])["result"] == result
        assert privacy_repo.get("alice", "message", result["message_id"])["content"] == result["text"]
