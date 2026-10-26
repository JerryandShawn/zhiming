"""Fixed-seed unique synthetic dates, with separately counted DST anchor probes."""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from typing import Any

SEED = 20261020
JIE = (
    "立春",
    "惊蛰",
    "清明",
    "立夏",
    "芒种",
    "小暑",
    "立秋",
    "白露",
    "寒露",
    "立冬",
    "大雪",
    "小寒",
)
DST = (
    ("1986-05-04", "1986-09-14"),
    ("1987-04-12", "1987-09-13"),
    ("1988-04-17", "1988-09-11"),
    ("1989-04-16", "1989-09-17"),
    ("1990-04-15", "1990-09-16"),
    ("1991-04-14", "1991-09-15"),
)


def case(category: str, moment: datetime, rng: random.Random, **extra: Any) -> dict:
    return {
        "category": category,
        "date": moment.date().isoformat(),
        "time": moment.strftime("%H:%M:%S"),
        "longitude": rng.choice((80, 87.625, 104.07, 120, 135)),
        "clock_basis": "clock" if category == "dst" else "standard",
        **extra,
    }


def _leap_pool() -> list[tuple[datetime, list[int]]]:
    from lunar_python import Lunar, LunarYear

    rows = []
    for year in range(1902, 2099):
        for month in LunarYear.fromYear(year).getMonthsInYear():
            if month.getMonth() >= 0:
                continue
            for day in range(1, month.getDayCount() + 1):
                anchor = [year, month.getMonth(), day]
                solar = Lunar.fromYmd(*anchor).getSolar()
                rows.append(
                    (datetime.fromisoformat(solar.toYmd() + "T12:00:00"), anchor)
                )
    return rows


def _jie_pool(engine: Any) -> list[tuple[str, datetime]]:
    rows = []
    for year in range(1980, 2099):
        table = engine.Solar.fromYmdHms(year, 7, 1, 12, 0, 0).getLunar().getJieQiTable()
        rows.extend(
            (name, datetime.fromisoformat(table[name].toYmdHms())) for name in JIE
        )
    return rows


def _draw(category: str, rng: random.Random, leap: list, jie: list) -> dict:
    if category == "dst":
        moment = datetime(1986, 1, 1) + timedelta(
            days=rng.randrange(2191), seconds=rng.randrange(86400)
        )
        return case(category, moment, rng)
    if category == "leap_month":
        moment, anchor = rng.choice(leap)
        return case(category, moment, rng, lunar_anchor=anchor)
    if category == "jie":
        name, boundary = rng.choice(jie)
        delta = rng.choice((-7201, -7200, -1, 0, 1, 7200, 7201))
        return case(
            category,
            boundary + timedelta(seconds=delta),
            rng,
            jie=name,
            boundary=boundary.isoformat(),
            delta_seconds=delta,
        )
    from mingjing_core.adapters.charts.boundary_candidates import coordinate_to_utc

    day = date(1902, 1, 1) + timedelta(
        days=rng.randrange((date(2099, 1, 1) - date(1902, 1, 1)).days)
    )
    coordinate = datetime(day.year, day.month, day.day, rng.choice((0, 23)))
    coordinate += timedelta(seconds=rng.choice((-901, -900, -1, 0, 1, 900, 901)))
    longitude = rng.choice((80, 87.625, 104.07, 120, 135))
    utc = coordinate_to_utc(coordinate, longitude).replace(microsecond=0)
    value = case(category, (utc + timedelta(hours=8)).replace(tzinfo=None), rng)
    value.update(longitude=longitude, nominal_solar_coordinate=coordinate.isoformat())
    return value


def corpus(engine: Any, count: int = 1000) -> list[dict]:
    if type(count) is not int or not 4 <= count <= 1000 or count % 4:
        raise ValueError("date_properties_count_must_be_divisible_by_four")
    rng, seen, output = random.Random(SEED), set(), []
    leap, jie = _leap_pool(), _jie_pool(engine)
    for category in ("dst", "leap_month", "jie", "late_zi"):
        admitted = 0
        for _ in range(50000):
            value = _draw(category, rng, leap, jie)
            if value["date"] in seen:
                continue
            seen.add(value["date"])
            output.append(value)
            admitted += 1
            if admitted == count // 4:
                break
        if admitted != count // 4:
            raise ValueError("date_properties_unique_sampling_budget_exceeded")
    return output


def dst_anchors() -> list[dict]:
    rng, rows = random.Random(SEED), []
    for start, end in DST:
        rows += [
            case(
                "dst",
                datetime.fromisoformat(start + "T02:30"),
                rng,
                expected="nonexistent",
            ),
            case(
                "dst", datetime.fromisoformat(end + "T01:30"), rng, expected="ambiguous"
            ),
        ]
    return rows


def target_days() -> list[str]:
    start, end = date(2026, 1, 1), date(2028, 1, 1)
    return [
        (start + timedelta(days=index)).isoformat()
        for index in range((end - start).days)
    ]
