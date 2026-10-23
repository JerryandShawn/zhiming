"""Every 2026-2027 day uses actual public tools and independent geometry checks."""

from __future__ import annotations

import copy
import os
import time
from collections import Counter
from datetime import date, timedelta

from ..daily_transit import daily_transit_prepared, prepare_natal
from ..tool_evidence import content_hash
from ..window_search import window_search
from .daily_transit_samples import sample_natal
from .night28_date_cases import target_days
from .night28_property_common import alias_checks
from .night28_ziwei_reference import day_ganzhi

PURPOSES = ("签约", "面试", "搬家", "出行", "表白", "开业")
ANGLES = {"合相": 0, "六合": 60, "刑相": 90, "拱相": 120, "冲相": 180}


def _tz(value: str) -> None:
    os.environ["TZ"] = value
    if hasattr(time, "tzset"):
        time.tzset()


def _aspect_checks(data: dict) -> bool:
    astro, expected = data["astro"], set()
    for source, value in astro["transit_planets"].items():
        for target, other in astro["natal_planets"].items():
            difference = abs(value["longitude"] - other["longitude"]) % 360
            separation = min(difference, 360 - difference)
            for name, angle in ANGLES.items():
                if abs(separation - angle) <= astro["orb_limit_degrees"]:
                    expected.add((source, target, name))
    actual = {(row["from"], row["to"], row["aspect"]) for row in astro["aspects"]}
    bounded = all(
        0 <= row["orb_degrees"] <= astro["orb_limit_degrees"]
        for row in astro["aspects"]
    )
    return actual == expected and len(actual) == len(astro["aspects"]) and bounded


def _daily_checks(day: str, result: dict) -> dict[str, bool]:
    data = result["data"]
    return {
        "daily_explicit_Beijing_noon": data["snapshot_at"] == day + "T12:00:00+08:00",
        "daily_explicit_physical_UTC": data["snapshot_at_utc"] == day + "T04:00:00Z",
        "daily_independent_day_count": data["bazi"]["snapshot"]["day"]["ganzhi"]
        == day_ganzhi(date.fromisoformat(day)),
        "daily_real_aliases_and_no_effects": alias_checks(result),
        "daily_independent_aspect_geometry": _aspect_checks(data),
    }


def _window_checks(result: dict) -> dict[str, bool]:
    data = result["data"]
    summary, page = data["ranking_summary"], data["pagination"]
    expected = sorted(summary, key=lambda row: (-row["score"], row["date"]))
    selected = expected[page["offset"] : page["offset"] + page["limit"]]
    counts = all(
        row["score"] == row["positive_sum"] + row["negative_sum"] for row in summary
    )
    score_ok = True
    for candidate in data["candidates"]:
        links = (
            candidate["positive_hits"]
            + candidate["negative_hits"]
            + candidate["neutral_hits"]
        )
        score_ok &= candidate["score"] == sum(
            result["rule_hits"][row["rule_hit_index"]]["contribution"] for row in links
        )
    return {
        "window_full_range_transparent_totals": counts,
        "window_global_score_date_sort": summary == expected,
        "window_page_matches_full_ranking": [
            (row["date"], row["score"]) for row in selected
        ]
        == [(row["date"], row["score"]) for row in data["candidates"]],
        "window_real_aliases_and_no_effects": alias_checks(result),
        "window_page_signed_hits_recompute": score_ok,
        "window_trace_summary_hash": data["trace"]["ranking_summary_sha256"]
        == content_hash(summary),
    }


def _month_window(natal: dict, day: str, purpose: str) -> dict:
    start = date.fromisoformat(day)
    last = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return window_search(
        natal,
        {"start_date": day, "end_date": last.isoformat()},
        purpose,
        offset=7,
        limit=7,
    )


def _record(
    checks: dict, run: Counter, passed: Counter, failures: list, day: str
) -> None:
    for name, correct in checks.items():
        run[name] += 1
        passed[name] += bool(correct)
    if not all(checks.values()):
        failed = [name for name, correct in checks.items() if not correct]
        existing = next((row for row in failures if row["date"] == day), None)
        if existing is not None:
            existing["failed_checks"] = failed
        else:
            failures.append({"date": day, "failed_checks": failed})


def run_annual() -> dict:
    natal, days = sample_natal(), target_days()
    before = copy.deepcopy(natal)
    prepared = prepare_natal(natal, days[0])
    run, passed, failures, purposes = Counter(), Counter(), [], Counter()
    old_tz, monthly = os.environ.get("TZ"), 0
    try:
        for index, day in enumerate(days):
            purpose = PURPOSES[index % len(PURPOSES)]
            purposes[purpose] += 1
            try:
                _tz("UTC")
                daily = daily_transit_prepared(prepared, day)
                _tz("Asia/Tokyo")
                window = window_search(
                    natal, {"start_date": day, "end_date": day}, purpose
                )
                checks = {**_daily_checks(day, daily), **_window_checks(window)}
                checks["daily_and_public_window_same_date_content_across_TZ"] = all(
                    row["daily_document_id"] == daily["document_id"]
                    for row in window["data"]["observations"]
                )
                if day.endswith("-01"):
                    checks.update(
                        {
                            "monthly_" + name: correct
                            for name, correct in _window_checks(
                                _month_window(natal, day, purpose)
                            ).items()
                        }
                    )
                    monthly += 1
            except Exception as error:
                checks = {"actual_calculation_completed": False}
                failures.append({"date": day, "exception_type": type(error).__name__})
            _record(checks, run, passed, failures, day)
    finally:
        if old_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old_tz
        if hasattr(time, "tzset"):
            time.tzset()
    return _annual_report(natal, before, days, monthly, purposes, run, passed, failures)


def _annual_report(
    natal: dict,
    before: dict,
    days: list[str],
    monthly: int,
    purposes: Counter,
    run: Counter,
    passed: Counter,
    failures: list,
) -> dict:
    return {
        "first_date": days[0],
        "last_date": days[-1],
        "daily_dates": len(days),
        "public_window_single_day_queries": len(days),
        "additional_public_monthly_page_queries": monthly,
        "purposes": dict(purposes),
        "checks_run": dict(run),
        "checks_passed": dict(passed),
        "input_unchanged": natal == before,
        "TZ_variants": ["UTC", "Asia/Tokyo"],
        "tzset_available": hasattr(time, "tzset"),
        "failure_count": len(failures) + int(natal != before),
        "failures": failures,
        "limits": [
            "每日实际调用公开window入口；额外每月一次多日分页。daily复用同一本命状态，但每个window调用仍准备一次本命。",
            "相位独立几何核对共用同一历表黄经，不验证天文位置或人生预测。",
            "甲子锚与历法库共源，不能把日差一致性冒充独立历史历法真值。",
        ],
    }
