"""Public window ranking, page boundaries and rule arithmetic."""

from __future__ import annotations

import re
from datetime import date, timedelta

from .common import INVALID_SOURCE, LABELS, LIMITS, PURPOSES, day, digest, integer, need, pointer, ref, verify
from .source_catalog import evidence


def window_weights(value: dict) -> dict:
    need(value["version"] == "project-six-purpose-ranking-v1" and value["prediction_validated"] is False)
    need(value["layer_factors"] == {"yearly": 1, "monthly": 2, "daily": 3})
    need(all(type(item) is int for item in value["layer_factors"].values()))
    weights = value["purpose_weights"]
    need(set(weights) == set(PURPOSES))
    output = {}
    for purpose in PURPOSES:
        need(set(weights[purpose]) == set(LABELS))
        output[purpose] = {}
        for family, labels in LABELS.items():
            need(set(weights[purpose][family]) == set(labels))
            output[purpose][family] = {label: integer(weights[purpose][family][label], -100, 100) for label in labels}
    return {
        "version": value["version"],
        "layer_factors": {"yearly": 1, "monthly": 2, "daily": 3},
        "purpose_weights": output,
        "prediction_validated": False,
    }


def window_rule(root: dict, hit: dict, index: int, weights: dict) -> tuple[dict, str, str]:
    context, purpose = hit["context"], root["data"]["purpose"]
    family, label = context["family"], context["label"]
    need(family in LABELS and label in LABELS[family] and context["recognized"] is True)
    need(context["purpose"] == purpose and context["prediction_validated"] is False)
    need(hit["rule_id"] == f"window.{purpose}.{family}.{label}")
    need(hit["rules_version"] == weights["version"])
    base = integer(context["base_weight"], -100, 100)
    factor = integer(context["layer_factor"], 1, 3)
    contribution = integer(hit["contribution"], -1000, 1000)
    need(base == weights["purpose_weights"][purpose][family][label])
    need(integer(context["contribution"], -1000, 1000) == contribution)
    need(context["reason"] in ("published_project_weight", "incomplete_relation_zero_weight"))
    need(contribution == (0 if context["reason"] == "incomplete_relation_zero_weight" else base * factor))
    need(len(hit["evidence_paths"]) == 2 and hit["evidence_paths"][1] == "/data/weights")
    path = hit["evidence_paths"][0]
    need(re.fullmatch(r"/data/observations/(0|[1-9][0-9]*)", path) is not None)
    observation = pointer(root, path)
    need(observation["date"] == hit["date"] and bool(day(hit["date"])))
    need(observation["kind"] == "derived_copy_of_actual_daily_evidence")
    need(observation["provenance_paths_scope"] == "external_daily_document_not_local_pointers")
    need(observation["facts_sha256"] == digest(observation["facts"]))
    need(observation["daily_hit"]["met"] is True)
    need(isinstance(observation["facts"], list) and bool(observation["facts"]))
    if context["reason"] == "incomplete_relation_zero_weight":
        need(family == "bazi_relation" and observation["daily_hit"]["context"]["complete"] is False)
    alias = root["aliases"]["r"][index]
    output = {
        "date": hit["date"],
        "family": family,
        "label": label,
        "base_weight": base,
        "layer_factor": factor,
        "contribution": contribution,
        "reason": context["reason"],
        "ref": ref(root, alias["alias"]),
        "evidence_refs": [ref(root, name) for name in alias["evidence_aliases"]],
    }
    summary = f"{hit['date']} · {label} · 项目计分 {contribution:+d}；未推断现实结果。"
    return output, path, summary


def window_rules(root: dict, weights: dict) -> tuple[list[dict], dict]:
    rules, summaries = [], {"/data/weights": "公开项目权重；这是启发式排序，不是成功率。"}
    for index, hit in enumerate(root["rule_hits"]):
        rule, path, summary = window_rule(root, hit, index, weights)
        rules.append(rule)
        summaries[path] = summary
    need(len(root["data"]["observations"]) == len(root["rule_hits"]))
    return rules, summaries


def ranking_rows(source: list, start: date, count: int) -> list[dict]:
    ranking = [
        {
            "date": day(row["date"]),
            "rank": integer(row["rank"], 1, 366),
            "score": integer(row["score"], -100000, 100000),
            "positive_sum": integer(row["positive_sum"], 0, 100000),
            "negative_sum": integer(row["negative_sum"], -100000, 0),
        }
        for row in source
    ]
    dates = {(start + timedelta(days=index)).isoformat() for index in range(count)}
    need(len(ranking) == count and {row["date"] for row in ranking} == dates)
    need(ranking == sorted(ranking, key=lambda row: (-row["score"], row["date"])))
    for index, row in enumerate(ranking):
        need(row["rank"] == index + 1 and row["score"] == row["positive_sum"] + row["negative_sum"])
    return ranking


