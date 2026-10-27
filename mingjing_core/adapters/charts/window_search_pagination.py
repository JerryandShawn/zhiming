"""Explicit bounded pages, with full-range ranking totals and page-local evidence."""

from __future__ import annotations

from copy import deepcopy

from .tool_evidence import content_hash


def validate_page(offset: int, limit: int) -> None:
    if type(offset) is not int or offset < 0:
        raise ValueError("window_offset_invalid")
    if type(limit) is not int or not 1 <= limit <= 31:
        raise ValueError("window_limit_invalid")


def _summary(candidates: list[dict]) -> list[dict]:
    return [
        {
            "date": row["date"],
            "rank": row["rank"],
            "score": row["score"],
            "positive_sum": sum(hit["contribution"] for hit in row["positive_hits"]),
            "negative_sum": sum(hit["contribution"] for hit in row["negative_hits"]),
        }
        for row in candidates
    ]


def _page_hits(data: dict, hits: list[dict], candidates: list[dict]) -> list[dict]:
    groups = ("positive_hits", "negative_hits", "neutral_hits")
    selected = sorted(
        {
            link["rule_hit_index"]
            for row in candidates
            for group in groups
            for link in row[group]
        }
    )
    indices = {old: index for index, old in enumerate(selected)}
    observations, page_hits = [], []
    for old in selected:
        hit = deepcopy(hits[old])
        path = hit["evidence_paths"][0]
        source_index = int(path.rsplit("/", 1)[1])
        observations.append(data["observations"][source_index])
        hit["evidence_paths"][0] = f"/data/observations/{len(observations) - 1}"
        page_hits.append(hit)
    for row in candidates:
        for group in groups:
            for link in row[group]:
                link["rule_hit_index"] = indices[link["rule_hit_index"]]
    data["observations"] = observations
    return page_hits


def paginate(
    data: dict, hits: list[dict], natal: dict, offset: int, limit: int
) -> list[dict]:
    validate_page(offset, limit)
    total = len(data["candidates"])
    data["ranking_summary"] = _summary(data["candidates"])
    data["candidates"] = deepcopy(data["candidates"][offset : offset + limit])
    returned = len(data["candidates"])
    more = offset + returned < total
    data["pagination"] = {
        "total": total,
        "offset": offset,
        "limit": limit,
        "returned": returned,
        "has_more": more,
        "next_offset": offset + returned if more else None,
    }
    data["trace"] = {
        "kind": "query_and_ranking_trace_not_a_directional_rule_hit",
        "query_sha256": content_hash(
            [natal, data["range"], data["purpose"], data["weights"]]
        ),
        "ranking_summary_sha256": content_hash(data["ranking_summary"]),
        "weights_sha256": content_hash(data["weights"]),
        "school": data["weights"]["school"],
        "source": data["weights"]["source"],
    }
    return _page_hits(data, hits, data["candidates"])
