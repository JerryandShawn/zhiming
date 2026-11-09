"""Owner-scoped read view of pending idle-reflection proposals for the confirm/ignore UI."""

from __future__ import annotations

from typing import Any

from mingjing_core.application.memory2_proposals import reflection_reviewable
from mingjing_core.application.memory2_undo import verify_originals
from mingjing_core.domain.contracts import CoreError

ORIGIN = "memory2_reflection"
LIMIT = 50


def pending_reflection_proposals(memory: Any, owner: str, subject: str) -> list[dict[str, Any]]:
    """Only rows whose originals are still live; the quote is the owner's own words, nothing else is exposed."""
    repo = memory.repo
    rows = []
    with repo.transaction(owner):
        repo.assert_scope(owner, subject)
        for row in repo.list(owner, "proposal", subject=subject):
            if row.get("origin") != ORIGIN or row.get("status") != "pending":
                continue
            try:
                verify_originals(memory, owner, subject, row.get("source_refs", []))
            except CoreError:
                continue
            ref = row["source_refs"][0]
            rows.append(
                {
                    "id": row["id"],
                    "revision": row["revision"],
                    "kind": row["kind"],
                    "summary": row["summary"],
                    "quote": ref["quote"],
                    "message_id": ref["message_id"],
                    "inferred": bool(row.get("inferred")),
                    "sensitive": not reflection_reviewable(row),
                    "can_remember_category": not reflection_reviewable(row),
                }
            )
            if len(rows) >= LIMIT:
                break
    return rows
