"""Opaque provider IDs stay private while frozen events retain stable paired IDs."""

from __future__ import annotations

import json
from typing import Any

import pytest
from psycopg import sql

from mingjing_core.agent.events import validate_event
from mingjing_core.application.agent_runtime_events import RuntimeEvents
from mingjing_core.application.public_tool_ids import OPAQUE_PREFIX, public_call_id
from mingjing_core.repositories.postgres import PostgresRepository

from .test_dispatcher_pg import queued


def emit_pair(repo: PostgresRepository, run: dict[str, Any], raw: str) -> list[dict]:
    observed: list[dict] = []
    events = RuntimeEvents(repo, run, observed.append)
    common = {"call_id": raw, "name": "time_context", "summary": "合成公开状态"}
    events.send("tool_call", common)
    events.send("tool_result", dict(common, ok=True))
    assert common["call_id"] == raw
    return observed


@pytest.mark.parametrize("raw", ["provider/call/A", "合成原始标识", "opaque-" + "x" * 250, "p3opaque:looks-valid"])
def test_opaque_ids_reconnect_and_pair_without_escaping_frozen_schema(p2_repo: PostgresRepository, raw: str) -> None:
    run = p2_repo.claim_run("alice", queued(p2_repo)["id"])
    observed = emit_pair(p2_repo, run, raw) + emit_pair(p2_repo, run, raw)
    mapped = public_call_id(run, raw)
    assert mapped.startswith(OPAQUE_PREFIX) and mapped != raw
    assert all(row["data"]["call_id"] == mapped for row in observed)
    for row in observed:
        validate_event(row["type"], row["data"])
    assert raw not in json.dumps(observed, ensure_ascii=False)


def test_legal_raw_id_cannot_impersonate_reserved_hash_output(p2_repo: PostgresRepository) -> None:
    run = p2_repo.claim_run("alice", queued(p2_repo)["id"])
    mapped = public_call_id(run, "opaque/private-first")
    first = emit_pair(p2_repo, run, "opaque/private-first")
    pretender = emit_pair(p2_repo, run, mapped)
    other = emit_pair(p2_repo, run, "opaque/private-second")
    assert first[0]["data"]["call_id"] == mapped
    assert len({first[0]["data"]["call_id"], pretender[0]["data"]["call_id"], other[0]["data"]["call_id"]}) == 3


@pytest.mark.parametrize("raw", ["valid-id_1:A.2", "simple"])
def test_existing_public_id_stays_unchanged(p2_repo: PostgresRepository, raw: str) -> None:
    run = p2_repo.claim_run("alice", queued(p2_repo)["id"])
    assert all(row["data"]["call_id"] == raw for row in emit_pair(p2_repo, run, raw))


def test_public_mapping_is_stable_within_epoch_and_separate_between_epochs(p2_repo: PostgresRepository) -> None:
    repo = p2_repo
    run = repo.claim_run("alice", queued(repo)["id"])
    before = emit_pair(repo, run, "opaque/private")
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET retry_epoch=retry_epoch+1 WHERE id=%s").format(repo.table("core_runs")), (run["id"],)
        )
    fresh = repo.fetch_run("alice", run["id"])
    after = emit_pair(repo, fresh, "opaque/private")
    assert before[0]["data"]["call_id"] != after[0]["data"]["call_id"]
    assert before[0]["data"]["call_id"] == before[1]["data"]["call_id"]
    assert after[0]["data"]["call_id"] == after[1]["data"]["call_id"]
