"""NOAA/Meeus equation of time; explicit standard/mean/apparent solar clocks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import cos, degrees, isfinite, radians, sin, tan
from typing import Any

METHOD = "noaa-meeus-julian-century-equation-of-time-v1"
SOURCE = "https://gml.noaa.gov/grad/solcalc/calcdetails.html"


def equation_of_time(instant: datetime) -> float:
    """Minutes of apparent solar time minus mean solar time at the actual UTC."""
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("均时差计算需要明确UTC瞬间")
    utc = instant.astimezone(UTC)
    if not 1901 <= utc.year <= 2099:
        raise ValueError("当前均时差验证范围为1901至2099年")
    century = (utc.timestamp() / 86400 + 2440587.5 - 2451545) / 36525
    longitude = radians(
        (280.46646 + century * (36000.76983 + century * 0.0003032)) % 360
    )
    anomaly = radians(357.52911 + century * (35999.05029 - 0.0001537 * century))
    eccentricity = 0.016708634 - century * (0.000042037 + 0.0000001267 * century)
    seconds = 21.448 - century * (46.815 + century * (0.00059 - century * 0.001813))
    obliquity = 23 + (26 + seconds / 60) / 60
    obliquity += 0.00256 * cos(radians(125.04 - 1934.136 * century))
    y = tan(radians(obliquity) / 2) ** 2
    expression = (
        y * sin(2 * longitude)
        - 2 * eccentricity * sin(anomaly)
        + 4 * eccentricity * y * sin(anomaly) * cos(2 * longitude)
        - 0.5 * y * y * sin(4 * longitude)
        - 1.25 * eccentricity * eccentricity * sin(2 * anomaly)
    )
    return 4 * degrees(expression)


def solar_time(instant: dict[str, Any], lon: float) -> dict[str, Any]:
    if instant.get("status") != "valid" or not instant.get("utc"):
        raise ValueError("不存在的钟表时刻不能计算太阳时")
    if (
        isinstance(lon, bool)
        or not isinstance(lon, (float, int))
        or not isfinite(lon)
        or not -180 <= lon <= 180
    ):
        raise ValueError("太阳时需要明确有效的东经为正经度")
    utc = datetime.fromisoformat(instant["utc"].replace("Z", "+00:00")).astimezone(UTC)
    offset = instant["standard_offset_minutes"]
    standard = (utc + timedelta(minutes=offset)).replace(tzinfo=None)
    correction = 4 * lon - offset
    mean = standard + timedelta(minutes=correction)
    eot = equation_of_time(utc)
    apparent = mean + timedelta(minutes=eot)
    return {
        "standard": standard.isoformat(),
        "mean_solar": mean.isoformat(),
        "true_solar": apparent.isoformat(),
        "longitude": lon,
        "standard_central_meridian": offset / 4,
        "longitude_correction_minutes": correction,
        "eot_minutes": eot,
        "eot_sign": "apparent_minus_mean",
        "method": METHOD,
        "eot_evaluated_at": instant["utc"],
        "source": SOURCE,
        "limits": [
            "天文公式近似，不将同算法数值对照称为独立实测。",
            "太阳时是时钟坐标，不是另一个UTC瞬间。",
        ],
    }
