"""Extractive partition selection with current source checks; mainline still owns ContextEngine."""

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta

from mingjing_core.organize.source_projection import (
    SearchSource,
    authorized_index,
    instant,
    source_index,
)
from mingjing_core.timekit.clock import Clock

from .partition_context_v2_contracts import (
    ContextLine,
    PartitionedContext,
    PartitionRecord,
    PartitionScope,
    SummaryInvalidation,
    SummaryInvalidationPlan,
)


def _validate(
    records: tuple[PartitionRecord, ...], scope: PartitionScope, source_epoch: int
) -> None:
    if (
        not isinstance(scope, PartitionScope)
        or type(source_epoch) is not int
        or source_epoch < 0
    ):
        raise ValueError("partition_scope_or_epoch_invalid")
    if not isinstance(records, tuple) or not all(
        isinstance(item, PartitionRecord) for item in records
    ):
        raise ValueError("partition_records_must_be_immutable")
    identities = [
        (item.unit.owner_id, item.unit.subject_id, item.unit.id) for item in records
    ]
    if len(identities) != len(set(identities)):
        raise ValueError("partition_duplicate_unit")


def _eligible(
    record: PartitionRecord,
    scope: PartitionScope,
    by_id: dict[str, SearchSource] | None,
    now: datetime,
) -> bool:
    unit = record.unit
    constraint = unit.category != "constraint" or (
        unit.kind in {"fact", "event", "fact_event"}
        and unit.origin == "user"
        and not unit.inferred
    )
    return (
        record.life_thread_id == scope.life_thread_id
        and constraint
        and unit.valid
        and unit.said_at <= now
        and authorized_index(unit, scope.owner_id, scope.subject_id, by_id)
    )


def _brief(text: str, maximum: int = 120) -> str:
    sentence = re.split(r"[。！？!?\n]|(?<=\.)\s+(?=\S)", text, maxsplit=1)[0]
    return sentence if len(sentence) <= maximum else sentence[:maximum] + "…"


def _line(
    record: PartitionRecord, scope: PartitionScope, *, abbreviated: bool = False
) -> ContextLine:
    unit = record.unit
    content = (
        record.title or unit.text
        if record.layer == "open_topic" and abbreviated
        else unit.text
    )
    if abbreviated:
        content = _brief(content)
    attribution = (
        "派生摘要，非新增用户事实" if record.layer == "summary" else "原话来源投影"
    )
    if record.layer == "round":
        attribution = "用户与助手原话轮次"
    elif record.layer == "open_topic":
        attribution = "话题元数据，非新增用户事实"
    if unit.inferred and record.layer != "summary":
        attribution = "助手推断，非用户事实"
    return ContextLine(
        unit.id,
        record.revision,
        record.space_id,
        record.topic_id,
        content,
        unit.source_refs,
        record.score * (1.5 if record.space_id == scope.space_id else 1.0),
        attribution,
        abbreviated,
    )


def _rank(
    records: list[PartitionRecord], scope: PartitionScope
) -> tuple[ContextLine, ...]:
    lines = (_line(item, scope) for item in records)
    return tuple(sorted(lines, key=lambda line: (-line.weighted_score, line.id)))


def _recent(
    records: list[PartitionRecord], scope: PartitionScope, now: datetime
) -> tuple[ContextLine, ...]:
    grouped: dict[str, list[PartitionRecord]] = defaultdict(list)
    for item in records:
        if item.space_id != scope.space_id and item.unit.said_at >= now - timedelta(
            days=7
        ):
            grouped[item.space_id].append(item)
    selected = []
    for space in sorted(grouped):
        latest = sorted(
            grouped[space],
            key=lambda item: (item.unit.said_at, item.unit.id),
            reverse=True,
        )[:2]
        selected.extend(
            _line(item, scope, abbreviated=True) for item in reversed(latest)
        )
    return tuple(selected)


