"""Eight independent public compose scenarios frozen before the current-manifest gate was exercised."""

import socket
from copy import deepcopy
from dataclasses import replace
from typing import Any

import pytest
from manifest_calendar_support_mod import digest, fictional_text, host_values, notice, raw_transit

from mingjing_core.application.briefing_v2 import BriefingError, BriefingResult, BriefSourceState, compose_briefing


@pytest.fixture(autouse=True)
def offline_manifest_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("独立晨报清单验收禁止网络")

    for key in ("KIMI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LANGSMITH_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    for name in ("socket", "create_connection", "getaddrinfo"):
        monkeypatch.setattr(socket, name, forbidden)


def visible(result: BriefingResult) -> str:
    return "\n".join(line.text for section in result.sections for line in section.lines)


def assert_zero_effects(result: BriefingResult) -> None:
    assert result.effects.model_calls == result.effects.writes == result.effects.notifications == 0
    assert result.effects.scheduler_mutations == 0


def assert_current_conflict(values: dict[str, Any]) -> None:
    with pytest.raises(BriefingError) as caught:
        compose_briefing(**values)
    assert caught.value.reason_code == "brief_current_source_manifest_inconsistent"
    for item in values["items"]:
        assert item.request.candidate.text not in str(caught.value)


def test_bm01_revoked_item_cannot_contradict_the_current_subscription() -> None:
    values = host_values()
    entry = notice(replace(values["subscription_state"], revoked=True), 1)
    assert_current_conflict(dict(values, items=(entry,)))


def test_bm02_bound_revoked_p8_cannot_be_filtered_before_its_active_item_conflict() -> None:
    values = host_values(raw_transit())
    entry = notice(values["transit_state"], 1)
    values["transit_state"] = replace(values["transit_state"], revoked=True)
    assert_current_conflict(dict(values, items=(entry,)))


def test_bm03_identical_subscription_and_p8_states_are_not_false_conflicts() -> None:
    raw = raw_transit()
    before = deepcopy(raw)
    values = host_values(raw)
    entries = (notice(values["subscription_state"], 1), notice(values["transit_state"], 2))
    result = compose_briefing(**dict(values, items=entries))
    assert {"calendar", "transit", "area_career"} <= {section.id for section in result.sections}
    assert all(entry.request.candidate.text in visible(result) for entry in entries)
    assert not result.omissions and raw == before
    assert_zero_effects(result)


def test_bm04_invalid_p8_does_not_authorize_a_conflicting_manifest_entry() -> None:
    raw = raw_transit()
    raw["limits"] = []
    values = host_values(raw)
    entry = notice(values["transit_state"], 1)
    values["transit_state"] = replace(values["transit_state"], revoked=True)
    result = compose_briefing(**dict(values, items=(entry,)))
    assert {"calendar", "area_career"} <= {section.id for section in result.sections}
    assert "transit" not in {section.id for section in result.sections} and result.warnings
    assert entry.request.candidate.text in visible(result)
    assert_zero_effects(result)


def test_bm05_mismatched_p8_revision_is_omitted_without_blocking_current_items() -> None:
    values = host_values(raw_transit())
    entry = notice(values["transit_state"], 1)
    values["transit_state"] = replace(values["transit_state"], revision=values["profile_revision"] + 1)
    result = compose_briefing(**dict(values, items=(entry,)))
    assert {"calendar", "area_career"} <= {section.id for section in result.sections}
    assert "transit" not in {section.id for section in result.sections} and result.warnings
    assert entry.request.candidate.text in visible(result)
    assert_zero_effects(result)


def test_bm06_disabled_subscription_still_returns_before_items_are_rendered() -> None:
    values = host_values(enabled=False)
    first = notice(values["subscription_state"], 1)
    second = notice(replace(values["subscription_state"], revoked=True), 2)
    result = compose_briefing(**dict(values, items=(first, second)))
    assert result.sections == result.basis == result.omissions == ()
    assert result.delivery is None and "brief_not_subscribed" in result.warnings
    assert_zero_effects(result)


@pytest.mark.parametrize(
    "reverse", [pytest.param(False, id="BM07-active-first"), pytest.param(True, id="BM08-revoked-first")]
)
def test_item_order_never_selects_a_local_state_over_its_contradictory_peer(reverse: bool) -> None:
    values = host_values()
    state = BriefSourceState("synthetic-manifest-shared-source", values["scope"], 1, digest(fictional_text(1)))
    first = notice(state, 1, body=fictional_text(1))
    second = notice(replace(state, revoked=True), 2, body=fictional_text(1))
    entries = (second, first) if reverse else (first, second)
    assert_current_conflict(dict(values, items=entries))
