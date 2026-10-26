"""Native registered P8 date tools, actual isolated Charts and strict scope."""

from dataclasses import replace
import json

import pytest
from pydantic import ValidationError

from mingjing_core.agent.loop_codec import extend_aliases, tool_message, verified_versions
from mingjing_core.agent.tools.p8_parameters import Almanac, DailyTransit, WindowSearch
from mingjing_core.application.agent_tools_contracts import ToolContext
from mingjing_core.domain.contracts import CoreError

from .test_p8_agent_charts_pg import registered, repository  # noqa: F401
from .test_toolkit_pg import setup

CASES = [
    ("almanac", "请看2026-10-27黄历宜忌", {"date": "2026-10-27"}),
    ("daily_transit", "2026-10-27运势如何", {"date": "2026-10-27"}),
    (
        "window_search",
        "择日安排面试",
        {"start_date": "2026-10-27", "end_date": "2026-10-27", "purpose": "面试", "limit": 1},
    ),
]


def begin(repo, name, text, args, *, birth=True):
    if birth:
        old, _, _, _ = registered(repo)
        old.finish()
    h = setup(repo, text)
    step = h.journal.next_or_replay(h.run, kind="tool", name=name, input_fp=h.registry.fingerprint(name, args))
    ctx = ToolContext.from_step(step, thread_id="life:self", source_ids=(h.source["id"],))
    return h, step, ctx


@pytest.mark.parametrize("name,text,args", CASES)
def test_actual_registered_date_tool_document_completed_lineage_and_replay(repo, name, text, args):
    h, step, ctx = begin(repo, name, text, args)
    before = len(repo.list("alice", "fact"))
    result = h.registry.execute(name, args, ctx)
    assert result.ok and result.data["adapter_mode"] == "p8_v1_1"
    assert result.data["documents"][0]["kind"] == name
    assert len(result.data["reference_views"]) <= 10
    assert len(repo.list("alice", "fact")) == before
    with pytest.raises(CoreError):
        verified_versions(h.service, h.run, name, result)
    h.journal.complete(step, result.model_dump())
    versions, records = verified_versions(h.service, h.run, name, result)
    aliases = {}
    extend_aliases(aliases, records)
    assert repo.verify_versions("alice", versions)
    assert len([key for key in aliases if key.startswith(("c", "r"))]) <= 10
    assert "documents" not in tool_message("date-tool", result, "cycle", aliases=aliases).content
    assert h.registry.execute(name, args, ctx) == result
    withdrawn = result.model_copy(deep=True)
    withdrawn.data["arguments"][next(iter(args))] = "forged"
    with pytest.raises(CoreError):
        verified_versions(h.service, h.run, name, withdrawn)
    h.finish()


def test_almanac_requires_no_birth_profile_or_profile_fact_reads(repo, monkeypatch):
    name, text, args = CASES[0]
    h, step, ctx = begin(repo, name, text, args, birth=False)
    assert repo.list("alice", "fact") == []
    monkeypatch.setattr(h.service, "chart_available", lambda ctx: False)
    monkeypatch.setattr(
        h.service.memory, "facts", lambda *a, **k: pytest.fail("Public almanac must not read birth facts")
    )
    result = h.registry.execute(name, args, ctx)
    assert result.ok and result.data["calculation"]["scope"] is None
    assert result.data["documents"][0]["scope"]["owner_user_id"] == "alice"
    assert repo.list("alice", "fact") == []
    h.finish()


@pytest.mark.parametrize("mode", ["unrelated", "quoted", "negated", "private", "crisis"])
def test_new_tools_cannot_be_forced_without_native_intent_or_in_private_mode(repo, mode):
    text = {
        "unrelated": "聊聊生活",
        "quoted": "引用‘2026-10-27运势如何’",
        "negated": "不要查运势",
        "private": "2026-10-27运势如何",
        "crisis": "2026-10-27运势如何",
    }[mode]
    name, _, args = CASES[1]
    h, step, ctx = begin(repo, name, text, args)
    if mode == "private":
        ctx = replace(ctx, incognito=True)
    elif mode == "crisis":
        ctx = replace(ctx, crisis=True)
    result = h.registry.execute(name, args, ctx)
    assert not result.ok and result.data["code"] == "tool_unavailable"
    assert repo.list("alice", "artifact") == []
    h.finish()


@pytest.mark.parametrize(
    "model,args",
    [
        (DailyTransit, {"date": "明天"}),
        (Almanac, {"date": "2026-10-27", "birth": {}}),
        (WindowSearch, {"start_date": "2026-10-27", "end_date": "2026-10-26", "purpose": "面试"}),
        (WindowSearch, {"start_date": "2026-01-01", "end_date": "2027-01-02", "purpose": "签约"}),
        (WindowSearch, {"start_date": "2026-10-27", "end_date": "2026-10-27", "purpose": "保证中奖"}),
        (WindowSearch, {"start_date": "2026-10-27", "end_date": "2026-10-27", "purpose": "面试", "limit": True}),
    ],
)
def test_date_tool_schema_never_accepts_birth_consent_or_unbounded_search(model, args):
    with pytest.raises(ValidationError):
        model.model_validate(args)


def test_scripted_agent_almanac_projection_and_final_envelope_use_actual_tool(repo):
    from mingjing_core.application.agent_finalization import AgentFinalizer
    from mingjing_core.models.port import ToolCall
    from .test_loop_cycle_support import ScriptedPort, answer, cycle, prepare

    run, registry, frozen = prepare(repo, "请看2026-10-27黄历宜忌")
    port = ScriptedPort(
        [
            answer("", [ToolCall("public-almanac", "almanac", {"date": "2026-10-27"})]),
            answer("本次查询是通用黄历，并非个人预测；请优先核对现实日程。"),
        ]
    )
    outcome = cycle(port, registry, run, frozen).execute()
    assert outcome.stop_reason == "completed"
    message = next(item for item in port.requests[-1]["messages"] if item.role == "tool")
    data = json.loads(message.content)["data"]
    assert data["tool_name"] == "almanac" and data["tool_data"] and data["limits"]
    assert "documents" not in data and "persisted" not in data
    envelope = AgentFinalizer(repo).finalize(
        run,
        text=outcome.text,
        alias_map=outcome.alias_map,
        versions=outcome.versions,
        snapshot_revision=frozen.snapshot_revision,
        usage=outcome.usage,
    )
    assert envelope["schema"] == "core4.0" and repo.list("alice", "fact") == []
