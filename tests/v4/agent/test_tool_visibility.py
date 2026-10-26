"""Z3 positive/negative disclosure contracts; no business effects are replaced."""

from __future__ import annotations

from dataclasses import dataclass, replace

import pytest

from mingjing_core.agent.tool_visibility import (
    CONDITIONAL_TOOLS,
    RESIDENT_TOOLS,
    ToolVisibilityConflict,
    VisibilityState,
    select_visible,
)
from mingjing_core.application.agent_tools_contracts import ToolContext
from mingjing_core.domain.contracts import EvidenceError


@dataclass(frozen=True)
class Definition:
    name: str
    read_only: bool = True
    private_allowed: bool = False


def context(**flags: object) -> ToolContext:
    return replace(
        ToolContext(
            "alice", "run", "self", 0, 1, "token", "model", "a" * 64, "life:self"
        ),
        **flags,
    )


def names(
    state: VisibilityState, *, required: tuple[str, ...] = (), **flags: object
) -> tuple[str, ...]:
    definitions = [
        Definition(name) for name in reversed((*RESIDENT_TOOLS, *CONDITIONAL_TOOLS))
    ]
    return tuple(
        tool.name
        for tool in select_visible(
            definitions, context(**flags), state, required=required
        )
    )


def test_exact_ten_residents_and_no_unrelated_conditional_tools() -> None:
    assert names(VisibilityState()) == RESIDENT_TOOLS
    assert len(RESIDENT_TOOLS) == 10 and len(set(RESIDENT_TOOLS)) == 10
    assert "date_calc" not in names(VisibilityState())
    assert "calendar_lookup" not in names(VisibilityState())
    assert "set_reminder" not in names(VisibilityState())


@pytest.mark.parametrize(
    "state,visible",
    [
        (VisibilityState(date_context=True), ("date_calc", "calendar_lookup")),
        (VisibilityState(reminder_requested=True), ("set_reminder",)),
        (VisibilityState(memory_search_has_results=True), ("memory_update",)),
        (VisibilityState(memory_correcting=True), ("memory_update",)),
        (VisibilityState(first_meeting=True), ("profile_update_request",)),
        (VisibilityState(profile_editing=True), ("profile_update_request",)),
        (VisibilityState(tarot_topic=True), ("tarot_start",)),
        (VisibilityState(tarot_pending=True), ("tarot_read",)),
        (
            VisibilityState(case_bound=True),
            ("case_list", "case_update", "case_add_event"),
        ),
        (
            VisibilityState(case_progress=True),
            ("case_list", "case_update", "case_add_event"),
        ),
        (VisibilityState(chart_computed=True), ("chart_skill",)),
    ],
)
def test_each_condition_opens_only_its_fixed_named_capability(
    state: VisibilityState, visible: tuple[str, ...]
) -> None:
    assert names(state) == RESIDENT_TOOLS + visible


def crowded(**changes: bool) -> VisibilityState:
    return replace(
        VisibilityState(
            memory_search_has_results=True,
            first_meeting=True,
            tarot_topic=True,
            case_bound=True,
        ),
        **changes,
    )


def test_optional_overflow_uses_frozen_conditional_order() -> None:
    assert names(crowded()) == RESIDENT_TOOLS + (
        "memory_update",
        "profile_update_request",
        "tarot_start",
        "case_list",
        "case_update",
    )


@pytest.mark.parametrize(
    "state,required",
    [
        (crowded(tarot_pending=True), "tarot_read"),
        (crowded(chart_computed=True), "chart_skill"),
        (crowded(case_progress=True), "case_add_event"),
    ],
)
def test_state_necessary_tool_survives_lower_registration_priority(
    state: VisibilityState, required: str
) -> None:
    selected = names(state)
    assert selected[:10] == RESIDENT_TOOLS and len(selected) == 15
    assert required in selected and "case_update" not in selected


def test_only_tool_is_reserved_before_truncation() -> None:
    selected = names(crowded(), required=("case_update",))
    assert (
        len(selected) == 15
        and selected[-1] == "case_update"
        and "case_add_event" not in selected
    )


def test_impossible_necessary_set_has_distinct_failure_instead_of_dropping_tools() -> (
    None
):
    with pytest.raises(ToolVisibilityConflict) as caught:
        names(
            crowded(
                tarot_pending=True,
                chart_computed=True,
                profile_editing=True,
                memory_correcting=True,
                date_context=True,
                reminder_requested=True,
            )
        )
    assert caught.value.code == "TOOL_VISIBILITY_CONFLICT"


def test_crisis_wins_even_over_state_necessary_tools() -> None:
    assert names(
        crowded(tarot_pending=True, chart_computed=True),
        crisis=True,
        required=("case_update",),
    ) == (
        "time_context",
        "memory_search",
    )


def test_incognito_rejects_long_term_writes_even_if_a_definition_allows_private() -> (
    None
):
    definitions = [
        Definition(name, private_allowed=True)
        for name in (*RESIDENT_TOOLS, *CONDITIONAL_TOOLS)
    ]
    selected = select_visible(
        definitions,
        context(incognito=True),
        crowded(tarot_pending=True, chart_computed=True),
    )
    actual = {tool.name for tool in selected}
    assert (
        "ask_user" in actual and "memory_search" in actual and "chart_skill" in actual
    )
    assert actual.isdisjoint(
        {
            "memory_write",
            "memory_update",
            "memory_forget",
            "note_write",
            "tarot_start",
            "tarot_read",
        }
    )


def test_unimplemented_tools_are_not_fabricated_and_unknown_tools_are_not_disclosed() -> (
    None
):
    definitions = [
        Definition(name) for name in RESIDENT_TOOLS if name != "chart_compute"
    ] + [Definition("unreviewed")]
    selected = select_visible(definitions, context(), VisibilityState())
    assert len(selected) == 9 and "unreviewed" not in {tool.name for tool in selected}
    with pytest.raises(EvidenceError, match="尚未注册"):
        select_visible(
            definitions, context(), VisibilityState(), required=("chart_compute",)
        )


def test_required_does_not_override_an_inactive_condition() -> None:
    assert "tarot_read" not in names(VisibilityState(), required=("tarot_read",))


def test_date_context_or_trusted_required_opens_date_tool_without_replacing_residents() -> (
    None
):
    for state, required in (
        (crowded(date_context=True), ()),
        (crowded(), ("date_calc",)),
    ):
        selected = names(state, required=required)
        assert selected[:10] == RESIDENT_TOOLS and len(selected) == 15
        assert "date_calc" in selected and "case_update" not in selected
    assert "date_calc" not in names(
        VisibilityState(), crisis=True, required=("date_calc",)
    )
