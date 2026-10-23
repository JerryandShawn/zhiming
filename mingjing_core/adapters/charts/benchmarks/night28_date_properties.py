"""Seeded calendar properties: independent arithmetic and explicitly shared data."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from ..almanac import almanac
from ..boundary_alerts import boundary_alerts
from ..time_basis import time_basis_candidates
from ..tool_evidence import content_hash
from .night28_date_cases import corpus, dst_anchors
from .night28_property_common import alias_checks
from .night28_ziwei_reference import day_ganzhi

BRANCHES, STEMS = "子丑寅卯辰巳午未申酉戌亥", "甲乙丙丁戊己庚辛壬癸"


def _pillars(candidate: dict) -> bool:
    coordinate = datetime.fromisoformat(candidate["coordinate_datetime"])
    day = coordinate.date() + timedelta(days=int(coordinate.hour == 23))
    ganzhi = day_ganzhi(day)
    hour_index = ((coordinate.hour + 1) // 2) % 12
    hour = STEMS[(STEMS.index(ganzhi[0]) * 2 + hour_index) % 10] + BRANCHES[hour_index]
    return (
        candidate["pillars"]["day"] == ganzhi and candidate["pillars"]["hour"] == hour
    )


def _coordinate_checks(variants: list[dict]) -> dict[str, bool]:
    by_utc, solar_ok = {}, True
    for value in variants:
        pillars = value["pillars"]
        by_utc.setdefault(value["utc"], set()).add((pillars["year"], pillars["month"]))
        if value["basis"] == "true_solar":
            utc = datetime.fromisoformat(
                value["utc"].replace("Z", "+00:00")
            ).astimezone(UTC)
            solar = value["solar_time"]
            expected = utc.replace(tzinfo=None) + timedelta(
                minutes=4 * solar["longitude"] + solar["eot_minutes"]
            )
            solar_ok &= (
                abs(
                    (
                        datetime.fromisoformat(value["coordinate_datetime"]) - expected
                    ).total_seconds()
                )
                <= 1e-6
            )
    return {
        "same_physical_instant_same_year_month": all(
            len(values) == 1 for values in by_utc.values()
        ),
        "independent_day_count_hour_arithmetic": all(
            _pillars(value) for value in variants
        ),
        "no_double_DST_or_longitude_correction": solar_ok,
    }


def _instant_checks(item: dict, result: dict, variants: list[dict]) -> dict[str, bool]:
    valid = [value for value in result["instants"] if value["status"] == "valid"]
    expected = item.get("expected")
    field = "clock" if item["clock_basis"] == "clock" else "standard"
    original = datetime.fromisoformat(item["date"] + "T" + item["time"])
    preserved = all(
        {value["basis"] for value in variants if value["instant_id"] == instant["id"]}
        == {"standard", "true_solar", "beijing_standard"}
        for instant in valid
    )
    return {
        "unique_physical_UTC": len({value["utc"] for value in valid}) == len(valid),
        "reported_clock_roundtrip": all(
            datetime.fromisoformat(value[field]).replace(tzinfo=None) == original
            for value in valid
        ),
        "all_three_declared_bases_preserved": preserved,
        "DST_gap_not_shifted": expected != "nonexistent"
        or (not valid and not variants),
        "DST_fold_both_instants_retained": expected != "ambiguous" or len(valid) == 2,
    }


def _calendar_checks(item: dict, result: dict, engine: Any) -> dict[str, bool]:
    data = result["data"]
    branch = BRANCHES.index(data["ganzhi"]["day"][1])
    checks = {
        "almanac_opposite_branch_plus_six": data["chong_sha"]["branch"]
        == BRANCHES[(branch + 6) % 12],
        "almanac_sha_direction_by_branch_group": data["chong_sha"]["sha_direction"]
        == "南东北西"[branch % 4],
        "almanac_day_counter": data["ganzhi"]["day"]
        == day_ganzhi(datetime.fromisoformat(item["date"]).date()),
        "almanac_real_alias_values": alias_checks(result),
    }
    if item["category"] == "leap_month":
        lunar = data["lunar"]
        checks["shared_library_leap_month_roundtrip"] = [
            lunar["year"],
            lunar["month"],
            lunar["day"],
        ] == item["lunar_anchor"]
    if item["category"] == "jie":
        boundary, values = datetime.fromisoformat(item["boundary"]), []
        for delta in (-1, 1):
            value = boundary + timedelta(seconds=delta)
            lunar = engine.Solar.fromYmdHms(
                value.year,
                value.month,
                value.day,
                value.hour,
                value.minute,
                value.second,
            ).getLunar()
            values.append(lunar.getMonthInGanZhiExact())
        checks["shared_library_Jie_month_changes_across_one_second"] = (
            values[0] != values[1]
        )
    return checks


def _expected_kinds(candidate: dict) -> set[str]:
    coordinate = datetime.fromisoformat(candidate["coordinate_datetime"])
    seconds = (
        coordinate.hour * 3600
        + coordinate.minute * 60
        + coordinate.second
        + coordinate.microsecond / 1e6
    )

    def near(boundary: int) -> bool:
        return abs((seconds - boundary + 43200) % 86400 - 43200) <= 900

    expected = set()
    if any(near(hour * 3600) for hour in range(1, 24, 2)):
        expected.add("hour_branch")
    if near(23 * 3600):
        expected.add("late_zi_day")
    if near(0):
        expected.add("zi_midnight")
    if candidate["jie_uncertainty"]["distance_seconds"] <= 7200:
        expected.add("jie_month")
    return expected


def _boundary_checks(result: dict) -> dict[str, bool]:
    alerts = boundary_alerts(result)
    covered = True
    for group in result["items"]:
        for value in group["source_variants"]:
            if value["basis"] != "true_solar":
                continue
            actual = {
                row["boundary_kind"]
                for row in alerts
                if row["instant_id"] == value["instant_id"]
            }
            covered &= actual - {"eot_implementations"} == _expected_kinds(value)
    return {
        "independent_boundary_band_arithmetic_no_missing_or_extra_alert": covered,
        "boundary_alerts_critical_and_sourced": all(
            value["critical"] and value["source"] and value["school"]
            for value in alerts
        ),
        "boundary_threshold_inclusive_no_outside_hit": all(
            value["threshold_seconds"] is None
            or value["distance_seconds"] <= value["threshold_seconds"]
            for value in alerts
        ),
        "EOT_difference_has_actual_different_pillars": all(
            value["current_pillars"] != value["alternatives"][0]["pillars"]
            for value in alerts
            if value["boundary_kind"] == "eot_implementations"
        ),
    }


def evaluate(engine: Any, inputs: list[dict]) -> dict:
    checks_run, passed, failures, statuses = Counter(), Counter(), [], Counter()
    for index, item in enumerate(inputs):
        try:
            result = time_basis_candidates(
                item["date"],
                item["time"],
                {"tz": "Asia/Shanghai", "lon": item["longitude"]},
                item["clock_basis"],
                include_beijing=True,
            )
            variants = [
                value for group in result["items"] for value in group["source_variants"]
            ]
            checks = {
                **_instant_checks(item, result, variants),
                **_coordinate_checks(variants),
                **_calendar_checks(item, almanac(item["date"]), engine),
                **_boundary_checks(result),
            }
            statuses.update(value["status"] for value in result["instants"])
        except Exception as error:
            checks = {"calculation_completed": False}
            failures.append(
                {
                    "index": index,
                    "category": item["category"],
                    "case_sha256": content_hash(item),
                    "exception_type": type(error).__name__,
                }
            )
        for name, correct in checks.items():
            checks_run[name] += 1
            passed[name] += bool(correct)
        if not all(checks.values()) and not any(
            row["index"] == index for row in failures
        ):
            failures.append(
                {
                    "index": index,
                    "category": item["category"],
                    "case_sha256": content_hash(item),
                    "failed_checks": [
                        name for name, correct in checks.items() if not correct
                    ],
                }
            )
    return {
        "cases": len(inputs),
        "categories": dict(Counter(value["category"] for value in inputs)),
        "unique_reported_dates": len({value["date"] for value in inputs}),
        "manifest_sha256": content_hash(inputs),
        "checks_run": dict(checks_run),
        "checks_passed": dict(passed),
        "instant_statuses": dict(statuses),
        "failure_count": len(failures),
        "failures": failures,
    }


def run_random(count: int) -> dict:
    from ..worker import load_engine

    engine = load_engine("bazi")
    random_cases = corpus(engine, count)
    anchor = (
        engine.Solar.fromYmdHms(2000, 1, 7, 12, 0, 0).getLunar().getDayInGanZhiExact()
    )
    if anchor != "甲子":
        raise ValueError("date_properties_shared_anchor_not_confirmed")
    return {
        "random_unique_dates": evaluate(engine, random_cases),
        "additional_DST_anchors": evaluate(engine, dst_anchors()),
        "day_counter_anchor": {
            "date": "2000-01-07",
            "ganzhi": "甲子",
            "checked_against": "installed_lunar_python",
        },
    }


def main() -> None:
    from .night28_date_properties_cli import main as run

    run()


if __name__ == "__main__":
    main()
