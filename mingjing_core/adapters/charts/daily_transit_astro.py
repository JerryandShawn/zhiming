"""One explicit UTC snapshot, major longitude aspects and a declared orb."""

from __future__ import annotations

from typing import Any

from .astro_ephemeris import SWISS_SOURCE, aspects, finite
from .daily_transit_natal import PreparedNatal, snapshot, utc_string

ASTRO_SOURCE = {
    "title": "Swiss Ephemeris Moshier + 项目五大黄经相位统一容许度",
    "url": SWISS_SOURCE,
    "status": "numerical_geometry_with_project_orb_not_predictive_validation",
}


def astro_day(prepared: PreparedNatal, day: str, orb_degrees: float) -> dict[str, Any]:
    limit = finite(orb_degrees, 0, 10)
    moment = snapshot(day, prepared.request["birth"]["date"])
    _, jd = prepared.ephemeris.julian(moment)
    transits = prepared.ephemeris.planets(jd)
    return {
        "natal_at_utc": prepared.candidate["utc"],
        "snapshot_at_utc": utc_string(moment),
        "natal_planets": prepared.natal_planets,
        "transit_planets": transits,
        "orb_limit_degrees": limit,
        "aspects": aspects(transits, prepared.natal_planets, limit),
        "method": prepared.ephemeris.metadata(),
        "limits": [
            "北京时间正午单点快照，不代表全天进入/离开区间，也不计算当前地宫位。",
            "几何相位不判断事件吉凶或概率，不改变原v3历表口径。",
        ],
    }


def astro_hits(data: dict[str, Any]) -> list[dict[str, Any]]:
    hits = []
    for index, row in enumerate(data["aspects"]):
        hits.append(
            {
                "rule_id": f"daily.astro.aspect.{index}",
                "met": True,
                "school": "geocentric-tropical-major-longitude-aspects-project-v1",
                "source": ASTRO_SOURCE,
                "context": {
                    "system": "astro",
                    "kind": "aspect",
                    **{
                        key: row[key] for key in ("from", "to", "aspect", "orb_degrees")
                    },
                    "orb_limit": data["orb_limit_degrees"],
                },
                "evidence_paths": [
                    f"/data/astro/aspects/{index}",
                    f"/data/astro/transit_planets/{row['from']}/longitude",
                    f"/data/astro/natal_planets/{row['to']}/longitude",
                    "/data/astro/orb_limit_degrees",
                ],
            }
        )
    return hits
