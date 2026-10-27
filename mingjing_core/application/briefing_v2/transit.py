"""Small descriptive templates; a structural hit never becomes a real-world prediction."""

from collections.abc import Mapping
from datetime import date
from typing import Any

from mingjing_core.application.followups_contracts import FollowupScope

from .contracts import BriefingError, BriefLine, BriefSection
from .evidence import pointer, validate_transit

TEN_GODS = frozenset({"比肩", "劫财", "食神", "伤官", "偏财", "正财", "七杀", "偏官", "正官", "偏印", "正印"})
RELATIONS = frozenset(
    {
        "天干五合",
        "六合",
        "三合",
        "三会",
        "三刑",
        "六冲",
        "六害",
        "六破",
        "冲",
        "合",
        "刑",
        "害",
        "破",
        "相克",
        "地支六冲",
        "地支六合",
    }
)
PLANETS = frozenset(
    {"太阳", "月亮", "水星", "金星", "火星", "木星", "土星", "天王", "海王", "冥王", "天王星", "海王星", "冥王星"}
)
ASPECTS = {"合相": 0, "六合": 60, "刑相": 90, "拱相": 120, "冲相": 180}
PALACES = frozenset(
    {"命宫", "兄弟", "夫妻", "子女", "财帛", "疾厄", "迁移", "仆役", "交友", "官禄", "田宅", "福德", "父母"}
)


def transit_section(
    payload: Mapping[str, Any], *, scope: FollowupScope, day: date, profile_revision: int
) -> tuple[BriefSection | None, tuple[str, ...]]:
    snapshot = validate_transit(payload, scope=scope, day=day, profile_revision=profile_revision)
    from mingjing_core.streaming.json_values import thaw_json

    raw = thaw_json(snapshot.payload)
    by_alias = {ref.alias: ref for ref in snapshot.basis}
    rendered, counts, warnings = [], {}, []
    for index, hit in enumerate(raw["rule_hits"], 1):
        system = hit["context"]["system"]
        if counts.get(system, 0) >= 2:
            continue
        try:
            wording = _wording(raw, hit)
        except (TypeError, ValueError, KeyError):
            warnings.append("transit_rule_context_not_rendered")
            continue
        if wording is None:
            continue
        rule = raw["aliases"]["r"][index - 1]
        basis = tuple(by_alias[alias] for alias in (*rule["evidence_aliases"], rule["alias"]))
        rendered.append(BriefLine("按当日北京时间12:00快照：" + wording, basis))
        counts[system] = counts.get(system, 0) + 1
    if not rendered:
        return None, ("transit_no_supported_daily_hits", *dict.fromkeys(warnings))
    return BriefSection("transit", "今日流日结构", tuple(rendered)), tuple(dict.fromkeys(warnings))


def _wording(raw: dict[str, Any], hit: dict[str, Any]) -> str | None:
    context = hit["context"]
    system, kind = context["system"], context.get("kind")
    if system == "bazi" and kind == "ten_god" and context.get("layer") == "daily":
        value = _object_evidence(raw, hit)
        if context.get("ten_god") not in TEN_GODS or value.get("stem_ten_god") != context["ten_god"]:
            raise BriefingError("transit_ten_god_context_mismatch")
        return f"子平具名口径的流日天干十神为{context['ten_god']}；仅描述结构，不推断现实结果。"
    if system == "bazi" and kind == "relation" and "daily" in context.get("target_layers", []):
        value = _object_evidence(raw, hit)
        if context.get("relation") not in RELATIONS or type(context.get("complete")) is not bool:
            raise BriefingError("transit_relation_context_invalid")
        if value.get("kind") != context["relation"] or value.get("complete") is not context["complete"]:
            raise BriefingError("transit_relation_context_mismatch")
        state = "成员齐备，仍不推断合化或应事" if context["complete"] else "成员未齐，不能说完整成立"
        return f"子平项目结构关系口径，八字{context['relation']}结构：{state}。"
    if system == "ziwei" and kind == "mutagen" and context.get("layer") == "daily":
        return _ziwei(raw, hit)
    if system == "astro" and kind == "aspect":
        return _astro(raw, hit)
    return None


def _ziwei(raw: dict[str, Any], hit: dict[str, Any]) -> str | None:
    context = hit["context"]
    mutagen, palace = context.get("mutagen"), context.get("natal_palace")
    index = context.get("palace_index")
    if (
        mutagen not in {"禄", "权", "科", "忌"}
        or palace not in PALACES
        or type(index) is not int
        or not 0 <= index < 12
    ):
        raise BriefingError("transit_ziwei_context_invalid")
    layer = raw["data"]["ziwei"]["transformations"]["daily"]
    links = [link for link in layer.get("links", []) if link.get("mutagen") == mutagen]
    if len(links) != 1 or links[0].get("status") != "resolved" or len(links[0].get("locations", [])) != 1:
        return None
    location = links[0]["locations"][0]
    if location.get("palace_index") != index or location.get("natal_palace") != palace:
        raise BriefingError("transit_ziwei_location_mismatch")
    if links[0].get("evidence_paths") != hit["evidence_paths"]:
        raise BriefingError("transit_ziwei_evidence_mismatch")
    return f"紫微引擎默认口径的流日化{mutagen}关联本命{palace}宫；只是星曜落点，不代表具体事件。"


def _astro(raw: dict[str, Any], hit: dict[str, Any]) -> str:
    context = hit["context"]
    value = _object_evidence(raw, hit)
    if context.get("from") not in PLANETS or context.get("to") not in PLANETS or context.get("aspect") not in ASPECTS:
        raise BriefingError("transit_aspect_context_invalid")
    orb, limit = context.get("orb_degrees"), context.get("orb_limit")
    if type(orb) not in (int, float) or type(limit) not in (int, float) or not 0 <= orb <= limit <= 10:
        raise BriefingError("transit_orb_invalid")
    if any(value.get(key) != context[key] for key in ("from", "to", "aspect", "orb_degrees")):
        raise BriefingError("transit_aspect_context_mismatch")
    if value.get("angle") != ASPECTS[context["aspect"]] or raw["data"]["astro"]["orb_limit_degrees"] != limit:
        raise BriefingError("transit_aspect_angle_or_limit_mismatch")
    return (
        f"行运{context['from']}与本命{context['to']}呈{context['aspect']}，"
        f"偏离{orb:.2f}°（容许度{limit:g}°）；几何条件不证明预测有效。"
    )


def _object_evidence(raw: dict[str, Any], hit: dict[str, Any]) -> dict[str, Any]:
    value = pointer(raw, hit["evidence_paths"][0])
    if type(value) is not dict:
        raise BriefingError("transit_evidence_object_required")
    return value
