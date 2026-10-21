"""Exact v4 entity dependencies coexist with v3 aggregate version keys."""

from __future__ import annotations

DIRECT = frozenset(
    {
        "fact",
        "message",
        "report_schedule",
        "thread",
        "thread_summary",
        "note",
        "profile_doc",
        "knowledge_gap",
        "followup",
        "reminder",
        "proposal",
    }
)


def entity_dependency(kind: str, ident: str) -> str:
    return kind + ":" + ident if kind in DIRECT else "entity:" + kind + ":" + ident


def dependency_entity_id(key: str) -> str:
    return key.split(":", 2)[-1] if key.startswith("entity:") else key.partition(":")[2]


def lineage_key(key: str) -> str:
    return key[7:] if key.startswith("entity:") else key
