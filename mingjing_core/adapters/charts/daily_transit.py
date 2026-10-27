"""Read-only three-system daily snapshot with local, content-bound evidence."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .astro_ephemeris import finite
from .daily_transit_astro import ASTRO_SOURCE, astro_day, astro_hits
from .daily_transit_bazi import TEN_SOURCE, bazi_day, bazi_hits
from .daily_transit_natal import (
    SCOPE_KEYS,
    PreparedNatal,
    prepare_natal,
    snapshot,
    utc_string,
)
from .daily_transit_ziwei import ZIWEI_SOURCE, ziwei_day, ziwei_hits
from .tool_evidence import evidence_result


def daily_transit_prepared(
    prepared: PreparedNatal, date: str, *, orb_degrees: float = 2.0
) -> dict[str, Any]:
    moment = snapshot(date, prepared.request["birth"]["date"])
    finite(orb_degrees, 0, 10)
    bazi = bazi_day(prepared, date)
    ziwei = ziwei_day(prepared, date)
    astro = astro_day(prepared, date, orb_degrees)
    data = {
        "date": date,
        "snapshot_at": moment.isoformat(),
        "snapshot_at_utc": utc_string(moment),
        "time_basis": {
            "primary": prepared.candidate,
            "comparisons": prepared.basis_comparisons,
        },
        "bazi": bazi,
        "ziwei": ziwei,
        "astro": astro,
    }
    hits = bazi_hits(bazi) + ziwei_hits(ziwei) + astro_hits(astro)
    result = evidence_result(
        "p8-daily-transit-v1",
        data,
        hits,
        [TEN_SOURCE, ZIWEI_SOURCE, ASTRO_SOURCE],
        {key: prepared.request[key] for key in SCOPE_KEYS},
    )
    result["limits"].extend(
        [
            "目标为明确日期北京时间12:00快照，不是全天应期或择时结论。",
            "本命真太阳主口径；北京时间四柱或紫微盘不同时并列，不改变已确认出生资料。",
        ]
    )
    return result


def daily_transit(
    natal: dict[str, Any], date: str, *, orb_degrees: float = 2.0
) -> dict[str, Any]:
    finite(orb_degrees, 0, 10)
    prepared = prepare_natal(deepcopy(natal), date)
    return daily_transit_prepared(prepared, date, orb_degrees=orb_degrees)


__all__ = ["PreparedNatal", "prepare_natal", "daily_transit", "daily_transit_prepared"]
