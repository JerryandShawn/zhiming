"""Independent solar-RA EOT comparison with explicit Moshier flags and no setters."""

from __future__ import annotations

import importlib
from datetime import UTC, datetime, timedelta
from math import floor, isfinite
from typing import Any

SOURCE = "https://www.astro.com/swisseph/swephprg.htm"
SOURCE_CODE = "https://raw.githubusercontent.com/aloistr/swisseph/v2.10.03/sweph.c"
METHOD = "swiss-moshier-apparent-solar-ra-and-sidereal-time-v1"


def reference_solar_coordinate(utc: datetime, longitude: float) -> dict[str, Any]:
    """Called in the existing isolated Charts worker; never reset Swiss state."""
    if utc.tzinfo is None or utc.utcoffset() is None:
        raise ValueError("均时差旁证需要明确UTC瞬间")
    utc = utc.astimezone(UTC)
    if not 1901 <= utc.year <= 2099:
        raise ValueError("均时差旁证范围为1901至2099年")
    if (
        isinstance(longitude, bool)
        or not isinstance(longitude, (int, float))
        or not isfinite(longitude)
    ):
        raise ValueError("均时差旁证需要有效经度")
    if not -180 <= longitude <= 180:
        raise ValueError("均时差旁证需要有效经度")
    swe = importlib.import_module("swisseph")
    seconds = utc.second + utc.microsecond / 1e6
    _, jd_ut1 = swe.utc_to_jd(
        utc.year, utc.month, utc.day, utc.hour, utc.minute, seconds, swe.GREG_CAL
    )
    jd_label = swe.julday(
        utc.year, utc.month, utc.day, utc.hour + utc.minute / 60 + seconds / 3600
    )
    position, flags = swe.calc_ut(jd_ut1, swe.SUN, swe.FLG_MOSEPH | swe.FLG_EQUATORIAL)
    if flags & (swe.FLG_JPLEPH | swe.FLG_SWIEPH | swe.FLG_MOSEPH) != swe.FLG_MOSEPH:
        raise ValueError("均时差旁证未使用显式Moshier历表")
    fraction = jd_ut1 + 0.5 - floor(jd_ut1 + 0.5)
    angle = (swe.sidtime(jd_ut1) * 15 - fraction * 360 - position[0]) % 360 - 180
    eot = angle * 4
    dut1_seconds = (jd_ut1 - jd_label) * 86400
    coordinate = utc.replace(tzinfo=None) + timedelta(
        minutes=4 * longitude + eot, seconds=dut1_seconds
    )
    return {
        "method": METHOD,
        "coordinate_datetime": coordinate.isoformat(),
        "eot_minutes": eot,
        "inferred_UT1_minus_UTC_seconds": dut1_seconds,
        "sun_flags": int(flags),
        "swisseph_version": str(swe.version),
        "source": SOURCE,
        "source_code": SOURCE_CODE,
        "limits": [
            "Swiss模型推算UT1，不是IERS观测；1972年前UTC输入按库文档处理为UT1。",
            "与NOAA不同的均时差实现；四柱仍使用同一lunar-python引擎，不是独立四柱验证。",
            "仅供已有隔离Charts工作进程；不调用close、set_ephe_path、set_tid_acc或其他配置setter。",
        ],
    }
