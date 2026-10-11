"""Rules authorize limited claims; valid JSON paths alone do not authorize inference.

There is no evaluator for arbitrary expressions, code or SQL. Builtin predicate
IDs select audited Python checks. The model cannot register or rewrite rules.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from .contracts import KnowledgeRule, KnowledgeSource

_PACK = Path(__file__).with_name("builtin.json")
_CARDS = Path(__file__).with_name("tarot_meanings.json")
_SYSTEMS = {"bazi", "ziwei", "astro", "tarot"}
_PREDICATES = {"bazi_structure", "ziwei_linked_structure", "astro_major_aspects", "tarot_editorial", "tarot_temperance_upright"}
_SPREADS = {"focus1": 1, "reflect3": 3, "choice5": 5}
_ANGLES = {"六合": 60, "刑相": 90, "拱相": 120, "冲相": 180}
_GANS = "甲乙丙丁戊己庚辛壬癸"
_ZHIS = "子丑寅卯辰巳午未申酉戌亥"
_RELEVANT = ("owner_user_id", "subject_id", "revision", "branch_id", "time_scale")


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _same_value(left, right):
    # Python's True == 1 must not authorize a reference with a different type.
    try:
        return _json(left) == _json(right)
    except (ValueError, TypeError):
        return False


def resolve_pointer(data, pointer):
    """Strict RFC 6901 references. Arrays do not accept negative Python indices."""
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("feature needs a non-root JSON Pointer")
    node = data
    for encoded in pointer.split("/")[1:]:
        for i, char in enumerate(encoded):
            if char == "~" and (i + 1 == len(encoded) or encoded[i + 1] not in "01"):
                raise ValueError("invalid JSON Pointer escape")
        part = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list):
            if not part.isascii() or not part.isdigit() or (len(part) > 1 and part[0] == "0"):
                raise ValueError("invalid array index")
            index = int(part)
            if index >= len(node):
                raise ValueError("array index outside artifact")
            node = node[index]
        elif isinstance(node, dict) and part in node:
            node = node[part]
        else:
            raise ValueError("missing artifact path")
    return node


def _issue(code, detail, feature_key=None):
    result = {"code": code, "detail": detail}
    if feature_key:
        result["feature_key"] = feature_key
    return result


def _finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


class KnowledgeRegistry:
    def __init__(self, rules, sources, tarot_catalog=None, *, pack_version="core-knowledge-2026-10-11-v1"):
        parsed_rules = [KnowledgeRule.model_validate(value) for value in rules]
        parsed_sources = [KnowledgeSource.model_validate(value) for value in sources]
        self._rules = {value.rule_id: value for value in parsed_rules}
        self._sources = {value.source_id: value for value in parsed_sources}
        if len(self._rules) != len(parsed_rules) or len(self._sources) != len(parsed_sources):
            raise ValueError("duplicate rule/source ID")
        for rule in parsed_rules:
            if rule.predicate_id not in _PREDICATES:
                raise ValueError("unregistered predicate")
            if any(ref not in self._sources for ref in rule.source_refs):
                raise ValueError("unknown knowledge source")
            if rule.editorial_status == "expert_reviewed":
                # Builtin content has no human expert sign-off. This code cannot
                # turn a machine review into an expert certification.
                raise ValueError("expert review requires a separately reviewed release")
        self._tarot = deepcopy(tarot_catalog or {})
        self._cards = {card["card_id"]: card for card in self._tarot.get("cards", [])}
        if self._tarot and (len(self._cards) != 78 or len(self._tarot["cards"]) != 78):
            raise ValueError("tarot catalog must contain 78 distinct cards")
        self.pack_version = pack_version
        self.pack_hash = _digest({"rules": [r.model_dump() for r in parsed_rules], "sources": [s.model_dump() for s in parsed_sources], "tarot": self._tarot})

    @classmethod
    def load_builtin(cls):
        payload = json.loads(_PACK.read_text(encoding="utf-8"))
        return cls(payload["rules"], payload["sources"], json.loads(_CARDS.read_text(encoding="utf-8")), pack_version=payload["pack_version"])

    def select(self, system, topic="general", time_scale="natal", school_id=None):
        if not isinstance(system, str) or system not in _SYSTEMS:
            return []
        return [rule.model_dump() for rule in self._rules.values()
                if rule.system == system and topic in rule.applicable_topics
                and time_scale in rule.time_scales and (school_id is None or rule.school_id == school_id)]

    def sources(self, rule_id=None):
        if rule_id is not None and (not isinstance(rule_id, str) or rule_id not in self._rules):
            return []
        selected = self._rules[rule_id].source_refs if rule_id else self._sources
        return [self._sources[identifier].model_dump() for identifier in selected]

    def get(self, rule_id):
        return self._rules[rule_id].model_dump() if isinstance(rule_id, str) and rule_id in self._rules else None

    def evaluate(self, rule_id, features, context, artifacts):
        rule = self._rules.get(rule_id) if isinstance(rule_id, str) else None
        if rule is None:
            return {"eligible": False, "status": "RULE_GAP", "issues": [_issue("RULE_GAP", "没有已发布的规则，禁止补成支持")], "feature_refs": [], "source_refs": []}
        result = {"eligible": False, "status": "RULE_GAP", "issues": [], "feature_refs": [], "source_refs": list(rule.source_refs),
                  "rule_id": rule.rule_id, "rule_version": rule.version, "rule_hash": _digest(rule.model_dump()),
                  "pack_version": self.pack_version, "pack_hash": self.pack_hash,
                  "editorial_status": rule.editorial_status, "empirical_status": rule.empirical_status,
                  "allowed_interpretations": [item.model_dump() for item in rule.allowed_interpretations],
                  "limitations": list(rule.limitations), "counter_factors": [], "values": {}}
        issues = result["issues"]
        if not isinstance(context, dict) or any(key not in context for key in _RELEVANT):
            issues.append(_issue("AUTH_SCOPE_ERROR", "缺少服务端人物、版本或分支范围"))
        elif any(not isinstance(context[key], str) or not context[key].strip() for key in _RELEVANT if key != "revision") or not isinstance(context["revision"], int) or isinstance(context["revision"], bool) or context["revision"] < 0:
            issues.append(_issue("AUTH_SCOPE_ERROR", "人物、版本或分支范围无效"))
        elif context["time_scale"] not in rule.time_scales:
            issues.append(_issue("SCOPE_MISMATCH", "规则不适用于当前时间层次"))
        if issues:
            result["status"] = issues[0]["code"]
            return result
        if not isinstance(features, dict) or not isinstance(artifacts, dict):
            issues.append(_issue("REFERENCE_ERROR", "特征或产物不是服务端映射"))
            result["status"] = issues[0]["code"]
            return result
        used_artifact_ids = set()
        values = {}
        for key in rule.required_features:
            feature = features.get(key, features.get(rule.system + "." + key))
            if key in features and rule.system + "." + key in features and not _same_value(features[key], features[rule.system + "." + key]):
                issues.append(_issue("REFERENCE_ERROR", "同一语义字段存在互相矛盾的引用", key))
                continue
            if not isinstance(feature, dict):
                issues.append(_issue("MISSING_INPUT", "规则所需计算字段未提供", key))
                continue
            artifact_id = feature.get("artifact_id")
            if not isinstance(artifact_id, str) or not artifact_id:
                issues.append(_issue("REFERENCE_ERROR", "计算产物ID无效", key))
                continue
            artifact = artifacts.get(artifact_id)
            if not isinstance(artifact, dict):
                issues.append(_issue("REFERENCE_ERROR", "计算产物不存在", key))
                continue
            used_artifact_ids.add(artifact_id)
            if any(artifact.get(name) != context[name] for name in ("owner_user_id", "subject_id")):
                issues.append(_issue("AUTH_SCOPE_ERROR", "产物不属于本轮授权人物", key))
                continue
            if not _same_value(artifact.get("revision"), context["revision"]):
                issues.append(_issue("STALE_INPUT", "计算资料版本已改变", key))
                continue
            composite_natal = (artifact.get("time_scale") == "natal_with_explicit_separate_target_layers"
                               and context["time_scale"] == "natal" and feature.get("time_scale") == "natal")
            if artifact.get("branch_id") != context["branch_id"] or (artifact.get("time_scale") != context["time_scale"] and not composite_natal):
                issues.append(_issue("SCOPE_MISMATCH", "产物的输入分支或时间层次不同", key))
                continue
            if artifact.get("system") != rule.system or artifact.get("school_id") != rule.school_id:
                issues.append(_issue("SCOPE_MISMATCH", "计算体系或流派与规则不符", key))
                continue
            # If the adapter supplies scoped feature metadata it must agree too.
            if any(name in feature and not _same_value(feature[name], context[name]) for name in _RELEVANT):
                issues.append(_issue("SCOPE_MISMATCH", "特征范围元数据不符", key))
                continue
            try:
                pointer = feature.get("path")
                relative = pointer[5:] if isinstance(pointer, str) and pointer.startswith("/data/") else pointer
                if relative != "/" + key:
                    raise ValueError("字段语义与授权计算路径不符")
                observed = resolve_pointer(artifact, pointer) if pointer.startswith("/data/") else resolve_pointer(artifact.get("data"), pointer)
                if "value" not in feature or not _same_value(observed, feature["value"]):
                    raise ValueError("引用值与产物字段不一致")
            except (ValueError, TypeError) as error:
                issues.append(_issue("REFERENCE_ERROR", str(error), key))
                continue
            values[key] = deepcopy(observed)
            result["feature_refs"].append({"feature_key": key, "artifact_id": artifact_id, "path": feature["path"], "value": deepcopy(observed)})
        if len(used_artifact_ids) > 1:
            issues.append(_issue("REFERENCE_ERROR", "本规则的字段必须来自同一确定性产物"))
        if issues:
            result["status"] = issues[0]["code"]
            return result
        issues.extend(self._check(rule, values))
        result["eligible"] = not issues
        result["status"] = "supported" if not issues else issues[0]["code"]
        if not issues:
            result["values"] = values
            result["counter_factors"] = self._counter_factors(rule, values)
        return result

    def _check(self, rule, values):
        predicate = rule.predicate_id
        if predicate == "bazi_structure":
            pillars, day_master = values["pillars"], values["day_master"]
            if not isinstance(pillars, dict) or any(key not in pillars for key in ("year", "month", "day", "hour")):
                return [_issue("RULE_GAP", "四柱不完整，不把缺时柱当成完整本命分析")]
            for key in ("year", "month", "day", "hour"):
                pillar = pillars[key]
                if not isinstance(pillar, dict) or not isinstance(pillar.get("ganzhi"), str) or len(pillar["ganzhi"]) != 2 or pillar["ganzhi"][0] not in _GANS or pillar["ganzhi"][1] not in _ZHIS:
                    return [_issue("RULE_GAP", "四柱干支字段不完整")]
                if pillar.get("gan", pillar["ganzhi"][0]) != pillar["ganzhi"][0] or pillar.get("zhi", pillar["ganzhi"][1]) != pillar["ganzhi"][1]:
                    return [_issue("REFERENCE_ERROR", "柱干支与拆分字段矛盾")]
            stem = day_master.get("gan") if isinstance(day_master, dict) else day_master
            if stem != pillars["day"]["ganzhi"][0]:
                return [_issue("REFERENCE_ERROR", "日主与日柱天干不一致")]
            if not isinstance(values["method"], dict) or not values["method"]:
                return [_issue("RULE_GAP", "计算口径缺失，不能假定交节或日界处理")]
        elif predicate == "ziwei_linked_structure":
            palace = values["topic_palace"]
            if not isinstance(palace, dict) or not isinstance(palace.get("index"), int) or isinstance(palace.get("index"), bool) or palace["index"] not in range(12):
                return [_issue("RULE_GAP", "缺少真实主题宫位索引")]
            linked = palace.get("linked_palaces")
            if not isinstance(linked, list) or len(linked) != 3:
                return [_issue("RULE_GAP", "缺少三方四正联动，禁用单星关键词解读")]
            expected = {(palace["index"] + offset) % 12: relation for offset, relation in ((4, "三合"), (8, "三合"), (6, "对宫"))}
            if any(not isinstance(item, dict) or type(item.get("index")) is not int for item in linked):
                return [_issue("REFERENCE_ERROR", "联动宫位索引无效")]
            if len({item["index"] for item in linked}) != 3:
                return [_issue("REFERENCE_ERROR", "联动宫位重复或缺失")]
            for item in [palace, *linked]:
                if not isinstance(item, dict) or any(not isinstance(item.get(key), str) or not item[key] for key in ("name", "ganzhi")) or not all(isinstance(item.get(key), list) for key in ("major", "minor")):
                    return [_issue("RULE_GAP", "宫位结构必须包含主星、辅星和宫干支")]
                if item is not palace and expected.get(item.get("index")) != item.get("relation"):
                    return [_issue("REFERENCE_ERROR", "联动宫位不符合本宫两组三合与对宫")]
                for star in [*item["major"], *item["minor"]]:
                    if not isinstance(star, dict) or not isinstance(star.get("name"), str) or not star["name"]:
                        return [_issue("REFERENCE_ERROR", "星曜必须来自命盘结构")]
                    if "mutagen" in star and star["mutagen"] not in ("", "禄", "权", "科", "忌", "化禄", "化权", "化科", "化忌"):
                        return [_issue("RULE_GAP", "本规则未定义该四化字段")]
            if not isinstance(values["method"], dict) or not values["method"]:
                return [_issue("RULE_GAP", "未记录排盘口径")]
        elif predicate == "astro_major_aspects":
            aspects, orb = values["aspects"], values["aspect_orb"]
            if not isinstance(aspects, list) or not aspects:
                return [_issue("RULE_GAP", "当前没有可引用的已计算主要相位")]
            if not _finite_number(orb) or orb < 0 or orb > 10:
                return [_issue("RULE_GAP", "缺少受支持的明确容许度口径")]
            for aspect in aspects:
                if not isinstance(aspect, dict):
                    return [_issue("REFERENCE_ERROR", "相位记录无效")]
                allowed_angles = dict(_ANGLES, 合相=0)
                if not isinstance(aspect.get("aspect"), str) or aspect["aspect"] not in allowed_angles or not _finite_number(aspect.get("angle")) or aspect["angle"] != allowed_angles[aspect["aspect"]]:
                    return [_issue("RULE_GAP", "相位名称或角度不在本规则定义中")]
                if not _finite_number(aspect.get("orb")) or aspect["orb"] < 0 or aspect["orb"] > orb:
                    return [_issue("REFERENCE_ERROR", "相位误差超出已声明容许度")]
                if not all(isinstance(aspect.get(key), str) and aspect[key] for key in ("from", "to")) or aspect["from"] == aspect["to"]:
                    return [_issue("REFERENCE_ERROR", "相位所涉天体记录无效")]
            if not any(item.get("aspect") in _ANGLES for item in aspects):
                return [_issue("RULE_GAP", "原典本条只覆盖六合、刑、拱、冲；合相需独立规则")]
            if not isinstance(values["method"], dict) or values["method"].get("zodiac") != "tropical":
                return [_issue("SCOPE_MISMATCH", "此包仅覆盖明确声明的回归黄道口径")]
        elif predicate in ("tarot_editorial", "tarot_temperance_upright"):
            cards, spread = values["cards"], values["spread_id"]
            if values["status"] not in ("finalized", "revealed"):
                return [_issue("DRAW_MISMATCH", "抽牌尚未完成，解释不能替代真实翻牌")]
            if values["deck_version"] != self._tarot.get("deck_version"):
                return [_issue("RULE_GAP", "未发布此牌系版本的牌意")]
            if not isinstance(spread, str) or spread not in _SPREADS or not isinstance(cards, list) or len(cards) != _SPREADS[spread]:
                return [_issue("DRAW_MISMATCH", "牌阵与已保存牌数不符")]
            if any(not isinstance(item, dict) or not isinstance(item.get("card_id"), str) for item in cards):
                return [_issue("DRAW_MISMATCH", "牌ID无效")]
            if len({item["card_id"] for item in cards}) != len(cards):
                return [_issue("DRAW_MISMATCH", "本牌系不允许同次抽牌重复")]
            for index, item in enumerate(cards):
                if item.get("card_id") not in self._cards or item.get("orientation") not in ("upright", "reversed"):
                    return [_issue("DRAW_MISMATCH", "未知牌 ID 或方向")]
                if "position" in item and (type(item["position"]) is not int or item["position"] != index + 1):
                    return [_issue("DRAW_MISMATCH", "牌位顺序与持久化结果不符")]
                if "name" in item and item["name"] != self._cards[item["card_id"]]["name"]:
                    return [_issue("DRAW_MISMATCH", "牌名与稳定牌 ID 不符")]
            if predicate == "tarot_temperance_upright" and not any(item["card_id"] == "major-14" and item["orientation"] == "upright" for item in cards):
                return [_issue("RULE_GAP", "Waite节制正位定义不能替代另一张牌或逆位")]
        return []

    def _counter_factors(self, rule, values):
        if rule.system == "bazi":
            return ["旺衰、格局、调候与用神完整前提尚未实现；本条不选择喜用神。"]
        if rule.system == "ziwei":
            palace = values["topic_palace"]
            stars = [star for p in [palace, *palace["linked_palaces"]] for star in [*p["major"], *p["minor"]]]
            factors = ["三方四正结构与流年应期不能互相替代。"]
            if any(star.get("mutagen") in ("忌", "化忌") for star in stars):
                factors.append("联动宫位含化忌：保留牵制因素，不能只摘取吉化。")
            return factors
        if rule.system == "astro":
            labels = {item["aspect"] for item in values["aspects"]}
            return (["盘中同时有协调与张力配置，禁止只保留符合期待的一组。"]
                    if labels & {"六合", "拱相"} and labels & {"刑相", "冲相"} else ["相位几何不证明现实事件；其他天体条件尚需独立规则。"])
        return [self._cards[item["card_id"]]["misreading"] for item in values["cards"]]

    def _render(self, rule, interpretation, values):
        if rule.system == "bazi":
            dm = values["day_master"]
            stem = dm.get("gan") if isinstance(dm, dict) else dm
            return interpretation.text_template.format(day_master=stem, month_ganzhi=values["pillars"]["month"]["ganzhi"])
        if rule.system == "ziwei":
            palace = values["topic_palace"]
            constellation = []
            for item in [palace, *palace["linked_palaces"]]:
                names = "、".join(star["name"] + ("(" + star["mutagen"] + ")" if star.get("mutagen") else "") for star in [*item["major"], *item["minor"]]) or "无已列主辅星"
                constellation.append(item["name"] + "：" + names)
            return interpretation.text_template.format(palace_name=palace["name"], linked_names="、".join(item["name"] for item in palace["linked_palaces"]), constellation="；".join(constellation))
        if rule.system == "astro":
            configurations = "；".join(f"{item['from']}与{item['to']} {item['aspect']}，容许误差{item['orb']}°" for item in values["aspects"] if item["aspect"] in _ANGLES)
            return interpretation.text_template.format(configurations=configurations, orb=values["aspect_orb"])
        if rule.predicate_id == "tarot_temperance_upright":
            return interpretation.text_template
        reflection = "；".join(f"第{index+1}牌位 {self._cards[item['card_id']]['name']}（{'正位' if item['orientation']=='upright' else '逆位'}）：{self._cards[item['card_id']][item['orientation']]}" for index, item in enumerate(values["cards"]))
        return interpretation.text_template.format(reflection=reflection)

    def declare(self, rule_id, features, context, artifacts, interpretation_id):
        result = self.evaluate(rule_id, features, context, artifacts)
        if not result["eligible"]:
            return result
        rule = self._rules[rule_id]
        interpretation = next((item for item in rule.allowed_interpretations if item.interpretation_id == interpretation_id), None)
        if interpretation is None:
            result["eligible"] = False
            result["status"] = "UNSUPPORTED_INFERENCE"
            result["issues"].append(_issue("UNSUPPORTED_INFERENCE", "解释不在该规则允许集合，字段存在不等于任意断语成立"))
            return result
        body = {"rule_id": rule_id, "rule_version": rule.version, "rule_hash": result["rule_hash"], "pack_version": self.pack_version,
                "system": rule.system, "school_id": rule.school_id, **{key: context[key] for key in _RELEVANT},
                "feature_refs": result["feature_refs"], "source_refs": result["source_refs"], "interpretation_id": interpretation_id,
                "text": self._render(rule, interpretation, result["values"]), "claim_type": "traditional_interpretation" if rule.empirical_status == "traditional_not_empirically_validated" else "symbolic_reflection",
                "scope": interpretation.scope, "limitations": result["limitations"], "counter_factors": result["counter_factors"],
                "editorial_status": rule.editorial_status, "empirical_status": rule.empirical_status,
                "real_world_link_status": "not_established", "derivation_summary": "已逐项核对本轮授权产物字段、规则前提与解释范围；此说明不包含隐藏思维链。"}
        body["claim_id"] = "claim-" + _digest(body)[:32]
        result["claim"] = body
        return result

    def validate_claim(self, claim, features, context, artifacts):
        """Recompute released meaning before render; a model cannot amend it."""
        if not isinstance(claim, dict):
            return {"eligible": False, "status": "UNSUPPORTED_INFERENCE", "issues": [_issue("UNSUPPORTED_INFERENCE", "声明不是结构化对象")]}
        result = self.declare(claim.get("rule_id"), features, context, artifacts, claim.get("interpretation_id"))
        if result["eligible"] and not _same_value(claim, result["claim"]):
            result["eligible"] = False
            result["status"] = "UNSUPPORTED_INFERENCE"
            result["issues"].append(_issue("UNSUPPORTED_INFERENCE", "声明文字、引用或范围已偏离已验证规则"))
            result.pop("claim", None)
        return result
