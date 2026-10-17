"""Eight auxiliary markers, returning placements rather than fate judgments."""

from __future__ import annotations

from typing import Any

from .elements import BRANCHES, STEMS, block, table


def auxiliary_stars(pillars: dict[str, str]) -> dict[str, Any]:
    rules = table("auxiliary_stars")
    master = pillars["day"][0]
    rows = []
    for name, stem_table in rules["stem_tables"].items():
        targets = stem_table.get(master, "")
        rows.append(
            {
                "name": name,
                "anchor": {"pillar": "day", "stem": master},
                "target_branches": list(targets),
                "applicability": "defined" if targets else "not_defined_for_yin_stem",
                "placements": [
                    {"pillar": key, "branch": value[1]} for key, value in pillars.items() if value[1] in targets
                ],
            }
        )
    for name, branch_table in rules["branch_tables"].items():
        for anchor in ("year", "day"):
            branch = pillars[anchor][1]
            targets = next(target for group, target in branch_table.items() if branch in group)
            rows.append(
                {
                    "name": name,
                    "anchor": {"pillar": anchor, "branch": branch},
                    "target_branches": list(targets),
                    "placements": [
                        {"pillar": key, "branch": value[1]} for key, value in pillars.items() if value[1] in targets
                    ],
                }
            )
    # A sexagenary decade uses ten stems and leaves two of the twelve branches empty.
    day = pillars["day"]
    decade_start = (BRANCHES.index(day[1]) - STEMS.index(day[0])) % 12
    empty = [BRANCHES[(decade_start + offset) % 12] for offset in (10, 11)]
    rows.append(
        {
            "name": "空亡",
            "anchor": {"pillar": "day", "ganzhi": day},
            "target_branches": empty,
            "placements": [{"pillar": key, "branch": value[1]} for key, value in pillars.items() if value[1] in empty],
        }
    )
    return block(
        rules["method"],
        rules["source"],
        rules_version=rules["version"],
        source_refs=rules["source_refs"],
        markers=rows,
        distinct_markers=sorted({row["name"] for row in rows}),
        warnings=["神煞属辅助参考；不输出灾病死亡断语", *rules["limitations"]],
    )
