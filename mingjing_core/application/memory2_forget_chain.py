"""Detach withdrawn facts without reviving unverified predecessors in update chains."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mingjing_core.application.memory2_fact_authority import authorized_fact
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.repositories.postgres import fingerprint

if TYPE_CHECKING:
    from mingjing_core.application.memory import MemoryService

ACTIVE = frozenset({"active"})


def _neighbor(memory: MemoryService, owner: str, fact: dict, direction: str, removed: dict) -> dict | None:
    current, seen = fact, {fact["id"]}
    reverse = "superseded_by" if direction == "supersedes" else "supersedes"
    while ident := current.get(direction):
        if ident in seen:
            return None
        seen.add(ident)
        try:
            row = removed.get(ident) or authorized_fact(memory, owner, fact["subject_id"], ident, statuses=ACTIVE)
        except (EvidenceError, ScopeError):
            return None
        if row.get(reverse) != current["id"] or row.get("case_id") != fact.get("case_id"):
            return None
        older, newer = (row, current) if direction == "supersedes" else (current, row)
        if older.get("valid_to") != newer.get("valid_from"):
            return None
        if ident not in removed:
            return row
        current = row
    return None


def _prior_end(memory: MemoryService, owner: str, previous: dict, removed: dict) -> tuple[bool, Any]:
    # Only a still-current program change can certify the old endpoint. Missing
    # snapshots or later edits must never turn an arbitrary historical row current.
    for change in memory.repo.list(owner, "proposal", subject=previous["subject_id"]):
        before = change.get("old_before")
        if not isinstance(before, dict) or before.get("id") != previous["id"]:
            continue
        managed = (
            change.get("kind") in {"memory2_slot_undo", "memory2_chain_repair"}
            and change["status"] == "applied"
            or change.get("proposal_type") == "memory_conflict"
            and change["status"] == "resolved_new"
        )
        if (
            managed
            and change.get("case_id") == previous.get("case_id")
            and change.get("old_revision") == previous["revision"]
            and previous.get("superseded_by") in removed
            and previous["superseded_by"] in change.get("fact_ids", [])
        ):
            return True, before.get("valid_to")
    return False, None


def detach_withdrawn_chain(memory: MemoryService, owner: str, withdrawn: list[dict]) -> None:
    """Run inside the privacy transaction, before its derived snapshots are purged."""
    removed = {row["id"]: row for row in withdrawn}
    changed, visited, continuations = [], set(), []
    for fact in withdrawn:
        previous = _neighbor(memory, owner, fact, "supersedes", removed)
        following = _neighbor(memory, owner, fact, "superseded_by", removed)
        if previous and following and previous["id"] == following["id"]:
            continue  # A corrupt cycle must neither revive data nor block deletion.
        key = (
            previous["id"] if previous else None,
            following["id"] if following else None,
        )
        if key in visited:
            continue
        visited.add(key)
        if previous:
            certified, prior_end = _prior_end(memory, owner, previous, removed)
            patch = {"superseded_by": following["id"] if following else None}
            if following:
                patch["valid_to"] = following["valid_from"]
            elif certified:
                patch["valid_to"] = prior_end
            updated = memory.repo.update(
                owner,
                "fact",
                previous["id"],
                patch,
                expected_revision=previous["revision"],
                operation_id="memory2_detach:"
                + fingerprint([owner, sorted(removed), previous["id"], previous["revision"]]),
            )
            if following and certified:
                continuations.append((previous, following, updated, prior_end))
            changed.append(previous["id"])
        if following:
            memory.repo.update(
                owner,
                "fact",
                following["id"],
                {"supersedes": previous["id"] if previous else None},
                expected_revision=following["revision"],
                operation_id="memory2_detach:"
                + fingerprint([owner, sorted(removed), following["id"], following["revision"]]),
            )
            changed.append(following["id"])
    if changed:
        memory.repo.invalidate_derived(owner, changed, [], recomputable=True)
    for previous, following, updated, prior_end in continuations:
        _record_continuation(memory, owner, previous, following, updated, prior_end, removed)


def _record_continuation(
    memory: MemoryService,
    owner: str,
    previous: dict,
    following: dict,
    updated: dict,
    prior_end: Any,
    removed: dict,
) -> None:
    # The deleted middle node's snapshot is about to be purged. Recertify only the
    # surviving endpoints so a later withdrawal can still restore their interval.
    ident = "memory2_chain_" + fingerprint([owner, sorted(removed), previous["id"], following["id"]])[:32]
    refs = [*previous["source_refs"], *following["source_refs"]]
    memory.repo.put(
        owner,
        "proposal",
        ident,
        {
            "kind": "memory2_chain_repair",
            "status": "applied",
            "old_before": dict(previous, valid_to=prior_end, superseded_by=None),
            "old_revision": updated["revision"],
            "fact_ids": [previous["id"], following["id"]],
            "source_refs": refs,
            "source_ids": list(dict.fromkeys(ref["message_id"] for ref in refs)),
        },
        subject=previous["subject_id"],
        case_id=previous.get("case_id"),
        expected_revision=0,
        operation_id=ident,
    )
