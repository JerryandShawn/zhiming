"""Privacy selection includes authorized history; erasure follows merged aliases."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mingjing_core.application.memory2_fact_authority import authorized_fact
from mingjing_core.domain.contracts import EvidenceError, ScopeError

if TYPE_CHECKING:
    from mingjing_core.application.memory import MemoryService


def forget_candidates(memory: MemoryService, owner: str, subject: str, case_ids: list | None = None) -> list[dict]:
    current = {row["id"]: row for row in memory.facts(owner, subject, case_ids)}
    for row in memory.repo.list(owner, "fact", subject=subject, case_ids=case_ids):
        if row.get("superseded_by") and row["status"] == "active" and row.get("assertion_status") == "user_asserted":
            try:
                current[row["id"]] = authorized_fact(memory, owner, subject, row["id"], statuses=frozenset({"active"}))
            except (EvidenceError, ScopeError):
                continue
    return list(current.values())


def merged_descendants(memory: MemoryService, owner: str, seeds: list[dict]) -> list[dict]:
    """Bounded owner/subject/case closure; cycles cannot prevent deletion."""
    children: dict[str, list[dict]] = {}
    for row in memory.repo.list(owner, "fact", include_deleted=True):
        if row.get("merged_into") and row["status"] != "deleted":
            children.setdefault(row["merged_into"], []).append(row)
    result = {row["id"]: row for row in seeds}
    queue = list(seeds)
    while queue:
        parent = queue.pop()
        for row in children.get(parent["id"], []):
            if (
                row["id"] not in result
                and row["subject_id"] == parent["subject_id"]
                and row.get("case_id") == parent.get("case_id")
            ):
                result[row["id"]] = row
                queue.append(row)
    return list(result.values())
