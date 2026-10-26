"""Actual registered Agent execution, native Charts worker and completed-step aliases."""

import json

import pytest

from mingjing_core.agent.loop_codec import extend_aliases, verified_versions
from mingjing_core.application.agent_tools_contracts import ToolContext
from mingjing_core.application.charts_service import ChartsService
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import CoreError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.skills.loader import SkillLibrary

from .test_computation_charts_pg import profile
from .test_toolkit_pg import SAID_AT, setup
from .test_toolkit_pg import tool_repo as source_fixture


@pytest.fixture(name="repo")
def repository(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> PostgresRepository:
    return source_fixture.__wrapped__(p2_repo, monkeypatch)


def registered(repo, system="bazi", metadata=True, effect=None):
    facts = profile(repo)
    if metadata:
        memory = MemoryService(repo)
        for field, value in (("birth.location.tz", "Asia/Shanghai"), ("birth.clock_basis", "clock")):
            text = f"请保存我的{field}为{value}"
            source = memory.receive("alice", content=text, source_id=field, at=SAID_AT)
            memory.save_fact("alice", "self", source["id"], text, "profile", field=field, value=value)
    h = setup(repo, "核对合成出生资料的盘面")
    args = {"system": system, "target": "2026-10-17", "scale": "natal"}
    step = h.journal.next_or_replay(
        h.run, kind="tool", name="chart_compute", input_fp=h.registry.fingerprint("chart_compute", args)
    )
    ctx = ToolContext.from_step(step, thread_id="life:self", source_ids=(h.source["id"],))
    if effect is not None:

        class ChangedAfterCalculation(ChartsService):
            def evaluate_time_basis(self, *arguments, **kwargs):
                value = super().evaluate_time_basis(*arguments, **kwargs)
                effect(h, facts)
                return value

        h.service.charts = ChangedAfterCalculation()
    return h, args, ctx, step


@pytest.mark.parametrize("system", ["bazi", "ziwei"])
def test_registered_precise_chart_has_actual_p8_cache_completed_proof_and_skill(repo, system):
    h, args, ctx, step = registered(repo, system)
    result = h.registry.execute("chart_compute", args, ctx)
    assert result.ok and result.data["adapter_mode"] == "p8_v1_1"
    assert "true_solar_time_basis" not in result.data["unsupported_capabilities"]
    assert "boundary_alerts" not in result.data["unsupported_capabilities"]
    assert result.data["calculation"]["model_calls"] == result.data["calculation"]["writes"] == 0
    assert len(result.data["reference_views"]) <= 10
    assert result.data["persisted"]["documents"]
    with pytest.raises(CoreError):
        verified_versions(h.service, h.run, "chart_compute", result)
    h.journal.complete(step, result.model_dump())
    versions, records = verified_versions(h.service, h.run, "chart_compute", result)
    aliases = {}
    extend_aliases(aliases, records)
    assert 0 < len([key for key in aliases if key.startswith(("c", "r"))]) <= 10
    assert "c1" in aliases and repo.verify_versions("alice", versions)
    if system == "bazi":
        assert "r1" in aliases

    class NoRecalculation(ChartsService):
        def evaluate_time_basis(self, *arguments, **kwargs):
            pytest.fail("An original completed step must replay its native cache")

    h.service.charts = NoRecalculation()
    assert h.registry.execute("chart_compute", args, ctx) == result
    topic = SkillLibrary().catalog["systems"][system]["chapters"][0]["topic"]
    skill, _ = h.call("chart_skill", {"system": system, "topic": topic})
    assert skill.ok and skill.data["context_utf8_bytes"] <= 5500
    h.finish()


def test_second_actual_calculation_cannot_get_ten_more_references_in_same_run(repo):
    h, args, ctx, step = registered(repo)
    first = h.registry.execute("chart_compute", args, ctx)
    assert first.ok
    h.journal.complete(step, first.model_dump())
    first_versions, first_records = verified_versions(h.service, h.run, "chart_compute", first)
    assert repo.verify_versions("alice", first_versions)
    second_args = {"system": "ziwei", "target": "2026-10-18"}
    second_step = h.journal.next_or_replay(
        h.run, kind="tool", name="chart_compute", input_fp=h.registry.fingerprint("chart_compute", second_args)
    )
    second_ctx = ToolContext.from_step(second_step, thread_id="life:self", source_ids=(h.source["id"],))
    second = h.registry.execute("chart_compute", second_args, second_ctx)
    h.journal.complete(second_step, second.model_dump())
    assert second.ok and second.data["adapter_mode"] == "p8_v1_1"
    assert len(first.data["reference_views"]) + len(second.data["reference_views"]) <= 10
    versions, records = verified_versions(h.service, h.run, "chart_compute", second)
    aliases = {}
    extend_aliases(aliases, first_records + records)
    assert len([key for key in aliases if key.startswith(("c", "r"))]) <= 10
    assert repo.verify_versions("alice", versions)
    h.finish()


def test_precise_profile_without_iana_does_not_silently_return_old_basis(repo):
    h, args, ctx, step = registered(repo, metadata=False)
    result = h.registry.execute("chart_compute", args, ctx)
    assert not result.ok and result.data["code"] == "MISSING_INPUT"
    assert repo.list("alice", "artifact") == repo.list("alice", "interpretive_claim") == []
    h.finish()


@pytest.mark.parametrize("mode", ["withdrawn_document", "withdrawn_reference", "forged_output", "changed_profile"])
def test_actual_p8_lineage_refuses_withdrawal_or_forged_output(repo, mode):
    h, args, ctx, step = registered(repo)
    result = h.registry.execute("chart_compute", args, ctx)
    assert result.ok
    h.journal.complete(step, result.model_dump())
    changed = result.model_copy(deep=True)
    if mode.startswith("withdrawn"):
        row = result.data["persisted"]["documents" if mode == "withdrawn_document" else "artifacts"][0]
        repo.delete("alice", "artifact", row["id"], expected_revision=row["revision"])
    elif mode == "forged_output":
        changed.data["reference_views"][0]["pointer"] = "/fake"
    else:
        fact = repo.list("alice", "fact")[0]
        repo.update("alice", "fact", fact["id"], {"value": "changed"}, expected_revision=fact["revision"])
    with pytest.raises(CoreError):
        verified_versions(h.service, h.run, "chart_compute", changed)
    h.finish()


@pytest.mark.parametrize("mode", ["cancelled", "profile_changed"])
def test_p8_actual_worker_finishing_after_authority_change_does_not_persist(repo, mode):
    def effect(h, facts):
        if mode == "cancelled":
            repo.fail_run("alice", h.run["id"], "synthetic-cancel", h.run["lease_token"], status="cancelled")
        else:
            fact = facts[0]
            repo.update("alice", "fact", fact["id"], {"value": "女"}, expected_revision=fact["revision"])

    h, args, ctx, step = registered(repo, effect=effect)
    result = h.registry.execute("chart_compute", args, ctx)
    assert not result.ok
    assert repo.list("alice", "artifact") == repo.list("alice", "interpretive_claim") == []
    if mode != "cancelled":
        h.finish()


def test_scripted_agent_uses_actual_p8_tool_message_and_commits_native_claim(repo):
    from mingjing_core.application.agent_finalization import AgentFinalizer
    from mingjing_core.models.port import ToolCall
    from .test_loop_cycle_support import ScriptedPort, answer, cycle, prepare

    h, _, _, _ = registered(repo)
    h.finish()
    run, registry, frozen = prepare(repo, "查看合成八字，保留口径限制")
    port = ScriptedPort(
        [
            answer("", [ToolCall("p8-call", "chart_compute", {"system": "bazi", "target": "2026-10-17"})]),
            answer("本次盘面〔c1〕与传统规则〔r1〕仅供参考，不作为现实结果的保证。"),
        ]
    )
    outcome = cycle(port, registry, run, frozen).execute()
    assert outcome.stop_reason == "completed"
    message = next(message for message in port.requests[-1]["messages"] if message.role == "tool")
    projection = json.loads(message.content)["data"]
    assert projection["adapter_mode"] == "p8_v1_1" and projection["chart_summaries"]
    assert "documents" not in projection and "persisted" not in projection and "calculation" not in projection
    assert "r1" in projection["registered_aliases"] and len(projection["registered_aliases"]) <= 10
    envelope = AgentFinalizer(repo).finalize(
        run,
        text=outcome.text,
        alias_map=outcome.alias_map,
        versions=outcome.versions,
        snapshot_revision=frozen.snapshot_revision,
        usage=outcome.usage,
    )
    assert envelope["schema"] == "core4.0"
    assert envelope["used_claim_ids"] == [outcome.alias_map["r1"]["id"]]
