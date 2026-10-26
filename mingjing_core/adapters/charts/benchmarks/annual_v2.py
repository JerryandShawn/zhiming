"""A named annual sampling convention, never an invented event month or day."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..adapter import stable_id
from ..interactions_bazi import bazi_interactions
from ..named_bazi import hidden_for, options
from ..rules import evaluate_rules
from .records import fingerprint

METHOD = "e2-target-year-july01-noon-utc8-annual-view-v1"


def annual_basis(year: int) -> dict[str, Any]:
    if type(year) is not int or not 1600 <= year <= 2199:
        raise ValueError("annual_view_explicit_target_year_required")
    return {
        "method": METHOD,
        "explicit_target_year": year,
        "sampling_date": f"{year:04}-07-01",
        "sampling_at": f"{year:04}-07-01T12:00:00+08:00",
        "sampling_date_is_not_event_date": True,
        "event_date": None,
        "event_month": None,
        "event_day": None,
        "visible_time_layers": ["natal", "yearly"],
        "calendar_year_convention": (
            "exact_LiChun_year_containing_named_midyear_snapshot"
        ),
        "limits": [
            "题面仅明确公历年份，事件月日未知；07-01正午只是具名年度采样，不是事件发生日。",
            "年初立春前后可能属于不同节年；没有事件日期，不能选定年初边界哪一侧。",
            "不使用快照流月、流日、流时或采样日所在大运判断具体事件；年度视图只保留原局与流年。",
        ],
    }


def _prune_data(data: dict[str, Any], basis: dict[str, Any]) -> None:
    p8 = data["p8"]
    year_layer = p8["calendar_layers"]["year"]
    for key in ("day", "dayun", "target_liuyue", "target_month", "target_liunian"):
        data.pop(key, None)
    p8.pop("decade_luck", None)
    p8["calendar_layers"] = {
        "method": METHOD,
        "requested_gregorian_year": basis["explicit_target_year"],
        "year": year_layer,
        "limits": basis["limits"],
    }
    selected = {
        key: value
        for key, value in p8["selected_schools"].items()
        if key != "hidden_order"
    }
    graph = bazi_interactions(
        {key: row["ganzhi"] for key, row in data["pillars"].items()},
        {"yearly": year_layer["ganzhi"]},
        hidden_stems=hidden_for(options(selected)),
    )
    p8["time_interactions"] = graph
    rules = evaluate_rules(data, graph=graph)
    p8.update(
        rule_hits=rules["rule_hits"],
        rule_assessments=rules["assessments"],
        rules_version=rules["version"],
    )
    data["e2_time_basis"] = deepcopy(basis)


def _profile(
    source: dict[str, Any], artifact: dict[str, Any], basis: dict[str, Any]
) -> dict[str, Any]:
    profile = deepcopy(source)
    profile["actual_method"]["e2_annual_view"] = dict(
        deepcopy(basis),
        source_profile_id=source["id"],
        source_profile_sha256=fingerprint(source),
        source_artifact_id=artifact["id"],
        source_artifact_sha256=fingerprint(artifact),
        source_natal_sha256=fingerprint(artifact["data"]["pillars"]),
        source_annual_layer_sha256=fingerprint(
            artifact["data"]["p8"]["calendar_layers"]["year"]
        ),
    )
    profile["versions"]["e2_annual_view"] = METHOD
    profile["id"] = stable_id(
        "profile-",
        [METHOD, {key: value for key, value in profile.items() if key != "id"}],
    )
    return profile


def annual_view(bundle: dict[str, Any], year: int) -> dict[str, Any]:
    basis = annual_basis(year)
    result = deepcopy(bundle)
    result.pop("features", None)
    result["artifacts"], result["profiles"] = {}, {}
    for source in bundle["artifacts"].values():
        if (
            source["system"] != "bazi"
            or source["target_date"] != basis["sampling_date"]
        ):
            raise ValueError("annual_view_requires_bound_bazi_sampling_date")
        profile = _profile(bundle["profiles"][source["profile_id"]], source, basis)
        artifact = deepcopy(source)
        _prune_data(artifact["data"], basis)
        artifact["profile_id"] = profile["id"]
        artifact["time_scale"] = "natal_and_annual_view"
        artifact["id"] = stable_id(
            "chart-", [profile["id"], artifact["target_date"], artifact["data"]]
        )
        result["profiles"][profile["id"]] = profile
        result["artifacts"][artifact["id"]] = artifact
    result["benchmark_time_basis"] = basis
    result["benchmark_view_sha256"] = fingerprint(result["artifacts"])
    return result
