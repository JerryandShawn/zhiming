"""Native completed-chart proof precedes local skill loading; no new aliases."""

from copy import deepcopy
from dataclasses import replace

import pytest
from pydantic import ValidationError

from mingjing_core.agent.toolkit import DEFINITIONS
from mingjing_core.agent.tools.computation_parameters import ChartSkill
from mingjing_core.application.agent_tools_chart_skill import execute_chart_skill
from mingjing_core.application.agent_tools_contracts import ToolContext
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.skills.loader import SkillLibrary

from .test_computation_charts_pg import engine, legacy_profile as profile
from .test_toolkit_pg import setup
from .test_toolkit_pg import tool_repo as source_fixture


@pytest.fixture(name="repo")
def repository(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> PostgresRepository:
    return source_fixture.__wrapped__(p2_repo, monkeypatch)


def chart(h, *, complete: bool = True):
    args = {"system": "bazi", "target": "2026-10-17", "scale": "natal"}
    step = h.journal.next_or_replay(
        h.run, kind="tool", name="chart_compute", input_fp=h.registry.fingerprint("chart_compute", args)
    )
    ctx = ToolContext.from_step(step, thread_id="life:self", source_ids=(h.source["id"],))
    result = h.registry.execute("chart_compute", args, ctx)
    assert result.ok
    if complete:
        h.journal.complete(step, result.model_dump())
    return result


def test_skill_is_registered_but_hidden_until_current_completed_chart(repo: PostgresRepository) -> None:
    profile(repo)
    h = setup(repo, "请解释合成八字")
    h.service.charts = engine(repo)
    result, _ = h.call("chart_skill", {"system": "bazi", "topic": "basics"})
    assert not result.ok and result.data["code"] == "tool_unavailable"
    native = chart(h)
    counts = {kind: len(repo.list("alice", kind)) for kind in ("artifact", "interpretive_claim", "fact", "note")}
    result, ctx = h.call("chart_skill", {"system": "bazi", "topic": "basics"})
    assert result.ok and result.receipt is None
    assert result.data == SkillLibrary().load("bazi", "basics")
    assert result.data["context"].startswith('<技能 system="bazi"')
    assert result.data["context_utf8_bytes"] <= 5500
    assert "registered_aliases" not in result.data
    assert counts == {kind: len(repo.list("alice", kind)) for kind in counts}
    assert native.data["adapter_mode"] == "legacy_v3"
    assert execute_chart_skill(h.service, {"system": "bazi", "topic": "basics"}, ctx) == result
    h.finish()


@pytest.mark.parametrize("mode", ["uncompleted", "withdrawn", "profile_changed", "forged_cache"])
def test_skill_refuses_invalid_current_calculation(repo: PostgresRepository, mode: str) -> None:
    facts = profile(repo)
    h = setup(repo, "请解释合成盘面")
    h.service.charts = engine(repo)
    result = chart(h, complete=mode != "uncompleted")
    if mode == "withdrawn":
        record = result.data["persisted"]["artifacts"][0]
        repo.delete("alice", "artifact", record["id"], expected_revision=record["revision"])
    elif mode == "profile_changed":
        fact = facts[0]
        repo.update("alice", "fact", fact["id"], {"value": "女"}, expected_revision=fact["revision"])
    elif mode == "forged_cache":
        row = next(row for row in repo.list("alice", "runtime_step") if row["id"].startswith("agent_chart_cache_"))
        changed = deepcopy(row["tool_output"])
        changed["data"]["adapter_mode"] = "made-up"
        repo.update("alice", "runtime_step", row["id"], {"tool_output": changed}, expected_revision=row["revision"])
    result, _ = h.call("chart_skill", {"system": "bazi", "topic": "basics"})
    assert not result.ok
    h.finish()


def test_skill_cannot_bypass_crisis_or_step_fingerprint(repo: PostgresRepository) -> None:
    profile(repo)
    h = setup(repo, "核对解释口径")
    h.service.charts = engine(repo)
    chart(h)
    _, ctx = h.call("chart_skill", {"system": "bazi", "topic": "basics"})
    with pytest.raises(EvidenceError):
        execute_chart_skill(h.service, {"system": "bazi", "topic": "basics"}, replace(ctx, input_fp="b" * 64))
    result = h.registry.execute("chart_skill", {"system": "bazi", "topic": "basics"}, replace(ctx, crisis=True))
    assert not result.ok and result.data["code"] == "tool_unavailable"
    h.finish()


def test_skill_schema_and_all_pairs_come_from_actual_catalog() -> None:
    library = SkillLibrary()
    schema = ChartSkill.model_json_schema()
    assert set(schema["properties"]["system"]["enum"]) == set(library.catalog["systems"])
    for system, package in library.catalog["systems"].items():
        allowed = {row["topic"] for row in package["chapters"]}
        for chapter in package["chapters"]:
            args = ChartSkill.model_validate({"system": system, "topic": chapter["topic"]})
            assert args.topic in schema["properties"]["topic"]["enum"]
        for topic in set(schema["properties"]["topic"]["enum"]) - allowed:
            with pytest.raises(ValidationError):
                ChartSkill.model_validate({"system": system, "topic": topic})
    for args in (
        {"system": "../bazi", "topic": "basics"},
        {"system": "astro", "topic": "hidden-command"},
        {"system": "bazi", "topic": "basics", "birth": {}},
        {"system": "bazi", "topic": "basics", "consent": True},
    ):
        with pytest.raises(ValidationError):
            ChartSkill.model_validate(args)
    definition = next(item for item in DEFINITIONS if item.name == "chart_skill")
    assert definition.read_only and definition.private_allowed
