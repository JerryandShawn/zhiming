"""Direct secondary progressions: a declared day-for-tropical-year convention."""

from __future__ import annotations

from typing import Any

from .astro_ephemeris import SWISS_SOURCE, Ephemeris, actual_utc, aspects, finite, iso

TROPICAL_YEAR_DAYS = 365.2422
METHOD = "secondary-direct-UT1-day-per-365.2422-UT1-days-v1"


def secondary_progressions(birth_at: str, target_at: str, *, orb: float = 1) -> dict[str, Any]:
    """Map elapsed UT1 days to symbolic ephemeris days, without invented houses."""
    birth, target = actual_utc(birth_at), actual_utc(target_at)
    finite(orb, 0, 10)
    engine = Ephemeris()
    birth_tt, birth_ut = engine.julian(birth)
    target_tt, target_ut = engine.julian(target)
    age = (target_ut - birth_ut) / TROPICAL_YEAR_DAYS
    if not 0 <= age <= 150:
        raise ValueError("次限目标须在出生至150热带年之内")
    progressed_ut = birth_ut + age
    progressed_at = engine.from_ut(progressed_ut)
    progressed_tt, _ = engine.julian(progressed_at)
    natal, progressed = engine.planets(birth_ut), engine.planets(progressed_ut)
    return {
        "version": "p8-secondary-progressions-v1",
        "method": METHOD,
        "actual_UTC": {"birth_at": iso(birth), "target_at": iso(target)},
        "symbolic_ephemeris_at_UTC": iso(progressed_at),
        "mapping": {
            "year_length_days": TROPICAL_YEAR_DAYS,
            "age_in_tropical_years": age,
            "formula": "progressed_JD_UT1 = birth_JD_UT1 + (target_JD_UT1-birth_JD_UT1)/365.2422",
            "birth_jd_ut1": birth_ut,
            "target_jd_ut1": target_ut,
            "progressed_jd_ut1": progressed_ut,
            "birth_jd_tt": birth_tt,
            "target_jd_tt": target_tt,
            "progressed_jd_tt": progressed_tt,
        },
        "natal_planets": natal,
        "progressed_planets": progressed,
        "aspect_orb_degrees": float(orb),
        "aspects_to_natal": aspects(progressed, natal, orb),
        "progressed_aspects": aspects(progressed, None, orb),
        "houses": None,
        "metadata": engine.metadata(),
        "reference_sources": [SWISS_SOURCE, "https://www.astro.com/faq/fq_fh_owtype_e.htm"],
        "limits": [
            "一历表日对应365.2422个UT1日是本项目具名口径；不是按生日整岁取整，不声称各软件同法。",
            "只做顺行次限（日返一年）；不混入逆行次限、太阳弧、主限或未定义的推运宫位算法。",
            "symbolic_ephemeris_at_UTC是取历表的位置时刻，不是目标日期真实天空；无人生预测效度证明。",
            "西占始终从实际UTC计算，不套用真太阳时；本命时区不确定须另行分支计算。",
        ],
    }
