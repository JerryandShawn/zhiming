"""Pure FTS/vector fusion: one authorization/time filter applies before either score."""

from collections.abc import Iterable, Mapping
from datetime import datetime
from math import isfinite

from .retrieval_types import (
    RetrievalConfig,
    SearchHit,
    SearchSource,
    SearchUnit,
    SourceRef,
    authorized_index,
    instant,
    source_index,
)
from .tokenize import tokenize

__all__ = ["RetrievalConfig", "SearchHit", "SearchSource", "SearchUnit", "SourceRef", "search"]
DEFAULT_CONFIG = RetrievalConfig()


def _time_matches(unit: SearchUnit, since: datetime | None, until: datetime | None) -> bool:
    when = unit.event_at if unit.kind in {"event", "fact_event"} else unit.said_at
    if when is None:
        return since is None and until is None
    return (since is None or when >= since) and (until is None or when < until)


def _score(
    unit: SearchUnit,
    query: frozenset[str],
    vectors: Mapping[str, float] | None,
    config: RetrievalConfig,
    filtered_time: bool,
    at: datetime | None,
) -> float:
    words = frozenset(tokenize(unit.text))
    lexical = len(query & words) / len(query) if query else 1.0
    vector = vectors.get(unit.id, 0.0) if vectors is not None else None
    if vector is not None and (not isfinite(vector) or not 0 <= vector <= 1):
        raise ValueError("向量检索分数无效")
    score = lexical if vector is None else config.vector_weight * vector + (1 - config.vector_weight) * lexical
    if filtered_time:
        score *= config.temporal_boost
    if at is not None and unit.category not in {"goal", "constraint"}:
        age_days = max(0.0, (at - unit.said_at).total_seconds() / 86400)
        score *= 2 ** (-age_days / config.half_life_days)
    return score


def _hits(candidates: list[tuple[SearchUnit, float]], limit: int) -> tuple[SearchHit, ...]:
    seen: set[tuple] = set()
    aliases: set[str] = set()
    result = []
    for unit, score in sorted(candidates, key=lambda item: (-item[1], item[0].id)):
        key = (unit.kind, unit.origin, unit.valid, tuple(sorted((ref.id, ref.revision) for ref in unit.source_refs)))
        if key in seen:
            continue
        seen.add(key)
        attribution = "我上次说过" if unit.origin == "assistant_claim" or unit.kind == "round" else "来源记录"
        alias = unit.alias or f"〔m{len(result) + 1}〕"
        number = len(result) + 1
        while alias in aliases:
            number += 1
            alias = f"〔m{number}〕"
        aliases.add(alias)
        result.append(SearchHit(unit, score, alias, attribution))
        if len(result) == limit:
            break
    return tuple(result)


def search(
    owner: str,
    subject: str,
    query_tokens: Iterable[str],
    kinds: Iterable[str],
    limit: int,
    since: datetime | None = None,
    until: datetime | None = None,
    *,
    units: Iterable[SearchUnit],
    source_state: Iterable[SearchSource],
    vector_scores: Mapping[str, float] | None = None,
    config: RetrievalConfig = DEFAULT_CONFIG,
    at: datetime | None = None,
) -> tuple[SearchHit, ...]:
    """`at` enables injected-clock decay; empty vectors means configured but zero similarity."""
    if not owner or not subject or type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("检索范围或数量无效")
    start, end = instant(since) if since else None, instant(until) if until else None
    if start is not None and end is not None and start >= end:
        raise ValueError("检索时间区间无效")
    stamp = instant(at) if at is not None else None
    query = frozenset(token.lower() for token in query_tokens if token.strip())
    allowed, candidates = frozenset(kinds), []
    sources = source_index(owner, subject, tuple(source_state))
    for unit in units:
        if allowed and unit.kind not in allowed:
            continue
        if not authorized_index(unit, owner, subject, sources) or (not unit.valid and not config.include_history):
            continue
        if not _time_matches(unit, start, end):
            continue
        score = _score(unit, query, vector_scores, config, start is not None or end is not None, stamp)
        if score > 0:
            candidates.append((unit, score))
    return _hits(candidates, limit)
