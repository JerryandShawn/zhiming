"""Check both real pillar sides before projecting comparison structures."""

from __future__ import annotations

from .common import ELEMENTS, PILLARS, STEMS, integer, need, pillars, tokens

BRANCH_PAIRS = {
    "地支六合": ("子丑", "寅亥", "卯戌", "辰酉", "巳申", "午未"),
    "地支六冲": ("子午", "丑未", "寅申", "卯酉", "辰戌", "巳亥"),
}


def visible(value: dict) -> dict:
    need(value["qi_strength_assessed"] is False)
    need(value["method"] == "four_exposed_stems_plus_selected_hidden_table_first_stem_per_branch")
    stems = tokens(value["stems"], STEMS, 8)
    need(len(stems) == 8 and set(value["element_counts"]) == set(ELEMENTS))
    counts = {key: integer(value["element_counts"][key], 0, 8) for key in ELEMENTS}
    expected = {key: sum("木木火火土土金金水水"[STEMS.index(stem)] == key for stem in stems) for key in ELEMENTS}
    need(counts == expected)
    return {"stems": stems, "element_counts": counts, "qi_strength_assessed": False}


def branch_relations(rows: list, left: dict, right: dict) -> list[dict]:
    output, seen = [], set()
    for row in rows:
        need(row["a_pillar"] in PILLARS and row["b_pillar"] in PILLARS)
        need(row["kind"] in BRANCH_PAIRS and row["transformation_established"] is False)
        need(row["a"] == left[row["a_pillar"]] and row["b"] == right[row["b_pillar"]])
        actual = frozenset((row["a"][-1], row["b"][-1]))
        need(actual in {frozenset(pair) for pair in BRANCH_PAIRS[row["kind"]]})
        pair = (row["a_pillar"], row["b_pillar"], row["kind"])
        need(pair not in seen)
        seen.add(pair)
        output.append({key: row[key] for key in ("a_pillar", "b_pillar", "a", "b", "kind")})
    return output


def useful_complement(rows: list, left: dict, right: dict) -> list[dict]:
    output = []
    for row in rows:
        need(row["recipient"] in ("a", "b") and row["method"] in ("扶抑", "调候", "格局"))
        need(row["candidate_only"] is True and row["effective_strength_assessed"] is False)
        need(row["aggregation"] == "union_of_parallel_candidates_not_consensus")
        candidates, other, overlap = (
            tokens(row[key], STEMS, 10) for key in ("candidate_stems", "other_exposed_stems", "overlap")
        )
        need(other == [pair[0] for pair in (right if row["recipient"] == "a" else left).values()])
        need(overlap == sorted(set(candidates).intersection(other)))
        output.append(
            {
                "recipient": row["recipient"],
                "method": row["method"],
                "candidate_stems": candidates,
                "other_exposed_stems": other,
                "overlap": overlap,
                "candidate_only": True,
                "effective_strength_assessed": False,
                "aggregation": row["aggregation"],
            }
        )
    need(len(output) == 6 and len({(row["recipient"], row["method"]) for row in output}) == 6)
    return output


def element_complement(rows: list, visible_a: dict, visible_b: dict) -> list[dict]:
    output = []
    for row in rows:
        need(row["recipient"] in ("a", "b"))
        own, other = (visible_a, visible_b) if row["recipient"] == "a" else (visible_b, visible_a)
        elements = tokens(row["absent_in_own_present_in_other"], ELEMENTS, 5)
        expected = {
            element
            for element in ELEMENTS
            if own["element_counts"][element] == 0 and other["element_counts"][element] > 0
        }
        need(len(set(elements)) == len(elements) and set(elements) == expected)
        output.append({"recipient": row["recipient"], "elements": elements})
    need(len(output) == 2 and {row["recipient"] for row in output} == {"a", "b"})
    return output


def synastry_bazi(value: dict) -> dict:
    left, right = pillars(value["pillars_a"]), pillars(value["pillars_b"])
    combination = value["day_stem_combination"]
    need(combination["a"] == left["day"][0] and combination["b"] == right["day"][0])
    need(type(combination["met"]) is bool and combination["transformation_established"] is False)
    need(combination["met"] == (abs(STEMS.index(combination["a"]) - STEMS.index(combination["b"])) == 5))
    visible_a, visible_b = visible(value["visible_a"]), visible(value["visible_b"])
    need(visible_a["stems"][::2] == [pair[0] for pair in left.values()])
    need(visible_b["stems"][::2] == [pair[0] for pair in right.values()])
    return {
        "pillars_a": left,
        "pillars_b": right,
        "day_stem_combination": {key: combination[key] for key in ("a", "b", "met", "transformation_established")},
        "branch_relations": branch_relations(value["branch_relations"], left, right),
        "visible_a": visible_a,
        "visible_b": visible_b,
        "element_complement": element_complement(value["element_complement"], visible_a, visible_b),
        "useful_complement": useful_complement(value["useful_complement"], left, right),
    }
