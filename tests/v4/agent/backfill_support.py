"""Synthetic committed runs for backfill; PG and the core4 loop remain real."""

from __future__ import annotations

import uuid
from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.agent_finalization import AgentFinalizer
from mingjing_core.application.memory import MemoryService
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.postgres import PostgresRepository

from .test_computation_charts_pg import engine, legacy_profile as profile
from .test_loop_cycle_support import ScriptedPort, answer, cycle, prepare


def remove_reply(repo: PostgresRepository, run: dict) -> None:
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("DELETE FROM {} WHERE owner='alice' AND kind='message' AND data->>'run_id'=%s").format(
                repo.table("core_entities")
            ),
            (run["id"],),
        )


def store_result(repo: PostgresRepository, run: dict, result: dict) -> None:
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET result=%s WHERE owner='alice' AND id=%s").format(repo.table("core_runs")),
            (Jsonb(result), run["id"]),
        )


def food_fact(repo: PostgresRepository, owner: str = "alice") -> dict:
    memory = MemoryService(repo)
    source = memory.receive(owner, content="请记住我不吃辣", source_id=uuid.uuid4().hex)
    return memory.save_fact(owner, "self", source["id"], "我不吃辣", "preference")


def core4(repo: PostgresRepository, *, delivery_target: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    profile(repo)
    fact = food_fact(repo)
    route = {"channel": "feishu", "external_id": delivery_target} if delivery_target else {}
    run, registry, frozen = prepare(repo, "请核对合成现实安排", **route)
    registry.service.charts = engine(repo)
    alias = next(key for key, row in frozen.alias_map.items() if row["kind"] == "fact" and row["id"] == fact["id"])
    port = ScriptedPort(
        [
            answer("", [ToolCall("calc", "chart_compute", {"system": "bazi", "target": "2026-10-17"})]),
            answer(f"结合〔{alias}〕和〔r1〕，先核实现实条件。"),
        ]
    )
    outcome = cycle(port, registry, run, frozen).execute()
    result = AgentFinalizer(repo).finalize(
        run,
        text=outcome.text,
        alias_map=outcome.alias_map,
        versions=outcome.versions,
        snapshot_revision=frozen.snapshot_revision,
        asked=outcome.asked,
        usage=outcome.usage,
    )
    run = repo.fetch_run("alice", run["id"])
    assert result["used_fact_ids"] == [fact["id"]] and len(result["used_claim_ids"]) == 1
    remove_reply(repo, run)
    return run, result


def core3(repo: PostgresRepository, *, temporary: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    memory = MemoryService(repo)
    source = memory.receive("alice", content="我不吃辣", source_id=uuid.uuid4().hex)
    run = repo.begin_run("alice", uuid.uuid4().hex, {"message": source["content"], "source_message_id": source["id"]})
    versions = {"message:" + source["id"]: source["revision"]}
    evidence = []
    if temporary:
        contextual = memory.current_source_context("alice", "self", source["id"], [{"quote": "我不吃辣"}])
        fact = contextual["facts"][0]
        evidence = [{"ref": "source:" + fact["id"], "context_only": True, "source_refs": fact["source_refs"]}]
    else:
        fact = food_fact(repo)
        versions["fact:" + fact["id"]] = fact["revision"]
    claim_id = "synthetic-rule"
    repo.put(
        "alice",
        "interpretive_claim",
        run["id"] + ":e0:" + claim_id,
        {"run_id": run["id"], "claim": {"claim_id": claim_id}},
        expected_revision=0,
    )
    repo.set_run_dependencies("alice", run["id"], versions, run["lease_token"])
    result = {
        "schema_version": "core3.0",
        "validation": {"status": "validated"},
        "answer": "合成历史终稿",
        "cited_fact_ids": [fact["id"]],
        "cited_claim_ids": [claim_id],
        "evidence": evidence,
        "meta": {
            "core_run": {"run_id": run["id"], "operation_id": run["operation_id"]},
            "subject_id": "self",
            "injected_ids": [fact["id"]],
        },
    }
    repo.commit_run("alice", run["id"], versions, result, run["lease_token"])
    return repo.fetch_run("alice", run["id"]), result
