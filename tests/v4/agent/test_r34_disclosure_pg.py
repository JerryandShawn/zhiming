"""Synthetic all-true state, real leased model journal, native E2 projection."""

import pytest

from mingjing_core.agent.tool_visibility import VisibilityState
from tools.eval.targets.v4_observations import tool_disclosures

from .test_loop_cycle_support import ScriptedPort, answer, cycle, prepare
from .test_loop_cycle_support import cycle_repo as source_repo_fixture


@pytest.fixture(name="cycle_repo")
def repository_fixture(p2_repo, monkeypatch):
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def test_all_true_disclosure_is_saved_in_real_model_step_for_e2(cycle_repo, monkeypatch):
    repo = cycle_repo
    run, registry, frozen = prepare(repo)
    state = VisibilityState(
        memory_search_has_results=True,
        memory_correcting=True,
        first_meeting=True,
        profile_editing=True,
        tarot_topic=True,
        tarot_pending=True,
        case_bound=True,
        case_progress=True,
        chart_computed=True,
        date_context=True,
        metaphysics_intent="synastry",
        reminder_requested=True,
    )
    monkeypatch.setattr(registry.service, "visibility_state", lambda ctx: state)
    monkeypatch.setattr(registry.service, "chart_available", lambda ctx: True)
    port = ScriptedPort([answer("合成容量核验")])
    result = cycle(port, registry, run, frozen).execute()
    assert result.stop_reason == "completed" and len(port.requests) == 1
    records = tool_disclosures(repo, "alice", run["id"])
    assert len(records) == 1 and records[0]["trimmed_known"] is True
    assert len(records[0]["visible"]) == 15
    assert {"tarot_read", "synastry", "chart_compute", "chart_skill", "memory_update", "date_calc"} <= set(
        records[0]["visible"]
    )
    assert records[0]["trimmed"] == [
        "schedule_followup",
        "tarot_start",
        "case_list",
        "case_update",
        "case_add_event",
        "calendar_lookup",
        "set_reminder",
    ]
    assert repo.fetch_run("alice", run["id"])["status"] == "running"
