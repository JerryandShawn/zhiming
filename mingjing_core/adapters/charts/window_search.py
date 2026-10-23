"""Six-purpose transparent date ranking from actual three-system daily calculations."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
from datetime import date, timedelta
from pathlib import Path

from .tool_evidence import content_hash, evidence_result
from .window_search_pagination import paginate, validate_page
from .window_search_scoring import score_day

VERSION = "p8-window-search-v1"
WEIGHTS = Path(__file__).resolve().parents[2] / "knowledge/p8_windows_v1.json"
SCOPE_KEYS = ("owner_user_id", "subject_id", "revision", "operation_id")


def _weights() -> dict:
    return json.loads(WEIGHTS.read_text(encoding="utf-8"))


def _day(value: object) -> date:
    if not isinstance(value, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
        raise ValueError("window_date_invalid")
    try:
        day = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("window_date_invalid") from error
    if not 1901 <= day.year <= 2099:
        raise ValueError("window_date_invalid")
    return day


def _days(date_range: dict) -> list[str]:
    if not isinstance(date_range, dict) or set(date_range) != {
        "start_date",
        "end_date",
    }:
        raise ValueError("window_range_invalid")
    start, end = _day(date_range["start_date"]), _day(date_range["end_date"])
    length = (end - start).days + 1
    if length <= 0:
        raise ValueError("window_range_invalid")
    if length > 366:
        raise ValueError("window_range_too_large")
    return [(start + timedelta(days=index)).isoformat() for index in range(length)]


def _scope(natal: dict) -> dict:
    if not isinstance(natal, dict):
        raise ValueError("window_natal_scope_invalid")
    for key in ("owner_user_id", "subject_id", "operation_id"):
        if not isinstance(natal.get(key), str) or not natal[key].strip():
            raise ValueError("window_natal_scope_invalid")
    if type(natal.get("revision")) is not int or natal["revision"] < 0:
        raise ValueError("window_natal_scope_invalid")
    return {key: natal[key] for key in SCOPE_KEYS}


def _validate_daily(daily: dict, day: str, scope: dict) -> None:
    actual_scope = daily.get("scope")
    if (
        not isinstance(actual_scope, dict)
        or set(actual_scope) != set(scope)
        or any(
            type(actual_scope[key]) is not type(value) or actual_scope[key] != value
            for key, value in scope.items()
        )
    ):
        raise ValueError("window_daily_scope_mismatch")
    if daily.get("data", {}).get("date") != day:
        raise ValueError("window_daily_date_mismatch")
    root = {
        key: daily.get(key)
        for key in ("version", "scope", "data", "rule_hits", "sources")
    }
    if daily.get("document_id") != "tool-" + content_hash(root):
        raise ValueError("window_daily_evidence_invalid")


def _daily_results(natal: dict, days: list[str]) -> Iterator[dict]:
    from .daily_transit import daily_transit_prepared, prepare_natal

    prepared = prepare_natal(natal, days[0])
    for day in days:
        yield daily_transit_prepared(prepared, day, orb_degrees=2.0)


def _data(days: list[str], purpose: str, weights: dict) -> dict:
    return {
        "purpose": purpose,
        "range": {
            "start_date": days[0],
            "end_date": days[-1],
            "inclusive": True,
            "day_count": len(days),
        },
        "method": {
            "ranking": "score_descending_then_date_ascending",
            "weights_version": weights["version"],
            "sample_clock": "12:00:00+08:00",
            "daily_orb_degrees": 2.0,
            "election_hours_searched": False,
            "prediction_validated": False,
        },
        "candidates": [],
        "observations": [],
        "ignored_conditions": [],
        "weights": weights,
    }


def _score_results(
    natal: dict,
    days: list[str],
    purpose: str,
    results: Iterable[dict],
    *,
    offset: int = 0,
    limit: int = 31,
) -> dict:
    validate_page(offset, limit)
    weights, scope = _weights(), _scope(natal)
    data, hits, sources = _data(days, purpose, weights), [], []
    for day, daily in zip(days, results, strict=True):
        _validate_daily(daily, day, scope)
        data["candidates"].append(score_day(daily, purpose, weights, data, hits))
        for source in daily["sources"]:
            if source not in sources:
                sources.append(source)
    data["candidates"].sort(key=lambda row: (-row["score"], row["date"]))
    for rank, row in enumerate(data["candidates"], 1):
        row["rank"] = rank
    hits = paginate(data, hits, natal, offset, limit)
    sources.append(
        {
            "school": weights["school"],
            "source": weights["source"],
            "version": weights["version"],
        }
    )
    result = evidence_result(VERSION, data, hits, sources, scope)
    result["limits"] += [
        "这是公开权重的项目排序，不是经过验证的传统择日定论或现实结果概率。",
        "仅每日北京时间正午快照，没有搜索全天时辰，不给精确吉时。",
        "优先核对现实日程、对方同意和出行条件；正负分不对应事故或成功断言。",
    ]
    return result


def window_search(
    natal: dict, date_range: dict, purpose: str, *, offset: int = 0, limit: int = 31
) -> dict:
    """Calculate all inclusive candidate dates, reusing one prepared natal chart."""
    weights = _weights()
    if not isinstance(purpose, str) or purpose not in weights["purpose_weights"]:
        raise ValueError("window_purpose_invalid")
    days = _days(date_range)
    validate_page(offset, limit)
    _scope(natal)
    return _score_results(
        natal, days, purpose, _daily_results(natal, days), offset=offset, limit=limit
    )
