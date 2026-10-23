"""A real persisted ask_user tool step survives the frozen public projection."""

from __future__ import annotations

from typing import Any

import pytest
from jsonschema import Draft202012Validator

from mingjing_core.agent.events import envelope_schema, make_event
from mingjing_core.application.agent_finalization import AgentFinalizer
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.postgres import PostgresRepository

from .test_loop_cycle_support import answer, cycle, prepare
from .test_loop_cycle_support import cycle_repo as source_cycle_repo


@pytest.fixture
def cycle_repo(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Any:
    yield from source_cycle_repo.__wrapped__(p2_repo, monkeypatch)


def test_real_ask_step_commits_public_ids_and_matching_event(cycle_repo: PostgresRepository) -> None:
    from .test_loop_cycle_support import ScriptedPort

    question = dict(
        question="这件事你最在意哪一点？",
        options=["时间", "收入"],
        allow_free_text=True,
        why="影响建议顺序",
        slot="最在意因素",
        changes_conclusion="决定先谈哪个方案",
    )
    run, registry, frozen = prepare(cycle_repo)
    component = cycle(
        ScriptedPort([answer("", [ToolCall("ask-synthetic", "ask_user", question)])]), registry, run, frozen
    )
    result = component.execute()
    final = AgentFinalizer(cycle_repo).finalize(
        run,
        text=result.text,
        alias_map=component.aliases,
        versions=component.versions,
        snapshot_revision=frozen.snapshot_revision,
        asked=result.asked,
        usage=result.usage,
    )
    Draft202012Validator(envelope_schema()).validate(final)
    assert final["asked"]["question"] == question["question"] and final["asked"]["multi"] is False
    assert "changes_conclusion" not in final["asked"] and final["options"] is None
    event = make_event("ask_user", run["id"], 1, final["asked"])
    assert event["data"]["ask_id"] == final["asked"]["ask_id"]
    assert cycle_repo.fetch_run("alice", run["id"])["result"] == final
