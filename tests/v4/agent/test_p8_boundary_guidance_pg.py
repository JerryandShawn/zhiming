"""Native completed chart references reach wording through the actual tool codec."""

import json
from copy import deepcopy

import pytest

from mingjing_core.agent.loop_codec import extend_aliases, tool_message, verified_versions
from mingjing_core.agent.p8_boundary_guidance import boundary_guidance
from mingjing_core.application.memory import MemoryService

from . import test_p8_agent_charts_pg as chart_tests
from .test_p8_agent_charts_pg import registered
from .test_toolkit_pg import SAID_AT


@pytest.fixture(name="repo")
def repository(p2_repo, monkeypatch):
    return chart_tests.repository.__wrapped__(p2_repo, monkeypatch)


@pytest.fixture(autouse=True)
def boundary_birth(monkeypatch):
    def confirmed_profile(repository):
        memory, facts = MemoryService(repository), []
        for field, value in {
            "gender": "男",
            "birth.solar_datetime": "1994-03-12 08:20",
            "birth.timezone_offset": 8,
            "birth.precision": "exact",
            "birth.location.lng": 104.07,
            "birth.location.lat": 30.67,
        }.items():
            text = f"请保存我的{field}为{value}"
            source = memory.receive("alice", content=text, source_id=field, at=SAID_AT)
            facts.append(memory.save_fact("alice", "self", source["id"], text, "profile", field=field, value=value))
        return facts

    monkeypatch.setattr(chart_tests, "profile", confirmed_profile)


def test_completed_native_chart_projects_only_registered_boundary_wording(repo):
    h, args, ctx, step = registered(repo)
    result = h.registry.execute("chart_compute", args, ctx)
    assert result.ok
    before = deepcopy(result.data)
    assert "boundary_guidance" not in json.loads(tool_message("call", result, "cycle").content)["data"]
    h.journal.complete(step, result.model_dump())
    versions, records = verified_versions(h.service, h.run, "chart_compute", result)
    aliases = {}
    extend_aliases(aliases, records)
    output = json.loads(tool_message("call", result, "cycle", aliases=aliases).content)["data"]
    expected = boundary_guidance(result.data, aliases)
    assert expected
    assert output.get("boundary_guidance", []) == expected
    for row in expected:
        assert row["rule_alias"] in aliases
        assert set(row["evidence_aliases"]) <= aliases.keys()
        assert row["profile_update_allowed"] is False and row["state_writes"] == 0
        assert row["affected_pillars"] == row["use_only_if_answer_uses"]
    assert result.data == before and h.repo.verify_versions("alice", versions)
    h.finish()


@pytest.mark.parametrize("mutation", ["missing_rule", "missing_evidence", "wrong_kind", "duplicate"])
def test_native_alert_needs_complete_unambiguous_current_registry(repo, mutation):
    h, args, ctx, step = registered(repo)
    result = h.registry.execute("chart_compute", args, ctx)
    assert result.ok
    h.journal.complete(step, result.model_dump())
    _, records = verified_versions(h.service, h.run, "chart_compute", result)
    aliases = {}
    extend_aliases(aliases, records)
    rules = [key for key in aliases if key.startswith("r")]
    assert rules
    if mutation == "missing_rule":
        aliases = {key: row for key, row in aliases.items() if not key.startswith("r")}
    elif mutation == "missing_evidence":
        aliases = {key: row for key, row in aliases.items() if not key.startswith("c")}
    elif mutation == "wrong_kind":
        for key in rules:
            aliases[key]["kind"] = "artifact"
    else:
        for number, key in enumerate(rules, 100):
            aliases[f"r{number}"] = deepcopy(aliases[key])
    assert boundary_guidance(result.data, aliases) == []
    h.finish()
