"""Two actual spouse palaces read beside the other chart's life palace."""

from __future__ import annotations

from copy import deepcopy

SCHOOL = "installed-py-iztro-natal-plus-project-side-by-side-v1"
SOURCE = {
    "title": "iztro本命十二宫；跨盘并列为项目展示约定",
    "url": "https://docs.iztro.com/posts/astrolabe",
    "status": "installed_named_convention_not_independent_compatibility_validation",
}


def _palace(data: dict, name: str) -> dict:
    found = [row for row in data["palaces"] if row["name"] == name]
    if len(found) != 1:
        raise ValueError("synastry_ziwei_palace_unresolved")
    return deepcopy(
        {key: found[0][key] for key in ("index", "name", "ganzhi", "major", "minor")}
    )


def ziwei_comparison(left: dict, right: dict) -> dict:
    rows = []
    for recipient, own, other in (("a", left, right), ("b", right, left)):
        spouse, life = _palace(own, "夫妻"), _palace(other, "命宫")
        spouse_stars = {row["name"] for row in spouse["major"] + spouse["minor"]}
        life_stars = {row["name"] for row in life["major"] + life["minor"]}
        rows.append(
            {
                "recipient": recipient,
                "own_spouse_palace": spouse,
                "other_life_palace": life,
                "same_branch": spouse["ganzhi"][1] == life["ganzhi"][1],
                "shared_star_names": sorted(spouse_stars.intersection(life_stars)),
                "interpretation": "两盘实际宫位并列供沟通学习；未建立星曜配对吉凶或适配分数算法",
            }
        )
    return {"cross_views": rows, "school": SCHOOL, "compatibility_score": None}


def ziwei_hits(data: dict) -> list[dict]:
    return [
        {
            "rule_id": "synastry.ziwei.spouse-life-readout",
            "met": True,
            "claim_kind": "computed_side_by_side_view_not_affinity_judgment",
            "school": SCHOOL,
            "source": SOURCE,
            "evidence_paths": [f"/data/ziwei/cross_views/{index}"],
        }
        for index in range(len(data["cross_views"]))
    ]
