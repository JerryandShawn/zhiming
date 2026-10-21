"""Bound quotations are useful work candidates; they are not generated narrative or emotion detection."""

from datetime import timedelta

from mingjing_core.memory2.contracts import MemorySnapshot, SourceAnchor

from .schedule_contracts import ReflectionIntent
from .validation import dataclass_json, digest
from .work_contracts import BoundExcerpt, ExtractiveSummary


def extractive_summaries(
    intent: ReflectionIntent,
    snapshot: MemorySnapshot,
) -> tuple[tuple[ExtractiveSummary, ...], ExtractiveSummary | None]:
    sources = [snapshot.source(row.id) for row in intent.source_manifest]
    ordered = sorted(
        (source for source in sources if source is not None and source.text), key=lambda row: (row.at, row.id)
    )
    groups: list[list[BoundExcerpt]] = []
    for source in ordered:
        quote = source.text[:480]
        anchor = SourceAnchor(source.id, source.revision, 0, len(quote), quote)
        excerpt = BoundExcerpt(source.id, source.revision, source.role, source.at, anchor)
        if not groups or source.at - groups[-1][-1].at > timedelta(hours=6):
            groups.append([])
        groups[-1].append(excerpt)
    episodes = tuple(_summary(intent, tuple(group), "episode_candidate") for group in groups)
    all_excerpts = tuple(row for group in groups for row in group)
    rolling = _summary(intent, all_excerpts, "thread_summary_candidate") if all_excerpts else None
    return episodes, rolling


def _summary(intent: ReflectionIntent, excerpts: tuple[BoundExcerpt, ...], kind: str) -> ExtractiveSummary:
    identity = digest([intent.input_fingerprint, kind, dataclass_json(excerpts)])
    return ExtractiveSummary(
        "summary:" + identity,
        intent.scope,
        intent.thread_id,
        kind,
        intent.snapshot_revision,
        intent.source_epoch,
        excerpts,
    )
