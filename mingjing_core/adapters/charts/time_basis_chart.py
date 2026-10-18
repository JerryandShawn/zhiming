"""Charts for already resolved coordinates; never apply the longitude twice."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ...calculations.bazi.calendar_layers import decade_luck, iso, solar_at
from .named_bazi import hidden_for, named_command, named_supplement, options, replace_layer_hidden
from .p8_analysis import attach_analysis
from .worker import iztro_provenance, load_engine, version


def bazi_context(candidate: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    engine = load_engine("bazi")
    physical = datetime.fromisoformat(candidate["calendar_datetime"])
    pillars = candidate["pillars"]
    data = {"pillars": {name: {"ganzhi": value, "gan": value[0], "zhi": value[1]} for name, value in pillars.items()}}
    args = {
        "datetime": physical.strftime("%Y-%m-%d %H:%M"),
        "tz": 8,
        "lng": 120,
        "gender": request["birth"]["gender"],
        "date": request["as_of_date"],
        "p8_options": request.get("p8_options"),
    }
    data["p8"] = named_supplement(engine, args, data)
    p8, lunar = data["p8"], solar_at(engine, physical).getLunar()
    previous = lunar.getPrevJie()
    following = lunar.getNextJie()
    elapsed = (physical - datetime.fromisoformat(previous.getSolar().toYmdHms())).total_seconds() / 86400
    p8["month_command"] = named_command(pillars["month"][1], elapsed, pillars["day"][0], options(args["p8_options"]))
    p8["month_command"].update(
        calendar_birth_at=physical.isoformat() + "+08:00",
        exact_seconds_preserved=True,
        period_start=iso(previous.getSolar()),
        period_end_exclusive=iso(following.getSolar()),
        start_jie=previous.getName(),
    )
    p8["decade_luck"] = decade_luck(engine, physical, int(args["gender"] == "男"), pillars)
    replace_layer_hidden(p8["decade_luck"], hidden_for(options(args["p8_options"])), pillars["day"][0])
    p8["time_basis_method"] = {
        "year_month_and_yun": "physical_UTC_plus8",
        "day_hour": candidate["pillar_method"],
        "not_birth_coordinates": "internal UTC+8 meridian only, no second longitude conversion",
    }
    attach_analysis(data)
    return data


def ziwei_column(candidate: dict[str, Any], gender: str) -> dict[str, Any]:
    from .ziwei_flying import palace_flying_transformations

    engine = load_engine("ziwei")
    coordinate = datetime.fromisoformat(candidate["coordinate_datetime"])
    ast, corrected = engine.build(coordinate, 0, gender, 0)
    result = engine.natal(ast, corrected)
    result["time_basis"] = candidate["basis"]
    result["method"].update(
        input="preconverted_declared_coordinate_no_second_longitude_or_DST_adjustment",
        equation_of_time_applied=candidate["basis"] == "true_solar",
        day_boundary="py-iztro late-Zi index12 default; distinct from Bazi sect1",
    )
    result["versions"] = {
        "py-iztro": version("py-iztro"),
        "pythonmonkey": version("pythonmonkey"),
        **iztro_provenance(),
    }
    result["p8_flying_transformations"] = palace_flying_transformations(result)
    return result
