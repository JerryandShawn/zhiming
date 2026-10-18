"""Pure condition checks; a match is never an auspicious/inauspicious judgment."""

from __future__ import annotations

from typing import Any


def result(met: bool, paths: list[str], **details: Any) -> dict[str, Any]:
    return {"met": bool(met), "evidence_paths": paths, "details": details}


def pattern_condition(
    data: dict[str, Any], params: dict[str, Any], graph: dict[str, Any]
) -> dict[str, Any]:
    rows = data["p8"]["patterns"]["regular_eight"]
    matches = [
        (index, row)
        for index, row in enumerate(rows)
        if row["ten_god"] == params["god"]
    ]
    if len(matches) != 1:
        raise ValueError("格局候选条件需要唯一的具名候选")
    index, row = matches[0]
    condition = row["conditions"][params["condition_index"]]
    if type(condition["satisfied"]) is not bool:
        raise ValueError("候选条件必须为明确布尔值")
    path = f"/data/p8/patterns/regular_eight/{index}/conditions/"
    path += str(params["condition_index"])
    return result(
        condition["satisfied"],
        [path],
        condition=condition["condition"],
        observed=condition["evidence"],
        pattern=row["pattern"],
        scope="single_candidate_condition_only",
    )


def exposed_combination(
    data: dict[str, Any], params: dict[str, Any], graph: dict[str, Any]
) -> dict[str, Any]:
    rows = data["p8"]["ten_gods"]["pillars"]
    observed = {
        key: row["exposed"]["ten_god"] for key, row in rows.items() if key != "day"
    }
    present = set(observed.values())
    return result(
        set(params["gods"]) <= present,
        [
            f"/data/p8/ten_gods/pillars/{key}/exposed"
            for key in ("year", "month", "hour")
        ],
        required_gods=params["gods"],
        observed=observed,
        scope="exposed_coappearance_not_effectiveness",
    )


def wealth_weak(
    data: dict[str, Any], params: dict[str, Any], graph: dict[str, Any]
) -> dict[str, Any]:
    exposed = data["p8"]["ten_gods"]["pillars"]
    wealth = [
        key
        for key in ("year", "month", "hour")
        if exposed[key]["exposed"]["ten_god"] in ("正财", "偏财")
    ]
    methods = data["p8"]["strength"]["methods"]
    weak = len(methods) == 2 and all(row["conclusion"] == "偏弱" for row in methods)
    return result(
        len(wealth) >= 2 and weak,
        ["/data/p8/ten_gods", "/data/p8/strength/methods"],
        wealth_exposed_pillars=wealth,
        required_count=2,
        strength_conclusions=[row["conclusion"] for row in methods],
        scope="project_count_and_both_project_strength_methods",
    )


def climate_missing(
    data: dict[str, Any], params: dict[str, Any], graph: dict[str, Any]
) -> dict[str, Any]:
    p8 = data["p8"]
    candidates = p8["climate"]["candidate_stems"]
    present = {
        stem
        for row in p8["ten_gods"]["pillars"].values()
        for stem in [row["exposed"]["stem"], *[item["stem"] for item in row["hidden"]]]
    }
    missing = [stem for stem in candidates if stem not in present]
    return result(
        bool(missing),
        ["/data/p8/climate", "/data/p8/ten_gods/pillars"],
        candidate_stems=candidates,
        missing_stems=missing,
        source_locator=p8["climate"]["source_locator"],
        scope="excerpt_candidates_absent_from_exposed_and_selected_hidden_table",
    )


def palace_activation(
    data: dict[str, Any], params: dict[str, Any], graph: dict[str, Any]
) -> dict[str, Any]:
    found = []
    for index, row in enumerate(graph.get("relations", [])):
        ids = [member["id"] for member in row["members"]]
        if (
            row["kind"] in ("六冲", "六合")
            and row.get("complete", True)
            and "natal." + params["palace"] in ids
            and any(ident in ("target.decadal", "target.yearly") for ident in ids)
        ):
            found.append((index, row))
    return result(
        bool(found),
        [f"/data/p8/time_interactions/relations/{index}" for index, _ in found],
        natal_pillar=params["palace"],
        relation_ids=[row["id"] for _, row in found],
        relation_kinds=[row["kind"] for _, row in found],
        target_layers=sorted(
            {
                member["id"].split(".")[1]
                for _, row in found
                for member in row["members"]
                if member["id"] in ("target.decadal", "target.yearly")
            }
        ),
        scope="decadal_or_yearly_branch_relation_only",
    )


CONDITIONS = {
    "pattern_condition": pattern_condition,
    "exposed_combination": exposed_combination,
    "wealth_weak": wealth_weak,
    "climate_missing": climate_missing,
    "palace_activation": palace_activation,
}
