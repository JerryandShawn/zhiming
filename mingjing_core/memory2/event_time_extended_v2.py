"""Source-bound extended event dates are review candidates, never save or scheduling authority."""

import re
from dataclasses import dataclass, field, replace
from datetime import datetime

from mingjing_core.timeparse.calendar_port import CalendarPort
from mingjing_core.timeparse.contracts import AbsolutizedText, ParseContext, TimeRangeResult, make_result
from mingjing_core.timeparse.extended_v2 import absolutize_extended

from .contracts import MemoryFact, MemorySnapshot
from .guards import authorize_fact

_RECURRING = re.compile(
    r"\b(?:every|each)\s+(?:(?:other|second|third|\d+)\s+)?"
    r"(?:day|week|month|year|morning|afternoon|evening|night|monday|tuesday|wednesday|"
    r"thursday|friday|saturday|sunday)s?\b"
    r"|\b(?:daily|weekly|monthly|yearly|annually)\b|每(?:天|日|早|晚|周|星期|个?(?:星期|周|月|年)|年|月|隔)",
    re.I,
)
_NONASSERTION = re.compile(
    r"\b(?:if|suppose|supposing|hypothetical|hypothetically|maybe|perhaps|assuming)\b"
    r"|\bfor\s+(?:example|instance)\b|\blet['’]s\s+say\b"
    r"|\bimagine\s+(?:that\s+)?(?:an?|the|i|we|you|he|she|they|it|having|being|attending|tomorrow)\b"
    r"|\b(?:might|may)\s+(?:not\s+)?(?:attend|be|go|meet|have|visit|interview|travel|join|leave|return|work)\b",
    re.I,
)
_CONTEXT_BOUNDARY = re.compile(r"[\n;；。！？!?]")


@dataclass(frozen=True)
class ExtendedEventCandidate:
    original: MemoryFact = field(repr=False)
    projected: MemoryFact | None = field(repr=False)
    time: TimeRangeResult = field(repr=False)
    wording: AbsolutizedText = field(repr=False)
    needs_clarification: bool
    reason: str | None = None

    @property
    def original_source_text(self) -> str:
        return self.wording.original_text

    @property
    def normalized_source_text(self) -> str:
        return self.wording.text


def _multiple_anchors(text: str, at: datetime, tz: str) -> AbsolutizedText:
    ctx = ParseContext(at, tz, text)
    result = make_result(
        ctx,
        start=None,
        end=None,
        matched_text=text,
        confidence=0.2,
        needs_clarification=True,
        reason="multiple_primary_source_anchors",
        normalized_text="多个原话片段的事件边界待确认",
    )
    return AbsolutizedText(text, text, result, False)


def _conflicts(fact: MemoryFact, result: TimeRangeResult) -> bool:
    return (fact.event_at is not None and fact.event_at != result.start) or (
        fact.event_end is not None and fact.event_end != result.end
    )


def _safe_wording(text: str, at: datetime, tz: str, calendar: CalendarPort | None) -> AbsolutizedText:
    wording = absolutize_extended(text, at, tz, calendar)
    if not _RECURRING.search(text) or wording.result.kind == "recurring":
        return wording
    # Fail closed if the extended parser recognized a weekday inside an unsupported recurrence.
    result = replace(
        wording.result,
        start=None,
        end=None,
        kind="recurring",
        candidates=(),
        needs_clarification=True,
        normalized_text="周期事件需要独立调度规则",
        reason="recurring_source_requires_rule",
    )
    return AbsolutizedText(text, text, result, False)


def _nonassertion_context(source_text: str, start: int, end: int) -> bool:
    # Source context is used solely to reject nonassertions, never to extract unanchored dates.
    # English dots can be abbreviations (Dr., e.g.); the containing fragment is conservative.
    left = list(_CONTEXT_BOUNDARY.finditer(source_text[:start]))
    right = _CONTEXT_BOUNDARY.search(source_text[end:])
    beginning = left[-1].end() if left else 0
    ending = end + right.start() if right else len(source_text)
    return bool(_NONASSERTION.search(source_text[beginning:ending]))


def _nonasserted_wording(text: str, at: datetime, tz: str) -> AbsolutizedText:
    result = make_result(
        ParseContext(at, tz, text),
        start=None,
        end=None,
        matched_text=text,
        confidence=0.2,
        needs_clarification=True,
        reason="english_nonassertion_source",
        normalized_text="条件或示例中的事件需先确认是否实际发生",
    )
    return AbsolutizedText(text, text, result, False)


def absolute_event_candidate_extended(
    fact: MemoryFact,
    snapshot: MemorySnapshot,
    *,
    tz: str = "Asia/Shanghai",
    calendar: CalendarPort | None = None,
) -> ExtendedEventCandidate:
    """Read primary original quotes at their source time, preserving anchors and source revisions.

    Disjoint anchors are a display-only composite in source order, never a synthesized assertion.
    No profile port is accepted: persisting a birthday-derived date requires a future profile
    dependency ledger. Persisting any projected event still requires Q2 policy/source rechecks.
    """
    authorize_fact(fact, snapshot, snapshot.scope)
    if fact.kind != "event":
        raise ValueError("event_fact_required")
    primary = snapshot.source(fact.source_ids[0])
    anchors = sorted(
        (anchor for anchor in fact.anchors if anchor.source_id == primary.id),
        key=lambda anchor: (anchor.start, anchor.end),
    )
    text = "；".join(anchor.quote for anchor in anchors)
    if len(anchors) == 1 and _nonassertion_context(primary.text, anchors[0].start, anchors[0].end):
        wording = _nonasserted_wording(text, primary.at, tz)
    else:
        wording = (
            _safe_wording(text, primary.at, tz, calendar)
            if len(anchors) == 1
            else _multiple_anchors(text, primary.at, tz)
        )
    result = wording.result
    clear = (
        result.start is not None
        and result.end is not None
        and (result.end > result.start or (result.kind == "point" and result.end == result.start))
        and result.span is not None
        and not result.needs_clarification
        and result.kind != "recurring"
    )
    reason = result.reason
    if clear and _conflicts(fact, result):
        clear, reason = False, "existing_event_time_conflict"
    projected = None
    if clear:
        # A model summary never becomes parsing input and is not rewritten to resemble a quote.
        projected = replace(
            fact,
            event_at=result.start,
            event_end=result.end,
            text=wording.text if len(anchors) == 1 and fact.text == anchors[0].quote else fact.text,
        )
    return ExtendedEventCandidate(fact, projected, result, wording, not clear, reason)
