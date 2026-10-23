"""Source-bound profile suggestions; nothing in this module promotes a proposal to a fact."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from .contracts import MemoryScope, utc
from .guards import MemoryGuardError, authorize_fact
from .validation import frozen_tuple, require_bool, require_int, require_text, unique

if TYPE_CHECKING:
    from mingjing_core.timekit.clock import Clock

    from .contracts import MemoryFact, MemorySnapshot

SECTION_TITLES = {
    1: "称呼与基本情况",
    2: "现在的生活",
    3: "在意的事与目标",
    4: "重要的人",
    5: "偏好与禁忌",
    6: "沟通偏好",
    7: "命理档案摘要",
    8: "正在跟进",
}
COMMUNICATION = re.compile(r"回答.{0,5}(?:长|短|详细|简洁)|直说|委婉|命理术语|沟通|语气")
BASIC_SLOT = re.compile(r"(?:name|city|occupation|study|age|称呼|城市|职业|学业|年龄)")
RELATION = re.compile(r"(?:relationship|person|relation|关系|重要的人)")
CHART_ALIAS = re.compile(r"〔[cr][1-9]\d*〕\Z")


@dataclass(frozen=True)
class ProfileItem:
    id: str
    section: int
    text: str = field(repr=False)
    source_ids: tuple[str, ...] = ()
    fact_ids: tuple[str, ...] = ()
    confidence: float = 0.8
    updated_at: datetime | None = None
    pinned: bool = False
    edited_by_user: bool = False

    def __post_init__(self) -> None:
        require_text(self.id, self.text)
        require_int(self.section, 1)
        if self.section not in SECTION_TITLES:
            raise ValueError("profile_item_invalid")
        require_bool(self.pinned, self.edited_by_user)
        if type(self.confidence) not in (int, float) or not 0 <= self.confidence <= 1:
            raise ValueError("profile_confidence_invalid")
        if self.updated_at is not None:
            object.__setattr__(self, "updated_at", utc(self.updated_at))
        for name in ("source_ids", "fact_ids"):
            values = frozen_tuple(getattr(self, name), str)
            require_text(*values)
            unique(values)
            object.__setattr__(self, name, values)


@dataclass(frozen=True)
class ChartSummary:
    id: str
    scope: MemoryScope
    text: str = field(repr=False)
    fact_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    basis_aliases: tuple[str, ...]
    method_version: str
    stability: str
    trusted: bool = False

    def __post_init__(self) -> None:
        require_bool(self.trusted)
        require_text(self.id, self.text)
        if not isinstance(self.scope, MemoryScope):
            raise ValueError("memory_scope_required")
        if not isinstance(self.method_version, str) or not isinstance(self.stability, str):
            raise ValueError("chart_metadata_invalid")
        for name in ("fact_ids", "source_ids", "basis_aliases"):
            values = frozen_tuple(getattr(self, name), str)
            require_text(*values)
            unique(values)
            object.__setattr__(self, name, values)


@dataclass(frozen=True)
class ReflectionProposal:
    id: str
    section: int
    title: str
    text: str = field(repr=False)
    source_ids: tuple[str, ...]
    fact_ids: tuple[str, ...]
    updated_at: datetime
    confidence: float = 0.8
    action: str = "proposal"
    origin: str = "reflection"
    target_item_id: str | None = None
    protected_item_ids: tuple[str, ...] = ()
    basis_aliases: tuple[str, ...] = ()
    method_version: str | None = None
    stability: str | None = None


def _section(fact: MemoryFact) -> int | None:
    slot = fact.slot or ""
    if fact.kind in {"chart_interpretation", "chart_summary", "note", "assistant_claim"}:
        return None
    if fact.kind == "profile" or BASIC_SLOT.search(slot) or re.search(r"称呼我|叫我.{1,8}(?:。|$)", fact.text):
        return 1
    if fact.kind == "communication" or COMMUNICATION.search(fact.text) or slot.startswith("communication"):
        return 6
    if fact.kind in {"goal", "constraint", "concern"}:
        return 3
    if fact.kind in {"relationship", "person"} or RELATION.search(slot):
        return 4
    if fact.kind == "preference":
        return 5
    if fact.kind in {"followup", "reminder", "event"}:
        return 8
    return 2


def _eligible(snapshot: MemorySnapshot, scope: MemoryScope, now: datetime) -> tuple[MemoryFact, ...]:
    result = []
    for fact in snapshot.facts:
        if fact.origin != "user" or fact.status != "active" or fact.said_at > now or fact.recorded_at > now:
            continue
        if fact.valid_from is not None and fact.valid_from > now:
            continue
        if any(value is not None and value <= now for value in (fact.valid_to, fact.event_end)):
            continue
        try:
            authorize_fact(fact, snapshot, scope)
        except MemoryGuardError:
            continue
        result.append(fact)
    return tuple(result)


def _proposal(
    section: int,
    text: str,
    sources: tuple[str, ...],
    facts: tuple[str, ...],
    now: datetime,
    current_items: tuple[ProfileItem, ...],
    *,
    chart: ChartSummary | None = None,
) -> ReflectionProposal | None:
    existing = tuple(item for item in current_items if item.section == section)
    if any(item.text == text for item in existing):
        return None
    protected = tuple(item.id for item in existing if item.pinned or item.edited_by_user)
    target = next((item.id for item in existing if not item.pinned and not item.edited_by_user), None)
    fingerprint = repr((section, text, sources, facts, chart.id if chart else None)).encode("utf-8")
    return ReflectionProposal(
        "reflection:" + hashlib.sha256(fingerprint).hexdigest(),
        section,
        SECTION_TITLES[section],
        text,
        sources,
        facts,
        now,
        target_item_id=target,
        protected_item_ids=protected,
        basis_aliases=chart.basis_aliases if chart else (),
        method_version=chart.method_version if chart else None,
        stability=chart.stability if chart else None,
    )


def _chart_valid(chart: ChartSummary, scope: MemoryScope, facts: tuple[MemoryFact, ...]) -> bool:
    authorized = {fact.id: fact for fact in facts}
    if not chart.trusted or chart.scope != scope or not chart.id or not chart.text or not chart.method_version:
        return False
    if chart.stability not in {"stable", "leaning", "uncertain"}:
        return False
    if not chart.basis_aliases or not all(CHART_ALIAS.fullmatch(alias) for alias in chart.basis_aliases):
        return False
    if not chart.fact_ids or not set(chart.fact_ids) <= authorized.keys():
        return False
    sources = {source for fact_id in chart.fact_ids for source in authorized[fact_id].source_ids}
    return bool(chart.source_ids) and set(chart.source_ids) == sources


def reflection_candidates(
    snapshot: MemorySnapshot,
    current_items: tuple[ProfileItem, ...] = (),
    *,
    scope: MemoryScope,
    clock: Clock,
    chart_summaries: tuple[ChartSummary, ...] = (),
) -> tuple[ReflectionProposal, ...]:
    if snapshot.scope != scope:
        raise MemoryGuardError("scope_mismatch")
    now = utc(clock.now())
    facts = _eligible(snapshot, scope, now)
    result = []
    for section in (1, 2, 3, 4, 5, 6, 8):
        selected = tuple(fact for fact in facts if _section(fact) == section)
        if not selected:
            continue
        sources = tuple(sorted({source for fact in selected for source in fact.source_ids}))
        proposal = _proposal(
            section,
            "；".join(fact.text for fact in selected),
            sources,
            tuple(fact.id for fact in selected),
            now,
            current_items,
        )
        if proposal is not None:
            result.append(proposal)
    for chart in chart_summaries:
        if _chart_valid(chart, scope, facts):
            proposal = _proposal(7, chart.text, chart.source_ids, chart.fact_ids, now, current_items, chart=chart)
            if proposal is not None:
                result.append(proposal)
    return tuple(sorted(result, key=lambda item: (item.section, item.id)))
