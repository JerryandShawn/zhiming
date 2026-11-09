"""Read-only lists for the new web page: pending memory proposals and the About Me sections.

Idle reflection (A) creates proposals outside any chat turn, so run events never carry them to the
page; without this list the user could not see, confirm or ignore them. Only the owner's own quoted
words are returned, never model text, and withdrawn or deleted proposals are excluded.
"""

from __future__ import annotations

from typing import Any

from mingjing_core.application.agent_tools_policy import SENSITIVITIES
from mingjing_core.application.memory2_profile_web import ProfileWebService
from mingjing_core.domain.contracts import EvidenceError, ScopeError

FIELDS = (
    "id",
    "revision",
    "status",
    "proposal_type",
    "origin",
    "kind",
    "summary",
    "sensitivity",
    "categories",
    "inferred",
    "needs_confirmation_reason",
    "created_at",
)
# Mirrors the accept rules in memory2_proposals / profile / conflict services; the page shows a
# confirm button only where the backend would accept the click.
SPECIAL_TYPES = ("profile_doc", "memory_conflict")


def confirmable(row: dict[str, Any]) -> bool:
    return row.get("proposal_type") in SPECIAL_TYPES or row.get("sensitivity") in SENSITIVITIES


def pending_proposals(repo: Any, owner: str, subject: str) -> list[dict[str, Any]]:
    repo.assert_scope(owner, subject)
    result = []
    for row in repo.list(owner, "proposal", subject=subject):
        if row.get("status") != "pending" or repo.is_revoked(owner, "proposal", row["id"]):
            continue
        item = {key: row[key] for key in FIELDS if key in row}
        refs = row.get("source_refs") or []
        item["quotes"] = [ref["quote"] for ref in refs if isinstance(ref, dict) and isinstance(ref.get("quote"), str)]
        item["confirmable"] = confirmable(row)
        result.append(item)
    return result


def profile_sections(repo: Any, owner: str, subject: str) -> list[dict[str, Any]]:
    """About Me rows exactly as the single-row view returns them; rows that fail its checks are skipped."""
    service = ProfileWebService(repo)
    with repo.transaction(owner):
        repo.assert_scope(owner, subject)
        rows = []
        for row in repo.list(owner, "profile_doc", subject=subject):
            try:
                rows.append(service.view(owner, subject, row["id"]))
            except (EvidenceError, ScopeError):
                continue
    return sorted(rows, key=lambda row: (row["section"], row["id"]))
