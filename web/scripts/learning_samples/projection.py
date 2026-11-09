"""Public learning cards retain original alias identities but never raw observed JSON."""

from __future__ import annotations

import re

from .common import ERROR, need
from .learning_integrity import EFFECTS, verify_learning
from .source_catalog import safe_point_text, school_label, source_label

PUBLIC_LIMITS = [
    "沿用原信封本轮别名，不重编号；某c覆盖整个主盘，本页只展示受控摘要。",
    "内容摘要不代表签名或真实授权；真实接线须核对归属和撤销状态。",
    "纯规则学习要点，不生成新命理结论、性格标签或现实结果承诺。",
]

CARD_LIMITS = {
    "orientation": ["从已核对的主盘学习读法，不据此推断人格或现实结果。"],
    "matched_condition": ["这里只满足一项候选条件，未综合其他条件确认成格；未实现的筛选不补造成命中。"],
    "boundary": ["保留默认主盘和交界候选；原始时刻与完整候选四柱未下发，不授权倒推或修改出生时辰。"],
}


def public_ref(row: dict) -> dict:
    return {"document_id": row["ref"]["document_id"], "alias": row["alias"], "claim_id": row["claim_id"]}


def evidence_summary(row: dict, chart: dict) -> str:
    path = row["ref"]["path"]
    if row["alias"].startswith("r"):
        return (
            "已核对的交界条件；不据此倒推出生时辰。"
            if path.startswith("/boundary_alerts/")
            else "已核对的一项原生候选条件；不等于格局成立。"
        )
    if row["ref"] in chart["view"]["primary"]:
        return "当前主盘的原有计算依据；本卡没有新造更细的别名。"
    if re.fullmatch(
        r"/charts/(?:0|[1-9][0-9]*)/data/p8/patterns/regular_eight/(?:0|[1-9][0-9]*)/conditions/(?:0|[1-9][0-9]*)", path
    ):
        return "原生格局候选的条件输入；不下发任意观察JSON。"
    if re.fullmatch(
        r"/time_basis/items/(?:0|[1-9][0-9]*)/source_variants/(?:0|[1-9][0-9]*)/(?:coordinate_datetime|pillars|solar_time)",
        path,
    ):
        return "交界核对的时间坐标输入已核对；原始时刻与完整候选四柱未下发。"
    raise ValueError(ERROR)


def public_evidence(row: dict, chart: dict, system: str, card_by_rule: dict) -> dict:
    result = {
        **public_ref(row),
        "kind": "fact" if row["alias"].startswith("c") else "rule",
        "value_sha256": row["value_sha256"],
        "summary": evidence_summary(row, chart),
        "basis": row["basis"],
    }
    if row["alias"].startswith("r"):
        point = card_by_rule[row["alias"]]
        names = {alias["alias"]: alias for alias in chart["aliases"]["c"]}
        result.update(
            {
                "evidence_refs": [public_ref(names[name]) for name in row["evidence_aliases"]],
                "school": school_label(point, system),
                "sources": [source_label(value) for value in point["source_refs"]],
            }
        )
    return result


def public_text(point: dict, system: str) -> str:
    if point["kind"] == "matched_condition":
        condition = point["title"].split("/", 1)[1]
        return (
            f"这次核对的是“{condition}”这项候选条件。这里只展示已核对来源的公开摘要；单项满足不能跳过其他条件说已成格。"
        )
    if point["kind"] == "boundary":
        return (
            "这个样例靠近口径交界。本页只展示已核对的交界摘要，原始时刻与完整候选四柱不展开；"
            "保留记录和默认主盘，不据此倒推出生时辰。"
        )
    if system == "astro":
        return (
            "本页核对本命主盘的来源与具名方法，不展开完整行星位置；"
            "黄道、坐标、宫制、历表与UTC口径一起阅读，不把计算位置当作现实事件。"
        )
    return point["text"]


def public_card(point: dict, aliases: dict, system: str) -> dict:
    safe_point_text(point, system)
    return {
        "point_id": point["point_id"],
        "kind": point["kind"],
        "title": point["title"],
        "text": public_text(point, system),
        "school": school_label(point, system),
        "sources": [source_label(value) for value in point["source_refs"]],
        "c_aliases": list(point["c_aliases"]),
        "r_aliases": list(point["r_aliases"]),
        "citations": point["citations"],
        "evidence_refs": [public_ref(aliases[name]) for name in point["c_aliases"] + point["r_aliases"]],
        "limits": CARD_LIMITS[point["kind"]][:],
    }


def project_learning(learning: dict, chart: dict, system: str) -> dict:
    try:
        _, aliases = verify_learning(learning, chart, system)
        cards = [public_card(point, aliases, system) for point in learning["points"]]
        by_rule = {name: point for point in learning["points"] for name in point["r_aliases"]}
        rows = learning["aliases"]["c"] + learning["aliases"]["r"]
        evidence = [public_evidence(row, chart, system, by_rule) for row in rows]
        need(len({(row["document_id"], row["alias"]) for row in evidence}) == len(evidence))
        return {
            "format": "frontend-learning-sample-v1",
            "sample_id": f"ayuan-{system}",
            "system": system,
            "status": learning["status"],
            "cards": cards,
            "evidence": evidence,
            "effects": dict(EFFECTS),
            "limits": PUBLIC_LIMITS
            + [
                "仅已发布合成样例；未连接真实资料、通用Pointer或别名账本。",
                "公开摘要省略任意observed、原始时刻、完整候选四柱及实现细节。",
                "卡中实际输入已在本地核对；本公开版只展示受控依据摘要。",
            ],
        }
    except (KeyError, TypeError, IndexError, AttributeError, OverflowError):
        raise ValueError(ERROR) from None
