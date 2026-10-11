"""Isolated chart-interpreter entry point, reusing only the verified pure engines.

The Web interpreter need not install pythonmonkey/Swiss Ephemeris. Engine results
are captured as data, never instructions. No archive, provider or channel is read.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timedelta
import hashlib
import importlib.metadata
import importlib.util
import inspect
import io
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace


ENGINES = Path(__file__).resolve().parents[3] / "hermes"


def load_engine(name):
    spec = importlib.util.spec_from_file_location("mingjing_pure_" + name, ENGINES / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def version(package):
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return "not_installed"


def iztro_provenance():
    dist = importlib.metadata.distribution("py-iztro")
    description = dist.metadata.get("Description", "")
    declared = re.search(r"基于[^\n]{0,40}版本[^\d\n]*(\d+\.\d+\.\d+)", description)
    bundles = {}
    for relative in dist.files or []:
        if str(relative).endswith((".js", ".cjs", ".mjs")):
            path = dist.locate_file(relative)
            if path.is_file():
                bundles[str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"iztro_upstream_declared": declared.group(1) if declared else "not_exposed_by_distribution_metadata",
            "iztro_upstream_version_source": "installed_py_iztro_distribution_description",
            "iztro_bundle_sha256": bundles,
            "upstream_version_independently_verified": False}


def capture(function, args):
    output = io.StringIO()
    with redirect_stdout(output):
        function(SimpleNamespace(**args))
    return json.loads(output.getvalue())


def bazi(args):
    engine = load_engine("bazi")
    data = capture(engine.cmd_chart, args)
    data["hidden_stems"] = {name: list(engine.LunarUtil.ZHI_HIDE_GAN[pillar["zhi"]])
                             for name, pillar in data["pillars"].items()}
    data["ten_gods"] = {name: {"exposed": pillar["shishen_gan"],
                                 "branch_principal": pillar["shishen_zhi"],
                                 "hidden_stems": [{"stem": stem, "ten_god": engine.LunarUtil.SHI_SHEN[data["day_master"] + stem]}
                                                  for stem in data["hidden_stems"][name]]}
                        for name, pillar in data["pillars"].items()}
    # The legacy chart's annual lists use datetime.now(). Only the requested
    # target date belongs in this artifact, so replace those lists explicitly.
    data.pop("liunian", None)
    data.pop("liuyue", None)
    data["day"] = capture(engine.cmd_day, {"date": args["date"]})
    data["target_liuyue"] = engine._liuyue(int(args["date"][:4]))
    data["target_liunian"] = [
        {"year": year, "ganzhi": engine.Solar.fromYmd(year, 6, 1).getLunar().getYearInGanZhi(),
         "sample_at": f"{year:04d}-06-01 00:00:00", "timezone_offset": 8,
         "precision_note": "各年六月一日节年干支样本，不代表公历全年同一干支"}
        for year in range(int(args["date"][:4]) - 2, int(args["date"][:4]) + 8)
    ]
    metadata = {"versions": {"lunar-python": version("lunar-python"), "engine": data["engine_version"]},
                "actual_method": dict(data["method"],
                    derived_features="hidden stems and ten gods from installed LunarUtil tables; structural relations without transformation judgments",
                    natal_day_hour="local_mean_solar_time_without_equation_of_time",
                    natal_day_hour_time=data["corrected_time"],
                    year_month_and_dayun="same_instant_converted_to_UTC+8_jie_table",
                    year_month_calendar_time=(datetime.strptime(args["datetime"], "%Y-%m-%d %H:%M") +
                                              timedelta(hours=8 - args["tz"])).isoformat(),
                    day_snapshot="requested_date_12:00_UTC+8"), "warnings": [], "fallback": []}
    return {"data": data, "metadata": metadata}


def ziwei(args):
    engine = load_engine("ziwei")
    birth = datetime.strptime(args["datetime"], "%Y-%m-%d %H:%M")
    ast, corrected = engine.build(birth, args["lng"], args["gender"], args["tz"])
    data = engine.natal(ast, corrected)
    data["timezone_offset"] = args["tz"]
    h = ast.horoscope(args["date"])
    data["horoscope"] = {"target_date": args["date"], "lunar": h.lunar_date,
                         **{layer: engine.scope(getattr(h, layer))
                            for layer in ("decadal", "yearly", "monthly", "daily")}}
    for level in ("decadal", "yearly", "monthly", "daily"):
        layer = data["horoscope"][level]
        links = []
        for label, name in zip(("禄", "权", "科", "忌"), layer["mutagen"]):
            for p in data["palaces"]:
                if any(star["name"] == name for star in p["major"] + p["minor"]):
                    links.append({"star": name, "mutagen": label, "natal_palace": p["name"],
                                  "palace_index": p["index"],
                                  "scope_palace": layer["palace_names"][p["index"]]})
        layer["mutagen_links"] = links
    # Record actual wrapper defaults. Do not call their unnamed upstream
    # behavior a independently verified traditional school.
    signature = inspect.signature(engine.Astro.by_solar)
    defaults = {name: repr(param.default) for name, param in signature.parameters.items()
                if param.default is not inspect.Parameter.empty}
    metadata = {"versions": {"py-iztro": version("py-iztro"),
                               "pythonmonkey": version("pythonmonkey"),
                               "engine": data["engine_version"],
                               **iztro_provenance()},
                "actual_method": dict(data["method"],
                    by_solar_defaults=defaults,
                    local_time="local_mean_solar_time_without_equation_of_time",
                    leap_month="solar_input_with_installed_by_solar_defaults",
                    horoscope_layers=["decadal", "yearly", "monthly", "daily"]),
                "warnings": ["py-iztro内嵌iztro版本尚未从包元数据独立核验；使用安装版本和源码哈希追踪"],
                "fallback": []}
    return {"data": data, "metadata": metadata}


def astro(args):
    engine = load_engine("astro")
    data = engine.chart(args["datetime"], args["lng"], args["lat"], args["date"], args["tz"], 8)
    utc = datetime.strptime(args["datetime"], "%Y-%m-%d %H:%M") - timedelta(hours=args["tz"])
    jd = engine.julian(utc)
    flags, actual, fallback = {"natal": {}, "transit_snapshot": {}}, set(), []
    transit_jd = engine.julian(datetime.strptime(args["date"], "%Y-%m-%d").replace(hour=12) - timedelta(hours=8))
    for layer, instant in (("natal", jd), ("transit_snapshot", transit_jd)):
        for name, body in engine.BODIES:
            _, returned = engine.swe.calc_ut(instant, body, engine.swe.FLG_MOSEPH | engine.swe.FLG_SPEED)
            flags[layer][name] = returned
            selected = returned & (engine.swe.FLG_JPLEPH | engine.swe.FLG_SWIEPH | engine.swe.FLG_MOSEPH)
            method = {engine.swe.FLG_JPLEPH: "JPL", engine.swe.FLG_SWIEPH: "Swiss Ephemeris",
                      engine.swe.FLG_MOSEPH: "Moshier"}.get(selected, "unrecognized_ephemeris_flags")
            actual.add(method)
            if method != "Moshier":
                fallback.append({"body": name, "layer": layer, "requested": "Moshier", "actual": method,
                                 "returned_flags": returned})
    data["calculation_flags"] = flags
    data["transits"]["calculation_flags"] = flags["transit_snapshot"]
    method = dict(data["method"], ephemeris=sorted(actual), houses="Placidus",
                  returned_flags=flags, requested_flags=engine.swe.FLG_MOSEPH | engine.swe.FLG_SPEED,
                  input_time="civil_minus_explicit_offset_to_UTC",
                  delta_t="calc_ut converts UT internally; civil UTC used as UT approximation",
                  transit_target="requested_date_12:00_UTC+8_snapshot",
                  ephemeris_files="Moshier requested explicitly; no Swiss data-file fallback presumed")
    data["method"] = method
    engine_version = getattr(engine.swe, "version", "not_exposed")
    if isinstance(engine_version, bytes):
        engine_version = engine_version.decode("utf-8", errors="replace")
    metadata = {"versions": {"pyswisseph": version("pyswisseph"),
                               "swisseph": str(engine_version), "engine": data["engine_version"]},
                "actual_method": method, "fallback": fallback,
                "warnings": ["Swiss Ephemeris及pyswisseph许可条款须在公开部署前审查；计算成功不代表许可核验已完成"]}
    return {"data": data, "metadata": metadata}


def main():
    request = json.load(sys.stdin)
    system = request.get("system")
    if system not in ("bazi", "ziwei", "astro"):
        raise ValueError("unsupported calculation system")
    # whitelist named arguments; they are data passed to pure functions.
    args = {key: request["args"][key] for key in ("datetime", "lng", "tz", "date", "gender", "lat")
            if key in request["args"]}
    result = globals()[system](args)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
