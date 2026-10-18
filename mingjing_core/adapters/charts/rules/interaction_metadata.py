"""Pure, explicit project labels and school-specific ordering of U2 relations."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def enrich_relations(
    relations: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    policy: dict[str, Any],
    school: str,
) -> list[dict[str, Any]]:
    if school not in policy["priority_by_school"]:
        raise ValueError("时间交互需要具名的项目排序口径")
    by_id = {node["id"]: node for node in nodes}
    output = []
    for relation in relations:
        row = deepcopy(relation)
        ids = [member["id"] for member in row["members"]]
        palaces = [
            palace for palace in policy["palace_order"] if "natal." + palace in ids
        ]
        domains = {
            domain for palace in palaces for domain in policy["palace_domains"][palace]
        }
        for ident in ids:
            domains.update(
                policy["ten_god_domains"].get(by_id[ident]["stem_ten_god"], [])
            )
        row.update(
            palace=palaces,
            domains=[domain for domain in policy["domain_order"] if domain in domains],
            priority={
                key: priorities[row["kind"]]
                for key, priorities in policy["priority_by_school"].items()
            },
            mapping_status=policy["status"],
        )
        output.append(row)
    return sorted(output, key=lambda row: _sort_key(row, policy, school))


def _sort_key(
    row: dict[str, Any], policy: dict[str, Any], school: str
) -> tuple[Any, ...]:
    layers = [
        member["id"].split(".")[1]
        for member in row["members"]
        if member["id"].startswith("target.")
    ]
    layer = min(
        (policy["layer_order"].index(item) for item in layers),
        default=len(policy["layer_order"]),
    )
    return (
        row["priority"][school],
        layer,
        tuple(policy["palace_order"].index(item) for item in row["palace"]),
        row["kind"],
        row["id"],
    )
