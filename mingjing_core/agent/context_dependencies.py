"""Keep only injected entities and their recursively referenced source versions."""

from __future__ import annotations

from typing import Any

from mingjing_core.repositories.dependencies import dependency_entity_id

from .context_types import BudgetResult, SourceSnapshot


def injected_versions(snapshot: SourceSnapshot, budget: BudgetResult) -> dict[str, int]:
    catalog: dict[str, dict[str, Any]] = {
        row["id"]: row for row in (*snapshot.facts, *snapshot.history, *snapshot.retrieved, snapshot.current)
    }
    catalog.update({row["id"]: row for rows in snapshot.extra_entities.values() for row in rows})
    pending = {ident for layer in budget.layers for item in layer.items for ident in (item.key, *item.source_ids)}
    retained: set[str] = set()
    while pending:
        ident = pending.pop()
        if ident in retained:
            continue
        retained.add(ident)
        row = catalog.get(ident, {})
        links = set(row.get("source_ids", [])) | set(row.get("used_fact_ids", [])) | set(row.get("fact_ids", []))
        links.update(ref["message_id"] for ref in row.get("source_refs", []))
        if row.get("source_fact_id"):
            links.add(row["source_fact_id"])
        pending.update(links - retained)
    return {key: version for key, version in snapshot.versions.items() if dependency_entity_id(key) in retained}
