"""Z3 fixed disclosure order; trusted state narrows registered capabilities."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol, TypeVar

from mingjing_core.application.agent_tools_contracts import ToolContext
from mingjing_core.domain.contracts import EvidenceError

RESIDENT_TOOLS = (
    "time_context",
    "memory_search",
    "memory_write",
    "memory_forget",
    "note_write",
    "profile_get",
    "ask_user",
    "present_options",
    "chart_compute",
    "schedule_followup",
)
CONDITIONAL_TOOLS = (
    "date_calc",
    "memory_update",
    "profile_update_request",
    "tarot_start",
    "tarot_read",
    "case_list",
    "case_update",
    "case_add_event",
    "chart_skill",
    "daily_transit",
    "window_search",
    "almanac",
    "synastry",
    "calendar_lookup",
    "set_reminder",
)
CRISIS_TOOLS = frozenset({"time_context", "memory_search"})
PRIVATE_WRITES = frozenset(
    {
        "memory_write",
        "memory_update",
        "memory_forget",
        "note_write",
        "profile_update_request",
        "case_update",
        "case_add_event",
        "tarot_start",
        "tarot_read",
        "schedule_followup",
    }
)


@dataclass(frozen=True)
class VisibilityState:
    memory_search_has_results: bool = False
    memory_correcting: bool = False
    first_meeting: bool = False
    profile_editing: bool = False
    tarot_topic: bool = False
    tarot_pending: bool = False
    case_bound: bool = False
    case_progress: bool = False
    chart_computed: bool = False
    date_context: bool = False
    metaphysics_intent: str = "none"
    reminder_requested: bool = False

    def conditional(self) -> dict[str, bool]:
        return {
            "date_calc": self.date_context,
            "memory_update": self.memory_search_has_results or self.memory_correcting,
            "profile_update_request": self.first_meeting or self.profile_editing,
            "tarot_start": self.tarot_topic,
            "tarot_read": self.tarot_pending,
            "case_list": self.case_bound or self.case_progress,
            "case_update": self.case_bound or self.case_progress,
            "case_add_event": self.case_bound or self.case_progress,
            "chart_skill": self.chart_computed,
            "daily_transit": self.metaphysics_intent == "daily",
            "window_search": self.metaphysics_intent == "window",
            "almanac": self.metaphysics_intent == "almanac",
            "synastry": self.metaphysics_intent == "synastry",
            "calendar_lookup": self.date_context,
            "set_reminder": self.reminder_requested,
        }

    def necessary(self) -> set[str]:
        return {
            name
            for name, active in (
                ("date_calc", self.date_context),
                ("memory_update", self.memory_correcting),
                ("profile_update_request", self.profile_editing),
                ("tarot_read", self.tarot_pending),
                ("case_add_event", self.case_progress),
                ("chart_skill", self.chart_computed),
                ("daily_transit", self.metaphysics_intent == "daily"),
                ("window_search", self.metaphysics_intent == "window"),
                ("almanac", self.metaphysics_intent == "almanac"),
                ("synastry", self.metaphysics_intent == "synastry"),
                ("set_reminder", self.reminder_requested),
            )
            if active
        }


class VisibilityTool(Protocol):
    name: str
    read_only: bool
    private_allowed: bool


T = TypeVar("T", bound=VisibilityTool)


class ToolVisibilityConflict(EvidenceError):
    code = "TOOL_VISIBILITY_CONFLICT"


def disclosure_priority(name: str, state: VisibilityState) -> int:
    intent_tool = {"daily": "daily_transit", "window": "window_search", "almanac": "almanac", "synastry": "synastry"}
    if name == "tarot_read" and state.tarot_pending:
        return 0
    if name == intent_tool.get(state.metaphysics_intent):
        return 1
    return {"chart_compute": 2, "chart_skill": 3, "memory_update": 4, "profile_update_request": 4, "date_calc": 5}.get(
        name, 6
    )


def select_visible(
    definitions: Iterable[T],
    ctx: ToolContext,
    state: VisibilityState,
    *,
    required: Iterable[str] = (),
    trimmed_out: list[str] | None = None,
) -> tuple[T, ...]:
    by_name = {item.name: item for item in definitions}
    requested = set(required)
    if requested.difference(by_name):
        raise EvidenceError("本步要求的工具尚未注册")
    conditions = state.conditional()
    order = (*RESIDENT_TOOLS, *CONDITIONAL_TOOLS)
    eligible = [
        name
        for name in order
        if name in by_name and (name in RESIDENT_TOOLS or conditions[name] or name == "date_calc" and name in requested)
    ]
    if ctx.crisis:
        eligible = [name for name in eligible if name in CRISIS_TOOLS]
    if ctx.private:
        eligible = [
            name
            for name in eligible
            if name not in PRIVATE_WRITES and (by_name[name].read_only or by_name[name].private_allowed)
        ]
    # R34: eligibility/privacy is authoritative; priority only removes capabilities.
    selected = set(sorted(eligible, key=lambda name: disclosure_priority(name, state))[:15])
    if trimmed_out is not None:
        trimmed_out.extend(name for name in eligible if name not in selected)
    return tuple(by_name[name] for name in eligible if name in selected)
