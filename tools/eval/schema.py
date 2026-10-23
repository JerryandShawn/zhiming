"""Strict, synthetic-only contracts for the versioned evaluation corpus."""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

JsonMap = dict[str, Any]
Nonempty = Annotated[str, Field(min_length=1)]
TargetName = Literal["v3", "v4"]
Channel = Literal["web", "feishu", "scheduled_report", "synthetic", "tarot", "web-action"]
Category = Literal[
    "time",
    "memory_write",
    "memory_recall",
    "forget",
    "question",
    "proactive",
    "chart",
    "tarot",
    "decision",
    "safety",
    "robustness",
    "portability",
]
SCENARIO_ID = (
    r"^(?:T(?:0[1-9]|1[0-4])|M(?:0[1-9]|1[0-3])|R0[1-9]|F0[1-4]|Q0[1-7]|P0[1-7]|"
    r"C0[1-7]|TA0[1-3]|D0[1-2]|S0[1-4]|X(?:0[1-8]|03[ab])|L0[1-2])$"
)
ID_CATEGORIES = {
    "T": "time",
    "M": "memory_write",
    "R": "memory_recall",
    "F": "forget",
    "Q": "question",
    "P": "proactive",
    "C": "chart",
    "TA": "tarot",
    "D": "decision",
    "S": "safety",
    "X": "robustness",
    "L": "portability",
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def aware_iso(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("A timezone-aware ISO timestamp is required")
    return value


class HistoryMessage(StrictModel):
    id: Nonempty
    role: Literal["user", "assistant", "tool"]
    content: Nonempty
    at: Nonempty
    channel: Channel

    _timestamp = field_validator("at")(aware_iso)


class FactSeed(StrictModel):
    id: Nonempty
    kind: Literal[
        "preference",
        "constraint",
        "background",
        "goal",
        "event",
        "concern",
        "relationship",
        "habit",
    ]
    summary: Nonempty
    quote: Nonempty
    source_message_id: Nonempty
    status: Literal["active", "retired", "pending"] = "active"
    event_at: str | None = None
    sensitivity: Literal["normal", "health", "third_party", "money", "identity", "legal"] = "normal"
    legacy: bool = False
    data: JsonMap = Field(default_factory=dict)

    @field_validator("event_at")
    @classmethod
    def event_date(cls, value: str | None) -> str | None:
        if value is not None:
            aware_iso(value) if "T" in value else date.fromisoformat(value)
        return value


class EntitySeed(StrictModel):
    id: Nonempty
    kind: Nonempty
    status: Nonempty = "active"
    data: JsonMap = Field(default_factory=dict)


class Seed(StrictModel):
    profile: Literal["default_synthetic", "empty_profile"] = "default_synthetic"
    synthetic: Literal[True] = True
    profile_overrides: JsonMap = Field(default_factory=dict)
    facts: list[FactSeed] = Field(default_factory=list)
    thread: list[HistoryMessage] = Field(default_factory=list)
    entities: list[EntitySeed] = Field(default_factory=list)
    settings: JsonMap = Field(default_factory=dict)
    context: JsonMap = Field(default_factory=dict)
    controls: JsonMap = Field(default_factory=dict)
    thread_id: Nonempty = "life-synthetic"
    incognito: bool = False

    @model_validator(mode="after")
    def source_integrity(self) -> Seed:
        messages = {item.id: item for item in self.thread}
        if len(messages) != len(self.thread):
            raise ValueError("History IDs must be unique")
        if len({item.id for item in self.facts}) != len(self.facts):
            raise ValueError("Fact IDs must be unique")
        if len({item.id for item in self.entities}) != len(self.entities):
            raise ValueError("Entity IDs must be unique")
        for fact in self.facts:
            source = messages.get(fact.source_message_id)
            if source is None or source.role != "user" or fact.quote not in source.content:
                raise ValueError("Seed facts require a verbatim user-source quote")
        return self


class DbAssertion(StrictModel):
    kind: str | None = None
    id: str | None = None
    where: JsonMap = Field(default_factory=dict)
    count: Annotated[int, Field(ge=0)] | None = None
    status: str | None = None
    path: str | None = None
    equals: Any = None
    contains: Any = None
    absent: bool = False
    lte: float | int | None = None
    gte: float | int | None = None

    @model_validator(mode="after")
    def has_selector(self) -> DbAssertion:
        if not any((self.kind, self.id, self.path)):
            raise ValueError("A DB assertion needs kind, id, or path")
        if self.path and self.count is not None:
            raise ValueError("Path assertions do not accept entity counts")
        if (self.lte is not None or self.gte is not None) and not self.path:
            raise ValueError("Numeric comparisons require a path")
        if self.lte is not None and self.gte is not None and self.gte > self.lte:
            raise ValueError("Numeric comparison bounds are inconsistent")
        return self


class ChartStabilityAssertion(StrictModel):
    fixture: Literal["C06"]


class Expectation(StrictModel):
    must_include_any: list[Nonempty] = Field(default_factory=list)
    must_include_all: list[Nonempty] = Field(default_factory=list)
    must_not_include: list[Nonempty] = Field(default_factory=list)
    tools_called: list[Nonempty] = Field(default_factory=list)
    tools_not_called: list[Nonempty] = Field(default_factory=list)
    receipts: list[JsonMap] = Field(default_factory=list)
    db: list[DbAssertion] = Field(default_factory=list)
    events: list[Nonempty] = Field(default_factory=list)
    min_questions: Annotated[int, Field(ge=0)] | None = None
    max_questions: Annotated[int, Field(ge=0)] | None = None
    chart_structure: bool = False
    chart_stability: ChartStabilityAssertion | None = None
    judge: Nonempty | None = None

    @model_validator(mode="after")
    def observable_check(self) -> Expectation:
        checks = self.model_dump(exclude={"judge"})
        if not any(checks.values()) and self.min_questions is None and self.max_questions is None:
            raise ValueError("At least one deterministic assertion is required")
        if set(self.tools_called) & set(self.tools_not_called):
            raise ValueError("A tool cannot be both required and forbidden")
        if (
            self.min_questions is not None
            and self.max_questions is not None
            and self.min_questions > self.max_questions
        ):
            raise ValueError("Question count bounds are inconsistent")
        return self


class Turn(StrictModel):
    user: Nonempty
    channel: Channel = "web"
    kind: Literal["chat", "brief", "followup", "action", "report", "turn"] = "chat"
    at: str | None = None
    action: JsonMap = Field(default_factory=dict)
    expect: Expectation

    @field_validator("at")
    @classmethod
    def timestamp(cls, value: str | None) -> str | None:
        return aware_iso(value) if value else value


class ToolCall(StrictModel):
    name: Nonempty
    arguments: JsonMap = Field(default_factory=dict)


class ScriptAction(StrictModel):
    text: str | None = None
    tool_call: ToolCall | None = None
    result: JsonMap | None = None
    receipt: JsonMap | None = None
    db: JsonMap | None = None
    event: Nonempty | None = None
    meta: JsonMap | None = None

    @model_validator(mode="after")
    def has_action(self) -> ScriptAction:
        if all(value is None for value in self.model_dump().values()):
            raise ValueError("An empty replay action is not executable")
        return self


class ScriptedStep(StrictModel):
    turn: Annotated[int, Field(ge=1)]
    model: Annotated[list[ScriptAction], Field(min_length=1)]


class Scenario(StrictModel):
    id: Annotated[str, Field(pattern=SCENARIO_ID)]
    title: Nonempty
    category: Category
    clock: Nonempty
    targets: Annotated[list[TargetName], Field(min_length=1)] = Field(default_factory=lambda: ["v3", "v4"])
    seed: Seed
    turns: Annotated[list[Turn], Field(min_length=1)]
    scripted: Annotated[list[ScriptedStep], Field(min_length=1)]
    notes: str | None = None

    _timestamp = field_validator("clock")(aware_iso)

    @model_validator(mode="after")
    def replay_is_complete(self) -> Scenario:
        prefix = re.match(r"[A-Z]+", self.id)[0]
        if self.category != ID_CATEGORIES[prefix]:
            raise ValueError("Scenario category must match its documented ID prefix")
        if len(set(self.targets)) != len(self.targets):
            raise ValueError("Targets must be unique")
        if sorted(step.turn for step in self.scripted) != list(range(1, len(self.turns) + 1)):
            raise ValueError("Exactly one scripted step is required for every turn")
        return self


def load_scenario(path: str | Path) -> Scenario:
    with Path(path).open(encoding="utf-8") as handle:
        return Scenario.model_validate(yaml.safe_load(handle))


def load_scenarios(directory: str | Path | None = None) -> list[Scenario]:
    root = Path(directory) if directory else Path(__file__).parent / "scenarios"
    scenarios = [load_scenario(path) for path in sorted(root.glob("*.yaml"))]
    if len({item.id for item in scenarios}) != len(scenarios):
        raise ValueError("Scenario IDs must be unique across files")
    return scenarios
