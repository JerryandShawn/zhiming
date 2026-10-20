"""Real PG run/source/epoch state drives Z3; model flags cannot disclose tools."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.agent.toolkit import ToolContext
from mingjing_core.domain.contracts import LeaseConflict, ScopeError
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.postgres import PostgresRepository

from .test_loop_cycle_support import (
    ScriptedPort,
    answer,
    cycle,
    modify,
    prepare,
    writer,
)
from .test_loop_cycle_support import cycle_repo as source_cycle_repo
from .test_toolkit_pg import setup


@pytest.fixture(name="cycle_repo")
def repository_fixture(
    p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
) -> Any:
    yield from source_cycle_repo.__wrapped__(p2_repo, monkeypatch)


def model_context(run: dict[str, Any]) -> ToolContext:
    return ToolContext(
        "alice",
        run["id"],
        "self",
        run["retry_epoch"],
        1,
        run["lease_token"],
        "model",
        "a" * 64,
        "life:self",
    )


@pytest.mark.parametrize(
    "text,tarot,correcting,progress",
    [
        ("想聊一下塔罗", True, False, False),
        ("请抽牌看看", True, False, False),
        ("今天先讨论工作", False, False, False),
        ("书上写着“请抽牌”，但我现在只想聊工作", False, False, False),
        ("今天别用塔罗，先聊工作", False, False, False),
        ("我不想再抽牌了", False, False, False),
        ("你记错了，请纠正", False, True, False),
        ("那件事的进展我想说一下", False, False, True),
    ],
)
def test_current_user_source_controls_topic_conditions(
    cycle_repo: PostgresRepository,
    text: str,
    tarot: bool,
    correcting: bool,
    progress: bool,
) -> None:
    h = setup(cycle_repo, text)
    state = h.service.visibility_state(model_context(h.run))
    assert (state.tarot_topic, state.memory_correcting, state.case_progress) == (
        tarot,
        correcting,
        progress,
    )
    assert (
        state.first_meeting
        and not state.memory_search_has_results
        and not state.chart_computed
    )


def test_model_request_flags_do_not_grant_visibility(
    cycle_repo: PostgresRepository,
) -> None:
    h = setup(cycle_repo, "普通合成对话")
    with cycle_repo.transaction("alice") as connection:
        request = dict(
            h.run["request"],
            tarot_topic=True,
            chart_computed=True,
            memory_search_has_results=True,
        )
        connection.execute(
            sql.SQL("UPDATE {} SET request=%s WHERE owner='alice' AND id=%s").format(
                cycle_repo.table("core_runs")
            ),
            (Jsonb(request), h.run["id"]),
        )
    state = h.service.visibility_state(model_context(h.run))
    assert (
        not state.tarot_topic
        and not state.chart_computed
        and not state.memory_search_has_results
    )
    assert "tarot_start" not in {
        tool.name for tool in h.registry.specs(model_context(h.run))
    }


def test_real_search_results_apply_only_to_the_same_run_epoch(
    cycle_repo: PostgresRepository,
) -> None:
    run, registry, frozen = prepare(cycle_repo, "我喜欢合成夜班")
    port = ScriptedPort(
        [
            answer("", [ToolCall("write", "memory_write", writer(run))]),
            answer(
                "",
                [
                    ToolCall(
                        "search", "memory_search", {"query": "合成", "kinds": ["fact"]}
                    )
                ],
            ),
            answer("合成结束"),
        ]
    )
    result = cycle(port, registry, run, frozen).execute()
    assert result.stop_reason == "completed"
    ctx = model_context(run)
    assert registry.service.visibility_state(ctx).memory_search_has_results
    modify(cycle_repo, run, "retry_epoch=retry_epoch+1")
    with pytest.raises(LeaseConflict):
        registry.service.visibility_state(ctx)
    assert not registry.service.visibility_state(
        replace(ctx, epoch=ctx.epoch + 1)
    ).memory_search_has_results


def test_wrong_subject_cannot_read_disclosure_state(
    cycle_repo: PostgresRepository,
) -> None:
    h = setup(cycle_repo, "合成话题")
    with pytest.raises(ScopeError):
        h.service.visibility_state(replace(model_context(h.run), subject="other"))


def test_second_user_turn_is_not_first_meeting(cycle_repo: PostgresRepository) -> None:
    setup(cycle_repo, "第一次合成对话")
    h = setup(cycle_repo, "第二次合成对话")
    assert not h.service.visibility_state(model_context(h.run)).first_meeting


@pytest.mark.parametrize("text", ["请更正一下出生资料", "我的出生时间改成八点"])
def test_profile_change_is_detected_from_current_user(
    cycle_repo: PostgresRepository, text: str
) -> None:
    h = setup(cycle_repo, text)
    assert h.service.visibility_state(model_context(h.run)).profile_editing


def test_model_cannot_execute_an_unexposed_tarot_write(
    cycle_repo: PostgresRepository,
) -> None:
    run, registry, frozen = prepare(cycle_repo, "普通合成对话")
    port = ScriptedPort(
        [
            answer(
                "",
                [
                    ToolCall(
                        "unexposed",
                        "tarot_start",
                        {
                            "question": run["request"]["message"],
                            "message_id": run["request"]["source_message_id"],
                        },
                    )
                ],
            ),
            answer("继续普通对话"),
        ]
    )
    component = cycle(port, registry, run, frozen)
    assert component.execute().stop_reason == "completed"
    assert "tarot_start" not in {spec.name for spec in port.requests[0]["tools"]}
    message = next(message for message in component.messages if message.role == "tool")
    assert json.loads(message.content)["data"]["code"] == "tool_unavailable"
    assert not cycle_repo.list("alice", "case")
    with cycle_repo.transaction("alice") as connection:
        count = connection.execute(
            sql.SQL("SELECT count(*) FROM {} WHERE owner='alice'").format(
                cycle_repo.table("tarot_draws")
            )
        ).fetchone()["count"]
    assert count == 0
