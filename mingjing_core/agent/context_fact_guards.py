"""L2 structured facts remain authoritative even when a profile summarizes them."""

from typing import Any

from .context_types import ContextItem, ContextLayer, SourceSnapshot


def fact_item(row: dict[str, Any], aliases: Any) -> ContextItem:
    from .context_layers import json_item

    data = {
        "alias": aliases.add("f", "fact", row),
        "date": row.get("said_at") or row.get("valid_from"),
        "kind": row["kind"],
        "text": row["content"],
    }
    if (row.get("field") == "birth.precision" and row.get("value") == "unknown") or (
        row.get("field") == "birth.time_unknown" and row.get("value") is True
    ):
        data["birth_time_notice"] = "时辰还不确定，以下只看不依赖时柱的部分。"
    return json_item(row["id"], "画像", data, required=True)


def preserve_field_facts(snapshot: SourceSnapshot, aliases: Any, layer: ContextLayer) -> ContextLayer:
    """Only current authorized snapshot facts can restore a structured L2 entry.

    Run after profile projection: a represented-fact optimization cannot erase
    calculation boundary notices or replace fields with an inferred summary.
    """
    items = list(layer.items)
    positions = {item.key: index for index, item in enumerate(items)}
    for row in sorted(snapshot.facts, key=lambda fact: (fact.get("kind") != "constraint", fact["id"])):
        if not row.get("field"):
            continue
        actual = fact_item(row, aliases)
        if row["id"] in positions:
            items[positions[row["id"]]] = actual
        else:
            positions[row["id"]] = len(items)
            items.append(actual)
    return ContextLayer(layer.name, tuple(items))
