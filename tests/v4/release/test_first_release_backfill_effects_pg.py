"""Two native business-effects components; no candidate process or source admission."""

from __future__ import annotations

import importlib
import os
import uuid
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import httpx
import psycopg
import pytest
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import sql
from psycopg.rows import dict_row

from mingjing_core.application.memory import MemoryService
from mingjing_core.memory.projections import tokenized_payload
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint
from tests.v4.test_p2_threads_backfill import seed_historical_runs
from tools.eval.targets.local_db import local_dsn
from tools.first_release_backfill_effects import BackfillState, observe_state, verify_backfill_effects
from tools.first_release_backfill_expected import WRITES, BackfillBindings


def checkpoint_fixture(dsn: str, schema: str) -> None:
    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as connection:
        connection.execute(sql.SQL("SET search_path={},public").format(sql.Identifier(schema)))
        saver = PostgresSaver(connection)
        saver.setup()
        checkpoint = empty_checkpoint()
        checkpoint["channel_values"] = {"synthetic": {"retained": "component checkpoint"}}
        checkpoint["channel_versions"] = {"synthetic": "1"}
        config = saver.put(
            {"configurable": {"thread_id": "synthetic-component:e0", "checkpoint_ns": ""}},
            checkpoint,
            {},
            {"synthetic": "1"},
        )
        saver.put_writes(config, [("synthetic", "component pending write")], "synthetic-task")


@pytest.fixture
def component(monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    dsn = os.getenv("CORE_TEST_DSN", "")
    if not dsn:
        pytest.skip("requires disposable loopback PostgreSQL 15")

    def reject(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("business-effects component forbids HTTP and child processes")

    monkeypatch.setattr(httpx.Client, "send", reject)
    monkeypatch.setattr(httpx.AsyncClient, "send", reject)
    monkeypatch.setattr("subprocess.run", reject)
    dsn, schema = local_dsn(dsn), "bf_effects_" + uuid.uuid4().hex
    repo = PostgresRepository(dsn, schema=schema, max_size=2)
    try:
        repo.ensure_owner("alice")
        repo.ensure_owner("bob")
        seed_historical_runs(repo, 2)
        MemoryService(repo).receive("bob", content="合成另一用户原话", source_id="bob-source")
        repo.mutation_request("bob", "synthetic-component", "receipt", {}, lambda: {"status": "saved"})
        checkpoint_fixture(dsn, schema)
        module = importlib.import_module("mingjing_core.memory.backfill")
        bindings = BackfillBindings(MemoryService, module, tokenized_payload, fingerprint)
        yield SimpleNamespace(repo=repo, bindings=bindings, module=module)
    finally:
        with repo.transaction() as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        repo.close()


def state(repo: PostgresRepository) -> BackfillState:
    with repo.transaction() as connection:
        return observe_state(connection, repo.schema)


def table_rows(repo: PostgresRepository, name: str) -> list[dict]:
    with repo.transaction() as connection:
        return [dict(row) for row in connection.execute(sql.SQL("SELECT * FROM {}").format(repo.table(name)))]


def test_core3_preview_exact_metadata_native_replies_operations_owner_and_second_zero(
    component: SimpleNamespace,
) -> None:
    repo = component.repo
    before = state(repo)
    owners = {row["id"]: row for row in before.rows["core_owners"]}
    result = verify_backfill_effects(repo, "alice", bindings=component.bindings)
    assert result["preview"] == result["first"]
    assert result["first"]["message_metadata"] == result["first"]["search_tokens"] == 2
    assert result["first"]["assistant_created"] == 2
    assert all(result["second"][key] == 0 for key in WRITES)
    assert result["second"]["assistant_existing"] == 2
    assert result["new_assistants_verified"] == 2 and result["generated_search_verified"] is True
    assert result["candidate_origin_verified"] is result["source_admission_verified"] is False
    assert "sample_ids" not in result and all(len(value) == 64 for value in result["sample_id_sha256"])
    after = state(repo)
    assert after.sequences == before.sequences and after.catalog == before.catalog and after.columns == before.columns
    assert after.hashes[repo.schema + ".core_runs"] == before.hashes[repo.schema + ".core_runs"]
    assert after.hashes[repo.schema + ".checkpoints"] == before.hashes[repo.schema + ".checkpoints"]
    assert after.hashes[repo.schema + ".checkpoint_blobs"] == before.hashes[repo.schema + ".checkpoint_blobs"]
    assert after.hashes[repo.schema + ".checkpoint_writes"] == before.hashes[repo.schema + ".checkpoint_writes"]
    assert (
        next(row for row in after.rows["core_owners"] if row["id"] == "alice")["revision"]
        == owners["alice"]["revision"] + 2
    )
    assert next(row for row in after.rows["core_owners"] if row["id"] == "bob") == owners["bob"]
    replies = [
        row for row in after.rows["core_entities"] if row["owner"] == "alice" and row["data"].get("role") == "assistant"
    ]
    assert len(replies) == 2 and len(after.rows["core_operations"]) == len(before.rows["core_operations"]) + 2
    for run in before.rows["core_runs"]:
        identifier = "msg_" + fingerprint(["alice", "assistant", run["id"]])[:32]
        reply = next(row for row in replies if row["id"] == identifier)
        assert reply["revision"] == 1 and reply["data"]["source_ids"] == [run["request"]["source_message_id"]]
        assert reply["data"]["content"] == run["result"]["answer"]


def test_actual_native_writes_then_ordinary_failure_roll_back_entire_backfill(
    component: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, before = component.repo, state(component.repo)
    original = component.module.record_assistant
    marker, reached = ValueError("SYNTHETIC_BACKFILL_AFTER_NATIVE_WRITE"), []
    owner_revision = next(row["revision"] for row in before.rows["core_owners"] if row["id"] == "alice")

    def fail_after_native(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = original(*args, **kwargs)
        entities = table_rows(repo, "core_entities")
        assert any(row["id"] == result["id"] and row["data"]["role"] == "assistant" for row in entities)
        users = [row for row in entities if row["owner"] == "alice" and row["data"].get("role") == "user"]
        assert len(users) == 2 and all(row["data"]["thread_id"] == "life:self" for row in users)
        assert len(table_rows(repo, "core_operations")) == len(before.rows["core_operations"]) + 1
        assert (
            next(row["revision"] for row in table_rows(repo, "core_owners") if row["id"] == "alice")
            == owner_revision + 1
        )
        reached.append(result["id"])
        raise marker

    monkeypatch.setattr(component.module, "record_assistant", fail_after_native)
    with pytest.raises(ValueError) as failed:
        verify_backfill_effects(repo, "alice", bindings=component.bindings)
    assert failed.value is marker and len(reached) == 1
    assert state(repo) == before
