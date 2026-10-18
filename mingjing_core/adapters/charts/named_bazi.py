"""Named P8 schools; the legacy calculator and its hidden table are untouched."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from math import isfinite
from typing import Any

from ...calculations.bazi.calendar_layers import iso, solar_at
from ...calculations.bazi.elements import HIDDEN, block, table, ten_god
from ...calculations.bazi.stars import auxiliary_stars
from ...calculations.bazi.supplement import supplement
from .named_strength import named_patterns, named_scores


def options(value: dict[str, str] | None = None) -> dict[str, str]:
    rules = table("schools")
    given = {} if value is None else dict(value)
    if set(given) - {"command", "tianyi", "blade", "shen_earth"}:
        raise ValueError("不支持的P8口径选项")
    result = dict(rules["defaults"], **given)
    for key, category in (("command", "commands"), ("tianyi", "tianyi"), ("blade", "blade")):
        if result[key] not in rules[category]:
            raise ValueError("未登记的P8具名口径")
    if result.get("shen_earth") not in (None, "戊", "己"):
        raise ValueError("申月合土只能显式选戊或己")
    if result["command"] == "xu_7716" and result.get("shen_earth") not in ("戊", "己"):
        raise ValueError("徐表申月为戊己合土；请显式选择shen_earth=戊或己的项目归一口径")
    return result


def command_rule(selected: dict[str, str]) -> dict[str, Any]:
    rule = deepcopy(table("schools")["commands"][selected["command"]])
    if selected["command"] == "xu_7716":
        rule["schedules"]["申"][0][0] = selected["shen_earth"]
    return rule


def hidden_for(selected: dict[str, str]) -> dict[str, str]:
    return {
        branch: "".join(row[0] for row in reversed(rows))
        for branch, rows in command_rule(selected)["schedules"].items()
    }


def named_command(month: str, elapsed: float, master: str, selected: dict[str, str]) -> dict[str, Any]:
    if isinstance(elapsed, bool) or not isfinite(elapsed) or elapsed < 0:
        raise ValueError("节后经过日数必须为有限非负数")
    rule = command_rule(selected)
    schedule, start = rule["schedules"][month], 0
    index = len(schedule) - 1
    for position, (_, days) in enumerate(schedule):
        if elapsed < start + days:
            index = position
            break
        start += days
    stem = schedule[index][0]
    return block(
        "p8-named-command-v1:" + selected["command"],
        rule["source"],
        name=rule["name"],
        locator=rule["locator"],
        normalization=rule["normalization"],
        month_branch=month,
        elapsed_days=round(elapsed, 9),
        selected_segment=index,
        commanding_stem=stem,
        ten_god=ten_god(master, stem),
        also_in_v3_hidden_stems=stem in HIDDEN[month],
        schedule=[{"stem": item, "days": days} for item, days in schedule],
        elapsed_rule="自前节起连续24小时为一日、半开区间、末段到下节；不拉伸分日表",
        warnings=["具名分日法有异说，不宣称唯一正确；藏干角色为逆段序项目定义"],
    )


def named_ten_gods(pillars: dict[str, str], hidden: dict[str, str], selected: dict[str, str]) -> dict[str, Any]:
    master, rows = pillars["day"][0], {}
    for name, ganzhi in pillars.items():
        stems = hidden[ganzhi[1]]
        roles = ("本气", "余气") if len(stems) == 2 else ("本气", "中气", "余气")
        rows[name] = {
            "exposed": {"stem": ganzhi[0], "ten_god": ten_god(master, ganzhi[0])},
            "hidden": [
                {"stem": stem, "role": roles[i], "ten_god": ten_god(master, stem)} for i, stem in enumerate(stems)
            ],
        }
    return block(
        "p8-named-hidden-ten-gods-v1",
        command_rule(selected)["source"],
        selected_command=selected["command"],
        day_master=master,
        pillars=rows,
        complete_table={stem: ten_god(master, stem) for stem in "甲乙丙丁戊己庚辛壬癸"},
        role_note="本/中/余为所选司令表逆序；二段第二项记余；不等同v3藏干表或气量比例",
    )


def named_stars(pillars: dict[str, str], selected: dict[str, str]) -> dict[str, Any]:
    result, rules = auxiliary_stars(pillars), table("schools")
    for row in result["markers"]:
        key = {"天乙贵人": "tianyi", "羊刃": "blade"}.get(row["name"])
        if key:
            method = rules[key][selected[key]]
            targets = method["table"].get(pillars["day"][0], "")
            row.update(
                target_branches=list(targets),
                applicability="defined" if targets else "not_defined_for_yin_stem",
                method=selected[key],
                method_name=method["name"],
                source=rules["star_source"],
                placements=[
                    {"pillar": name, "branch": value[1]} for name, value in pillars.items() if value[1] in targets
                ],
            )
    result["method"] = "p8-named-auxiliary-v1"
    result["warnings"] = ["神煞属辅助参考；具名口径可选；不输出现实灾病死亡结论"]
    result["selected_schools"] = {key: selected[key] for key in ("tianyi", "blade")}
    return result


def replace_layer_hidden(value: Any, hidden: dict[str, str], master: str) -> None:
    if isinstance(value, dict):
        if "ganzhi" in value and "hidden_ten_gods" in value:
            value["hidden_ten_gods"] = [
                {"stem": stem, "ten_god": ten_god(master, stem)} for stem in hidden[value["ganzhi"][1]]
            ]
        for child in value.values():
            replace_layer_hidden(child, hidden, master)
    elif isinstance(value, list):
        for child in value:
            replace_layer_hidden(child, hidden, master)


def named_supplement(engine: Any, args: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    selected = options(args.get("p8_options"))
    hidden = hidden_for(selected)
    pillars = {key: row["ganzhi"] for key, row in data["pillars"].items()}
    result = supplement(engine, args, data)
    civil = datetime.strptime(args["datetime"], "%Y-%m-%d %H:%M") + timedelta(hours=8 - args["tz"])
    lunar = solar_at(engine, civil).getLunar()
    previous, following = lunar.getPrevJie(), lunar.getNextJie()
    elapsed = (civil - datetime.fromisoformat(previous.getSolar().toYmdHms())).total_seconds() / 86400
    result["month_command"] = named_command(pillars["month"][1], elapsed, pillars["day"][0], selected)
    result["month_command"].update(
        calendar_birth_at=civil.isoformat() + "+08:00",
        period_start=iso(previous.getSolar()),
        period_end_exclusive=iso(following.getSolar()),
        start_jie=previous.getName(),
    )
    result["ten_gods"] = named_ten_gods(pillars, hidden, selected)
    result["strength"] = named_scores(pillars, hidden)
    result["patterns"] = named_patterns(pillars, hidden, result["strength"])
    from ...calculations.bazi.structure import useful

    result["useful_candidates"] = useful(pillars, result["strength"], result["patterns"], result["climate"])
    result["climate"]["collation_status"] = "未经原刊校勘"
    result["climate"]["warnings"].append("未经原刊校勘；正式阶段待校勘，不将转录本视作原刊")
    result["auxiliary_stars"] = named_stars(pillars, selected)
    result["selected_schools"] = dict(selected, hidden_order="reverse_command_segments")
    result["method"] = "p8-named-bazi-supplement-v2"
    replace_layer_hidden(result["decade_luck"], hidden, pillars["day"][0])
    replace_layer_hidden(result["calendar_layers"], hidden, pillars["day"][0])
    return result
