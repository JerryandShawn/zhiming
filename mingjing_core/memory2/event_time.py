"""Time candidates preserve the user's wording; they do not save or schedule anything."""

from dataclasses import dataclass, field, replace

from mingjing_core.timeparse import parse_time_range
from mingjing_core.timeparse.calendar_port import CalendarPort
from mingjing_core.timeparse.contracts import TimeRangeResult

from .contracts import MemoryFact, MemorySnapshot
from .guards import authorize_fact


@dataclass(frozen=True)
class AbsoluteEventCandidate:
    original: MemoryFact = field(repr=False)
    projected: MemoryFact | None = field(repr=False)
    time: TimeRangeResult = field(repr=False)
    needs_clarification: bool


def absolute_event_candidate(
    fact: MemoryFact,
    snapshot: MemorySnapshot,
    *,
    tz: str = "Asia/Shanghai",
    calendar: CalendarPort | None = None,
) -> AbsoluteEventCandidate:
    authorize_fact(fact, snapshot, snapshot.scope)
    if fact.kind != "event":
        raise ValueError("只有事件记忆可以生成事件时间候选")
    # said_at is validated against the original source, never the extraction job's time.
    original_time_text = "；".join(anchor.quote for anchor in fact.anchors if anchor.source_id == fact.source_ids[0])
    result = parse_time_range(original_time_text, fact.said_at, tz, calendar)
    clear = result.start is not None and not result.needs_clarification and result.kind != "recurring"
    if fact.event_at is not None and fact.event_at != result.start:
        clear = False
    projected = replace(fact, event_at=result.start, event_end=result.end) if clear else None
    return AbsoluteEventCandidate(fact, projected, result, not clear)
