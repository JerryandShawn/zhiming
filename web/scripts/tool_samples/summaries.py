"""Evidence descriptions are constructed from checked fields, never raw context."""

from __future__ import annotations

import re

from .common import need, pointer


def astro_summary(data: dict, path: str) -> str:
    if path.startswith("/data/astro/aspects/"):
        item = pointer(data, path.removeprefix("/data"))
        return f"A方{item['from']}与B方{item['to']}{item['aspect']}，误差{item['orb_degrees']:.4f}°。"
    if path == "/data/astro/orb_degrees":
        return f"跨盘相位统一容许度{data['astro']['orb_degrees']:g}°。"
    need(re.fullmatch(r"/data/astro/positions_[ab]/[^/]+", path) is not None)
    _, _, _, side, planet = path.split("/")
    item = data["astro"][side][planet]
    return f"{side[-1].upper()}方{planet}黄经{item['longitude']:.4f}°。"


def bazi_summary(data: dict, path: str) -> str:
    if path in ("/data/bazi/pillars_a", "/data/bazi/pillars_b"):
        return f"{path[-1].upper()}方四柱：" + " · ".join(data["bazi"][path.rsplit("/", 1)[1]].values())
    if re.fullmatch(r"/data/bazi/element_complement/[01]", path):
        item = data["bazi"]["element_complement"][int(path.rsplit("/", 1)[1])]
        return f"{item['recipient'].upper()}方表层缺项对照：{''.join(item['elements']) or '无'}；不等于喜用。"
    if re.fullmatch(r"/data/bazi/useful_complement/[0-5]", path):
        item = data["bazi"]["useful_complement"][int(path.rsplit("/", 1)[1])]
        return f"{item['recipient'].upper()}方{item['method']}候选交集：{''.join(item['overlap']) or '无'}；未判力量。"
    need(path == "/data/bazi/day_stem_combination" or path.startswith("/data/bazi/branch_relations/"))
    item = pointer(data, path.removeprefix("/data"))
    return f"两侧{item['a']}、{item['b']}的结构对读；不据此宣布合化或关系结局。"


def synastry_summaries(root: dict, data: dict) -> dict:
    output = {}
    for row in root["aliases"]["c"]:
        path = row["path"]
        if path.startswith("/data/astro/"):
            summary = astro_summary(data, path)
        elif path.startswith("/data/bazi/"):
            summary = bazi_summary(data, path)
        else:
            need(re.fullmatch(r"/data/ziwei/cross_views/[01]", path) is not None)
            item = data["ziwei"]["cross_views"][int(path.rsplit("/", 1)[1])]
            own, other = item["own_spouse_palace"]["ganzhi"], item["other_life_palace"]["ganzhi"]
            summary = f"{item['recipient'].upper()}方夫妻宫{own}与对方命宫{other}并列，未提供适配分数。"
        output[path] = summary
    return output
