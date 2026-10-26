"""Confirmed, currently sourced About Me items are the L2 profile projection."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mingjing_core.memory.profile_doc import SECTION_TITLES

if TYPE_CHECKING:
    from .context_layers import AliasBook
    from .context_types import ContextItem, SourceSnapshot


def profile_items(snapshot: SourceSnapshot, aliases: AliasBook) -> tuple[list[ContextItem], set[str]]:
    from .context_layers import json_item

    items, represented = [], set()
    documents = getattr(snapshot, "extra_entities", {}).get("profile_doc", ())
    rows = sorted(documents, key=lambda row: (row["section"], row["id"]))
    for row in rows:
        alias = aliases.add("p", "profile_doc", row)
        data = {
            "alias": alias,
            "section": row["section"],
            "title": SECTION_TITLES[row["section"]],
            "text": row["text"],
            "confidence": row["confidence"],
            "inferred": True,
            "confirmed_by_user": True,
        }
        items.append(json_item(row["id"], "画像", data, required=True, sources=tuple(row["source_ids"])))
        represented.update(row["fact_ids"])
    return items, represented
