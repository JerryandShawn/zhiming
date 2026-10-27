"""Merged current originals stay separate and required; nothing becomes a synthetic quote."""

from dataclasses import replace
from typing import Any

from mingjing_core.application.agent_source_boundary import authorize_boundary
from mingjing_core.domain.contracts import EvidenceError

from .context_types import SourceSnapshot


def attach_turn_sources(memory: Any, snapshot: SourceSnapshot, supplied: dict | None) -> SourceSnapshot:
    if supplied is None:
        return snapshot
    repo = memory.repo
    with repo.transaction(snapshot.owner):
        run = authorize_boundary(repo, snapshot.owner, snapshot.subject, snapshot.current, supplied)
        if ident := run["request"].get("draw_id"):
            from mingjing_core.application.tarot_reveal_ingress import selected_draw

            draw = selected_draw(
                repo,
                snapshot.owner,
                snapshot.subject,
                ident,
                snapshot.current["thread_id"],
                run["request"].get("case_ids"),
            )
            # Only the server's authenticated run can attach this state. Card
            # meanings and faces must still come from tarot_read's tool result.
            projection = {key: draw[key] for key in ("id", "question", "spread_id")}
            snapshot = replace(snapshot, extra_entities=dict(snapshot.extra_entities, revealed_draw=(projection,)))
        identifiers = run["request"].get("source_message_ids")
        if identifiers is None:
            return snapshot
        from mingjing_core.application.thread_sources import ingress_sources, source_segments

        rows = ingress_sources(repo, snapshot.owner, snapshot.subject, snapshot.current["thread_id"], identifiers)
        if rows[-1]["id"] != snapshot.current["id"] or source_segments(rows) != run["request"].get("source_segments"):
            raise EvidenceError("合并轮次来源与已入队的原话区间不符")
        selected = {row["id"] for row in rows}
        versions = dict(snapshot.versions, **{"message:" + row["id"]: row["revision"] for row in rows})
        return replace(
            snapshot,
            history=tuple(row for row in snapshot.history if row["id"] not in selected),
            retrieved=tuple(row for row in snapshot.retrieved if row["id"] not in selected),
            versions=versions,
            extra_entities=dict(snapshot.extra_entities, turn_sources=tuple(rows)),
        )
