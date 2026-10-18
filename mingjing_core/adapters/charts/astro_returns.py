"""Tropical solar return roots and explicit-location Placidus houses."""

from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timedelta
from math import isfinite
from typing import Any

from .astro_ephemeris import (
    SWISS_SOURCE,
    Ephemeris,
    actual_utc,
    aspects,
    finite,
    iso,
    signed_angle,
)

ROOT_SECONDS = 0.02


def _find_return(engine: Ephemeris, natal: float, anchor: datetime) -> tuple[float, float]:
    left = engine.julian(anchor - timedelta(days=5))[1]
    end = engine.julian(anchor + timedelta(days=5))[1]
    found = []

    def error(jd: float) -> float:
        return signed_angle(engine.position("太阳", jd)["longitude"], natal)

    while left < end:
        right = min(left + 1, end)
        segment_end = right
        a, b = error(left), error(right)
        if a == 0:
            found.append((left, 0.0))
        if a < 0 <= b and max(abs(a), abs(b)) < 90:
            while (right - left) * 86400 > ROOT_SECONDS:
                middle = (left + right) / 2
                if error(middle) >= 0:
                    right = middle
                else:
                    left = middle
            root = (left + right) / 2
            found.append((root, (right - left) * 86400))
        left = segment_end
    unique = []
    for root in found:
        if not unique or abs(root[0] - unique[-1][0]) * 86400 > ROOT_SECONDS:
            unique.append(root)
    if len(unique) != 1:
        raise ValueError("周年锚点前后5日内未找到唯一太阳回归根")
    return unique[0]


def _house_of(longitude: float, cusps: tuple[float, ...]) -> int:
    for index, start in enumerate(cusps):
        if (longitude - start) % 360 < (cusps[(index + 1) % 12] - start) % 360:
            return index + 1
    raise ValueError("太阳回归宫位区间不能覆盖行星黄经")


def _houses(engine: Ephemeris, jd_ut: float, longitude: float, latitude: float) -> dict[str, Any]:
    try:
        cusps, angles = engine.swe.houses_ex(jd_ut, latitude, longitude, b"P", 0)
    except engine.swe.Error as exc:
        raise ValueError("此时地Placidus宫制计算失败；不自动更换宫制") from exc
    if len(cusps) != 12 or len(angles) < 2 or not all(isfinite(x) for x in (*cusps, *angles)):
        raise ValueError("Placidus返回不完整或非有限宫位")
    return {
        "system": "Placidus",
        "location": {"longitude": longitude, "latitude": latitude},
        "cusps": [{"house": i + 1, "longitude": value} for i, value in enumerate(cusps)],
        "ascendant": angles[0],
        "midheaven": angles[1],
        "armc": angles[2],
        "assignment": "geocentric ecliptic longitude inside consecutive cusp intervals; no latitude correction",
    }


def solar_return(
    birth_at: str,
    return_year: int,
    *,
    longitude: float,
    latitude: float,
    orb: float = 6,
) -> dict[str, Any]:
    """Find the sole return within five days of the UTC-birthday anniversary."""
    birth = actual_utc(birth_at)
    if type(return_year) is not int or not birth.year <= return_year <= min(2398, birth.year + 150):
        raise ValueError("太阳回归年份须为出生年起150年内的整数且不晚于2398年")
    lon, lat, limit = finite(longitude, -180, 180), finite(latitude, -89.999, 89.999), finite(orb, 0, 10)
    engine = Ephemeris()
    birth_tt, birth_ut = engine.julian(birth)
    natal = engine.position("太阳", birth_ut)["longitude"]
    day = min(birth.day, monthrange(return_year, birth.month)[1])
    anchor = birth.replace(year=return_year, day=day)
    root, bracket = _find_return(engine, natal, anchor)
    if return_year == birth.year:
        root, bracket = birth_ut, 0.0
    if root < birth_ut - ROOT_SECONDS / 86400:
        raise ValueError("太阳回归时刻不能早于出生")
    returned = engine.from_ut(root)
    return_tt, _ = engine.julian(returned)
    houses, planets = _houses(engine, root, lon, lat), engine.planets(root)
    cusps = tuple(row["longitude"] for row in houses["cusps"])
    for position in planets.values():
        position["house"] = _house_of(position["longitude"], cusps)
    return _result(
        engine,
        birth,
        returned,
        return_year,
        natal,
        planets,
        houses,
        limit,
        {
            "bracket_seconds": bracket,
            "requested_bracket_seconds": ROOT_SECONDS,
            "residual_degrees": abs(signed_angle(planets["太阳"]["longitude"], natal)),
            "birth_jd_ut1": birth_ut,
            "birth_jd_tt": birth_tt,
            "return_jd_ut1": root,
            "return_jd_tt": return_tt,
            "anniversary_anchor_at_UTC": iso(anchor),
            "leap_day_anchor_clamped": birth.day != day,
            "crossed_anniversary_year_boundary": returned.year != return_year,
        },
    )


def _result(
    engine: Ephemeris,
    birth: datetime,
    returned: datetime,
    year: int,
    natal: float,
    planets: dict[str, Any],
    houses: dict[str, Any],
    orb: float,
    root: dict[str, Any],
) -> dict[str, Any]:
    return {
        "version": "p8-solar-return-v1",
        "method": "tropical-apparent-longitude-return-UTC-anniversary-Placidus-v1",
        "actual_UTC": {"birth_at": iso(birth), "return_at": iso(returned)},
        "return_year": year,
        "year_basis": "UTC birth-month/day/time anniversary +/-5 days; Feb29 anchor clamps to Feb28",
        "natal_sun_longitude": natal,
        "planets": planets,
        "houses": houses,
        "root": root,
        "aspect_orb_degrees": orb,
        "aspects": aspects(planets, None, orb),
        "metadata": engine.metadata(),
        "reference_sources": [SWISS_SOURCE, "https://www.astro.com/faq/fq_fh_return_e.htm"],
        "limits": [
            "返回时刻由太阳热带视黄经相等求根；orb仅控制盘内相位列表，不是回归根容差。",
            "地点须显式传入，不猜出生地/居住地/当时所在地；地点影响宫位，不影响地心回归时刻。",
            "高纬Placidus失败直接报错，不接受Swiss内部回退的其他宫制。",
            "数值括区间不是历表或UTC物理准确度；未来UT1/闰秒模型可能更新；无现实预测效度证明。",
            "使用实际UTC，不套真太阳时；出生时刻有区间须在外部逐分支调用并比较稳定字段。",
        ],
    }