def candidate_row(row: dict, rules: list, ranking: list, used: list) -> dict:
    item = {
        "date": day(row["date"]),
        "rank": integer(row["rank"], 1, 366),
        "score": integer(row["score"], -100000, 100000),
    }
    sums = []
    for group, sign in (("positive_hits", 1), ("negative_hits", -1), ("neutral_hits", 0)):
        selected = []
        for link in row[group]:
            index = integer(link["rule_hit_index"], 0, len(rules) - 1)
            rule = rules[index]
            need(rule["date"] == item["date"] and link["label"] == rule["label"])
            need(integer(link["contribution"], -1000, 1000) == rule["contribution"])
            actual_sign = (rule["contribution"] > 0) - (rule["contribution"] < 0)
            need(actual_sign == sign)
            selected.append(dict(rule))
            used.append(index)
        item[group] = selected
        sums.append(sum(hit["contribution"] for hit in selected))
    need(sum(sums) == item["score"])
    summary = ranking[item["rank"] - 1]
    need(all(item[key] == summary[key] for key in ("date", "rank", "score")))
    need(sums[:2] == [summary["positive_sum"], summary["negative_sum"]])
    return item


def page_view(page: dict, count: int, candidates: list, ranking: list) -> dict:
    offset, limit = integer(page["offset"]), integer(page["limit"], 1, 31)
    keys = ("date", "rank", "score")
    need(
        [{key: row[key] for key in keys} for row in candidates]
        == [{key: row[key] for key in keys} for row in ranking[offset : offset + limit]]
    )
    returned, more = len(candidates), offset + len(candidates) < count
    need(type(page["has_more"]) is bool and page["has_more"] == more)
    need(integer(page["total"], 1, 366) == count and integer(page["returned"], 0, 31) == returned)
    need(page["next_offset"] == (offset + returned if more else None))
    if more:
        integer(page["next_offset"])
    return {
        "total": count,
        "offset": offset,
        "limit": limit,
        "returned": returned,
        "has_more": more,
        "next_offset": offset + returned if more else None,
    }


def window_data(root: dict) -> tuple[dict, dict]:
    data, interval = root["data"], root["data"]["range"]
    need(data["purpose"] in PURPOSES and interval["inclusive"] is True)
    start, end = date.fromisoformat(day(interval["start_date"])), date.fromisoformat(day(interval["end_date"]))
    count = (end - start).days + 1
    need(1 <= count <= 366 and integer(interval["day_count"], 1, 366) == count)
    method = {
        "ranking": "score_descending_then_date_ascending",
        "weights_version": "project-six-purpose-ranking-v1",
        "sample_clock": "12:00:00+08:00",
        "daily_orb_degrees": 2.0,
        "election_hours_searched": False,
        "prediction_validated": False,
    }
    need(data["method"] == method)
    need(data["method"]["election_hours_searched"] is False and data["method"]["prediction_validated"] is False)
    weights = window_weights(data["weights"])
    rules, summaries = window_rules(root, weights)
    ranking = ranking_rows(data["ranking_summary"], start, count)
    used = []
    candidates = [candidate_row(row, rules, ranking, used) for row in data["candidates"]]
    need(sorted(used) == list(range(len(rules))))
    pagination = page_view(data["pagination"], count, candidates, ranking)
    trace = data["trace"]
    need(trace["ranking_summary_sha256"] == digest(data["ranking_summary"]))
    need(trace["weights_sha256"] == digest(data["weights"]))
    need(re.fullmatch(r"[0-9a-f]{64}", trace["query_sha256"]) is not None)
    need(isinstance(data["ignored_conditions"], list))
    return {
        "purpose": data["purpose"],
        "range": {"start_date": start.isoformat(), "end_date": end.isoformat(), "inclusive": True, "day_count": count},
        "method": method,
        "weights": weights,
        "ranking_summary": ranking,
        "candidates": candidates,
        "pagination": pagination,
        "query_sha256": trace["query_sha256"],
        "ignored_condition_count": len(data["ignored_conditions"]),
    }, summaries


def project_window(root: dict) -> dict:
    try:
        verify(root, "p8-window-search-v1")
        data, summaries = window_data(root)
        return {
            "format": "frontend-tool-sample-v1",
            "tool": "window_search",
            "document_id": root["document_id"],
            "data": data,
            "evidence": evidence(root, summaries),
            "effects": {"model_calls": 0, "writes": 0, "alias_registry": "ephemeral_only"},
            "limits": LIMITS + ["仅北京时间正午快照，不提供精确吉时。", "分数是公开权重的项目排序，不是成功概率。"],
        }
    except INVALID_SOURCE:
        raise ValueError("tool_public_projection_invalid") from None
