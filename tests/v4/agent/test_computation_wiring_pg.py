"""Registered computation and c/r aliases traverse actual PG authority and journal."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from typing import Any

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.agent.loop_codec import extend_aliases, tool_message, verified_versions
from mingjing_core.agent.tools.computation_parameters import DateCalc
from mingjing_core.application.agent_tools_contracts import ToolContext, ToolResult, tool_input_fingerprint
from mingjing_core.domain.contracts import CoreError
from mingjing_core.repositories.dependencies import entity_dependency
from mingjing_core.repositories.postgres import PostgresRepository

from .test_computation_charts_pg import engine, profile
from .test_computation_updates_pg import prior
from .test_toolkit_pg import Harness, setup
from .test_toolkit_pg import tool_repo as source_fixture


@pytest.fixture(name="tool_repo")
def repository(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> PostgresRepository:
    return source_fixture.__wrapped__(p2_repo, monkeypatch)


def registered(h: Harness) -> tuple[Any, Any]:
    args = {"system": "bazi", "target": "2026-10-17"}
    step = h.journal.next_or_replay(
        h.run, kind="tool", name="chart_compute", input_fp=h.registry.fingerprint("chart_compute", args)
    )
    ctx = ToolContext.from_step(step, thread_id="life:self", source_ids=(h.source["id"],))
    h.service.charts = engine(h.repo)
    result = h.registry.execute("chart_compute", args, ctx)
    assert result.ok
    return step, result


def test_registered_chart_gets_c_r_only_after_real_completed_step(tool_repo: PostgresRepository) -> None:
    profile(tool_repo)
    h = setup(tool_repo, "看看合成八字")
    step, result = registered(h)
    with pytest.raises(CoreError):
        verified_versions(h.service, h.run, "chart_compute", result)
    h.journal.complete(step, result.model_dump())
    versions, records = verified_versions(h.service, h.run, "chart_compute", result)
    aliases: dict[str, dict[str, Any]] = {}
    extend_aliases(aliases, records)
    assert "c1" in aliases and "r1" in aliases
    assert aliases["c1"]["kind"] == "artifact" and aliases["r1"]["kind"] == "interpretive_claim"
    assert aliases["r1"]["run_id"] == h.run["id"] and aliases["r1"]["epoch"] == 0
    assert all(entity_dependency(row["kind"], row["id"]) in versions for row in records)
    assert all(key in versions for key in ("owner:alice", "subject:self"))
    original = copy.deepcopy(result.model_dump())
    message = json.loads(tool_message("call", result, "cycle", aliases=aliases).content)
    assert message["data"]["registered_aliases"]["c1"]["id"] == aliases["c1"]["id"]
    assert "source_refs" not in str(message["data"]["registered_aliases"])
    assert result.model_dump() == original
    assert "registered_aliases" not in json.loads(tool_message("old", result, "cycle", aliases={}).content)["data"]
    fake_search = ToolResult(
        ok=True, data={"items": [{"entity_kind": "artifact", "id": aliases["c1"]["id"]}]}, summary="伪造搜索"
    )
    with pytest.raises(CoreError):
        verified_versions(h.service, h.run, "memory_search", fake_search)


@pytest.mark.parametrize("forgery", ["text", "entity", "other_run", "epoch", "stored_content"])
def test_model_or_stale_output_cannot_forge_c_r(tool_repo: PostgresRepository, forgery: str) -> None:
    profile(tool_repo)
    h = setup(tool_repo, "看看合成八字")
    step, result = registered(h)
    h.journal.complete(step, result.model_dump())
    changed, run = result.model_copy(deep=True), h.run
    if forgery == "text":
        changed.data["claims"][0]["text"] = "伪造的未来保证"
    elif forgery == "entity":
        changed.data["persisted"]["artifacts"][0]["id"] = "forged-artifact"
    elif forgery == "other_run":
        h.finish()
        run = setup(tool_repo, "另一个合成问题").run
    elif forgery == "epoch":
        run = dict(run, retry_epoch=1)
    else:
        ident = result.data["persisted"]["artifacts"][0]["id"]
        with tool_repo.transaction("alice") as connection:
            connection.execute(
                sql.SQL(
                    "UPDATE {} SET data=jsonb_set(data,'{{artifact,data,fake}}',%s,true) "
                    "WHERE owner='alice' AND kind='artifact' AND id=%s"
                ).format(tool_repo.table("core_entities")),
                (Jsonb(True), ident),
            )
    with pytest.raises(CoreError):
        verified_versions(h.service, run, "chart_compute", changed)


def test_chart_not_disclosed_without_confirmed_profile_or_in_private_mode(
    tool_repo: PostgresRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = setup(tool_repo, "看看合成八字")
    ctx = ToolContext("alice", h.run["id"], "self", 0, 1, h.run["lease_token"], "model", "a" * 64, "life:self")
    assert "chart_compute" not in {item.name for item in h.registry.specs(ctx)}
    profile(tool_repo)
    assert "chart_compute" in {item.name for item in h.registry.specs(ctx)}
    monkeypatch.setattr(h.service.memory, "facts", lambda *args, **kwargs: pytest.fail("无痕不可读档案"))
    assert "chart_compute" not in {item.name for item in h.registry.specs(replace(ctx, incognito=True))}
    assert "date_calc" not in {item.name for item in h.registry.specs(replace(ctx, incognito=True))}


def test_date_calc_is_a_registered_read_without_write_receipt(tool_repo: PostgresRepository) -> None:
    h = setup(tool_repo, "计算日期差")
    args = DateCalc(operation="add_days", start_date="2026-10-17", days=4).model_dump()
    step = h.journal.next_or_replay(
        h.run, kind="tool", name="date_calc", input_fp=tool_input_fingerprint("date_calc", args)
    )
    ctx = ToolContext.from_step(step, thread_id="life:self", source_ids=(h.source["id"],))
    result = h.registry.execute("date_calc", args, ctx)
    assert result.ok and result.data["end_date"] == "2026-10-21"
    assert result.receipt is None and result.summary == "算了一下日期"
    assert "date_calc" in {item.name for item in h.registry.specs(ctx)}


def test_registered_memory_update_and_profile_request_use_real_mutation_receipts(tool_repo: PostgresRepository) -> None:
    fact = prior(tool_repo)
    h = setup(tool_repo, "更正：我现在喜欢夜间阅读")
    result, _ = h.call(
        "memory_update",
        {
            "fact_id": fact["id"],
            "expected_revision": fact["revision"],
            "message_id": h.source["id"],
            "quote": h.source["content"],
            "summary": "合成更正",
        },
    )
    assert result.ok and tool_repo.get("alice", "fact", result.receipt["id"])["content"] == h.source["content"]
    h.finish()
    requested = setup(tool_repo, "更正出生资料")
    result, _ = requested.call(
        "profile_update_request",
        {
            "fields": ["birth.solar_datetime"],
            "message_id": requested.source["id"],
            "quote": requested.source["content"],
        },
    )
    assert result.receipt["write_status"] == "pending_confirmation"
    assert tool_repo.get("alice", "proposal", result.receipt["id"])["kind"] == "profile_update_request"


def test_scripted_loop_reads_registered_c_r_from_actual_tool_message(tool_repo: PostgresRepository) -> None:
    from mingjing_core.models.port import ToolCall

    from .test_loop_cycle_support import ScriptedPort, answer, cycle, prepare

    profile(tool_repo)
    run, registry, frozen = prepare(tool_repo, "看看合成八字")
    registry.service.charts = engine(tool_repo)
    call = ToolCall("chart-call", "chart_compute", {"system": "bazi", "target": "2026-10-17"})
    port = ScriptedPort([answer("", [call]), answer("按本轮计算〔c1〕与规则〔r1〕提供反思。")])
    outcome = cycle(port, registry, run, frozen).execute()
    assert outcome.stop_reason == "completed" and outcome.alias_map["c1"]["kind"] == "artifact"
    assert outcome.alias_map["r1"]["kind"] == "interpretive_claim"
    messages = port.requests[-1]["messages"]
    tool = next(message for message in messages if message.role == "tool")
    aliases = json.loads(tool.content)["data"]["registered_aliases"]
    assert aliases["c1"]["id"] == outcome.alias_map["c1"]["id"]
    assert aliases["r1"]["id"] == outcome.alias_map["r1"]["id"]
    from mingjing_core.application.agent_finalization import AgentFinalizer

    envelope = AgentFinalizer(tool_repo).finalize(
        run,
        text=outcome.text,
        alias_map=outcome.alias_map,
        versions=outcome.versions,
        snapshot_revision=frozen.snapshot_revision,
        usage=outcome.usage,
    )
    assert envelope["schema"] == "core4.0" and envelope["used_claim_ids"] == [outcome.alias_map["r1"]["id"]]