def _fingerprint(
    scope: PartitionScope, source_epoch: int, groups: dict[str, tuple[ContextLine, ...]]
) -> str:
    scope_key = (
        scope.owner_id,
        scope.subject_id,
        scope.life_thread_id,
        scope.space_id,
        scope.topic_id,
        source_epoch,
    )
    values = {
        key: [
            (
                row.id,
                row.revision,
                row.space_id,
                row.topic_id,
                hashlib.sha256(row.text.encode()).hexdigest(),
                [(ref.id, ref.revision) for ref in row.source_refs],
                row.weighted_score,
                row.attribution,
            )
            for row in rows
        ]
        for key, rows in groups.items()
    }
    encoded = json.dumps(
        (scope_key, values), ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    return "partition-" + hashlib.sha256(encoded.encode()).hexdigest()


def _groups(
    eligible: list[PartitionRecord], scope: PartitionScope, now: datetime
) -> dict[str, tuple[ContextLine, ...]]:
    constraints = [item for item in eligible if item.unit.category == "constraint"]
    normal = [item for item in eligible if item.unit.category != "constraint"]
    order = lambda item: (item.space_id != scope.space_id, item.unit.id)  # noqa: E731
    profiles = sorted((item for item in normal if item.layer == "profile"), key=order)
    topics = sorted((item for item in normal if item.layer == "open_topic"), key=order)
    rounds = sorted(
        (
            item
            for item in normal
            if item.layer == "round"
            and item.topic_id == scope.topic_id
            and item.space_id == scope.space_id
        ),
        key=lambda item: (item.unit.said_at, item.unit.id),
    )[-30:]
    summaries = [item for item in normal if item.layer == "summary"]
    current = sorted(
        (
            item
            for item in summaries
            if item.space_id == scope.space_id and item.topic_id is None
        ),
        key=lambda item: (item.unit.said_at, item.unit.id),
    )[-1:]
    return {
        "constraints": _rank(constraints, scope),
        "profile": tuple(
            _line(item, scope, abbreviated=item.space_id != scope.space_id)
            for item in profiles
        ),
        "open_topics": tuple(
            _line(item, scope, abbreviated=item.space_id != scope.space_id)
            for item in topics
        ),
        "rounds": tuple(_line(item, scope) for item in rounds),
        "current_summary": tuple(_line(item, scope) for item in current),
        "recent_elsewhere": _recent(summaries, scope, now),
        "retrieval": _rank(
            [item for item in normal if item.layer == "retrieval"], scope
        ),
    }


def project_partition_context(
    records: tuple[PartitionRecord, ...],
    sources: tuple[SearchSource, ...],
    *,
    scope: PartitionScope,
    source_epoch: int,
    clock: Clock,
) -> PartitionedContext:
    """Select after current source checks; this creates neither a prompt nor token authorization.

    A `round` must be a trusted preassembled user/assistant pair, not two arbitrary raw messages.
    Summaries are existing derived records: this module never invents a semantic summary.
    Mainline must atomically rebuild sources/epoch and apply U38 context/token guards afterwards.
    """
    _validate(records, scope, source_epoch)
    if not isinstance(sources, tuple) or not all(
        isinstance(item, SearchSource) for item in sources
    ):
        raise ValueError("partition_sources_must_be_immutable")
    now = instant(clock.now())
    by_id = source_index(scope.owner_id, scope.subject_id, sources)
    eligible = [item for item in records if _eligible(item, scope, by_id, now)]
    groups = _groups(eligible, scope, now)
    selected = {row.id for rows in groups.values() for row in rows}
    omitted = tuple(
        sorted(
            item.unit.id
            for item in records
            if item.unit.id not in selected
            and item.life_thread_id == scope.life_thread_id
            and (item.unit.owner_id, item.unit.subject_id)
            == (scope.owner_id, scope.subject_id)
        )
    )
    return PartitionedContext(
        scope,
        source_epoch,
        **groups,
        omitted_ids=omitted,
        projection_key=_fingerprint(scope, source_epoch, groups),
    )


def plan_summary_invalidations(
    records: tuple[PartitionRecord, ...],
    sources: tuple[SearchSource, ...],
    *,
    scope: PartitionScope,
    source_epoch: int,
    clock: Clock,
) -> SummaryInvalidationPlan:
    """Return invalidation intents only; never delete source records or mutate a stored summary."""
    _validate(records, scope, source_epoch)
    if not isinstance(sources, tuple) or not all(
        isinstance(item, SearchSource) for item in sources
    ):
        raise ValueError("partition_sources_must_be_immutable")
    now, changes = instant(clock.now()), []
    by_id = source_index(scope.owner_id, scope.subject_id, sources)
    for item in records:
        unit = item.unit
        if item.layer != "summary" or item.life_thread_id != scope.life_thread_id:
            continue
        if (unit.owner_id, unit.subject_id) != (scope.owner_id, scope.subject_id):
            continue
        if not _eligible(item, scope, by_id, now):
            changes.append(
                SummaryInvalidation(
                    unit.id, item.revision, "summary_dependency_no_longer_current"
                )
            )
    ordered = tuple(sorted(changes, key=lambda change: change.id))
    raw = json.dumps(
        (
            scope.owner_id,
            scope.subject_id,
            scope.life_thread_id,
            source_epoch,
            [(item.id, item.expected_revision) for item in ordered],
        ),
        separators=(",", ":"),
    )
    return SummaryInvalidationPlan(
        scope,
        source_epoch,
        ordered,
        "invalidate-" + hashlib.sha256(raw.encode()).hexdigest(),
    )
