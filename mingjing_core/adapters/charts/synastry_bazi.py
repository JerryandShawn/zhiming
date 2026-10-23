"""Named symbolic comparisons, without a marriage score or merged birth chart."""

from __future__ import annotations

from collections import Counter
from itertools import product

from ...calculations.bazi.elements import ELEMENTS, element, relations

SCHOOL = "ziping-structural-pairs-and-project-candidate-overlap-v1"
SOURCE = {
    "title": "三命通会卷二：十干合、支元六合、冲击",
    "url": "https://zh.wikisource.org/wiki/三命通會/卷二",
    "status": "public_transcription_original_edition_pending",
}
PROJECT_SOURCE = {
    "title": "P8显式用神三候选与表层五行对读",
    "status": "project_descriptive_comparison_not_traditional_compatibility_algorithm",
}


def _visible(data: dict) -> dict:
    rows = data["p8"]["ten_gods"]["pillars"]
    stems = [
        stem
        for row in rows.values()
        for stem in (row["exposed"]["stem"], row["hidden"][0]["stem"])
    ]
    counts = Counter(element(stem) for stem in stems)
    return {
        "stems": stems,
        "element_counts": {key: counts[key] for key in ELEMENTS},
        "method": "four_exposed_stems_plus_selected_hidden_table_first_stem_per_branch",
        "qi_strength_assessed": False,
    }


def _proposals(data: dict) -> dict[str, list[str]]:
    p8 = data["p8"]
    useful = p8["useful_candidates"]
    return {
        "扶抑": sorted(
            {stem for row in useful["balancing"] for stem in row["candidate_stems"]}
        ),
        "调候": list(p8["climate"]["candidate_stems"]),
        "格局": sorted(
            {stem for row in useful["pattern"] for stem in row["candidate_stems"]}
        ),
    }


def _useful_complement(left: dict, right: dict) -> list[dict]:
    output = []
    for name, own, other in (("a", left, right), ("b", right, left)):
        exposed = [row["gan"] for row in other["pillars"].values()]
        for method, candidates in _proposals(own).items():
            output.append(
                {
                    "recipient": name,
                    "method": method,
                    "candidate_stems": candidates,
                    "other_exposed_stems": exposed,
                    "overlap": sorted(set(candidates).intersection(exposed)),
                    "candidate_only": True,
                    "aggregation": "union_of_parallel_candidates_not_consensus",
                    "effective_strength_assessed": False,
                }
            )
    return output


def bazi_comparison(left: dict, right: dict) -> dict:
    a = {key: row["ganzhi"] for key, row in left["pillars"].items()}
    b = {key: row["ganzhi"] for key, row in right["pillars"].items()}
    branch_rows = []
    for (pa, va), (pb, vb) in product(a.items(), b.items()):
        for kind in relations(va, vb):
            if kind in ("地支六合", "地支六冲"):
                branch_rows.append(
                    {
                        "a_pillar": pa,
                        "b_pillar": pb,
                        "a": va,
                        "b": vb,
                        "kind": kind,
                        "transformation_established": False,
                    }
                )
    visible_a, visible_b = _visible(left), _visible(right)
    complement = []
    for name, own, other in (("a", visible_a, visible_b), ("b", visible_b, visible_a)):
        complement.append(
            {
                "recipient": name,
                "absent_in_own_present_in_other": [
                    key
                    for key in ELEMENTS
                    if own["element_counts"][key] == 0
                    and other["element_counts"][key] > 0
                ],
                "meaning": "表层计数的缺项对照；不表示缺项就是用神或需由他人补足",
            }
        )
    return {
        "pillars_a": a,
        "pillars_b": b,
        "day_stem_combination": {
            "a": a["day"][0],
            "b": b["day"][0],
            "met": "天干五合" in relations(a["day"], b["day"]),
            "transformation_established": False,
        },
        "branch_relations": branch_rows,
        "visible_a": visible_a,
        "visible_b": visible_b,
        "element_complement": complement,
        "useful_complement": _useful_complement(left, right),
        "school": SCHOOL,
    }


def bazi_hits(data: dict) -> list[dict]:
    definitions = []
    if data["day_stem_combination"]["met"]:
        definitions.append(("day_stem_combination", "day-stems-combine", SOURCE))
    definitions += [
        (f"branch_relations/{index}", "branch-" + row["kind"], SOURCE)
        for index, row in enumerate(data["branch_relations"])
    ]
    definitions += [
        (f"element_complement/{index}", "visible-element-complement", PROJECT_SOURCE)
        for index, row in enumerate(data["element_complement"])
        if row["absent_in_own_present_in_other"]
    ]
    definitions += [
        (f"useful_complement/{index}", "useful-candidate-overlap", PROJECT_SOURCE)
        for index, row in enumerate(data["useful_complement"])
        if row["overlap"]
    ]
    return [
        {
            "rule_id": "synastry.bazi." + rule,
            "met": True,
            "school": SCHOOL,
            "source": source,
            "evidence_paths": [
                "/data/bazi/" + path,
                "/data/bazi/pillars_a",
                "/data/bazi/pillars_b",
            ],
        }
        for path, rule, source in definitions
    ]
