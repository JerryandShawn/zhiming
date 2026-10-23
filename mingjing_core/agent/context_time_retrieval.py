"""Time-ranked retrieval keeps original-source authority and bounded lexical work."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from mingjing_core.domain.time_ranges import TimeRangeParser
from mingjing_core.memory.tokenize import tokenize
from mingjing_core.memory2.ranking import rank_key, ranked_projection
from mingjing_core.repositories.context_retrieval import time_query_candidates
from mingjing_core.timekit.clock import get_clock
from mingjing_core.timekit.timestamps import history_instant

from .context_types import ContextInputError

if TYPE_CHECKING:
    from .context_sources import BoundedSources


@dataclass(frozen=True)
class RetrievalWindow:
    start: datetime
    end: datetime
    zone: str

    @property
    def label(self) -> str:
        start = self.start.astimezone(ZoneInfo(self.zone)).date()
        last = (self.end - timedelta(microseconds=1)).astimezone(ZoneInfo(self.zone)).date()
        return f"{start.isoformat()}..{last.isoformat()}"

    def matches(self, row: dict[str, Any]) -> bool:
        value = row.get("event_at") if row.get("_retrieval_kind") == "fact" else None
        value = value or row.get("said_at") or row.get("at")
        if isinstance(value, str) and len(value) == 10:
            try:
                point = datetime.fromisoformat(value).replace(tzinfo=ZoneInfo(self.zone))
            except ValueError:
                return False
            return point < self.end and point + timedelta(days=1) > self.start
        point = history_instant(value)
        return point is not None and self.start <= point < self.end


def time_window(parser: TimeRangeParser, query: str, source: dict[str, Any], zone: str) -> RetrievalWindow | None:
    reference = history_instant(source.get("at"))
    if reference is None:
        raise ContextInputError("context_source_time_invalid")
    result = parser.parse_time_range(query, reference, zone)
    if (
        result.needs_clarification
        or result.confidence < 0.8
        or result.kind == "recurring"
        or result.start is None
        or result.end is None
    ):
        return None
    end = result.end if result.end > result.start else result.start + timedelta(microseconds=1)
    return RetrievalWindow(result.start, end, zone)


def _project(
    sources: BoundedSources,
    owner: str,
    subject: str,
    row: dict[str, Any],
    facts: dict[str, dict[str, Any]],
    cases: tuple[str, ...],
) -> dict[str, Any] | None:
    if row.get("_retrieval_kind") != "fact":
        result = sources._project(owner, subject, row, list(facts.values()), cases)
        return dict(result, _retrieval_kind="message") if result else None
    # Facts were already checked against current source versions, original spans,
    # owner/subject/cases and withdrawal state by BoundedSources._facts.
    fact = facts.get(row["id"])
    if fact is None:
        return None
    original = next(ref for ref in fact["source_refs"] if ref.get("quote") == fact.get("content"))
    source = sources._source(owner, original["message_id"])
    if sources._project(owner, subject, source, list(facts.values()), cases) is None:
        return None
    return dict(
        fact,
        said_at=fact.get("said_at") or source.get("at"),
        _retrieval_kind="fact",
        search_rank=row.get("search_rank", 0),
    )


def retrieve(
    sources: BoundedSources,
    owner: str,
    subject: str,
    query: str,
    facts: list[dict[str, Any]],
    cases: tuple[str, ...],
    current: dict[str, Any],
    zone: str,
) -> tuple[list[dict[str, Any]], int, str | None]:
    tokens = tokenize(query[:2000])[:32]
    if not tokens:
        return [], 0, None
    window = time_window(sources.time_parser, query, current, zone)
    if window is None:
        rows = [
            dict(row, _retrieval_kind=kind)
            for kind in ("message", "fact")
            for row in sources.repo.search(owner, subject, tokens, [kind], 50)
        ]
    else:
        rows = time_query_candidates(sources.repo, owner, subject, tokens)
    available, seen = [], set()
    known = {fact["id"]: fact for fact in facts}
    for row in rows:
        if row["id"] == current["id"] or row["id"] in seen:
            continue
        projected = _project(sources, owner, subject, row, known, cases)
        if projected is not None:
            seen.add(row["id"])
            available.append(
                ranked_projection(
                    projected,
                    dict(projected, entity_kind=projected["_retrieval_kind"]),
                    clock=get_clock(),
                )
            )
    available.sort(key=rank_key)
    if window is not None:
        available = [dict(row, _time_match=window.matches(row)) for row in available]
        available.sort(key=lambda row: not row["_time_match"])
    return available[: sources.policy.search_limit], len(rows), window.label if window else None
