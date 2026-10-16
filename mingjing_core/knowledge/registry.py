"""Rules authorize limited claims; valid JSON paths alone do not authorize inference.

There is no evaluator for arbitrary expressions, code or SQL. Builtin predicate
IDs select audited Python checks. The model cannot register or rewrite rules.
"""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from .contracts import KnowledgeRule, KnowledgeSource
from ..domain.json_values import ensure_finite_json

_PACK = Path(__file__).with_name("builtin.json")
_CARDS = Path(__file__).with_name("tarot_meanings.json")
_SYSTEMS = {"bazi", "ziwei", "astro", "tarot"}
_PREDICATES = {"bazi_structure", "bazi_hidden_structure", "bazi_relations", "bazi_target_day", "bazi_target_period",
               "ziwei_linked_structure", "ziwei_temporal_structure", "astro_major_aspects",
               "astro_placements", "astro_transit_snapshot", "tarot_editorial", "tarot_temperance_upright"}
_SPREADS = {"focus1": 1, "reflect3": 3, "choice5": 5}
_ANGLES = {"六合": 60, "刑相": 90, "拱相": 120, "冲相": 180}
_GANS = "甲乙丙丁戊己庚辛壬癸"
_ZHIS = "子丑寅卯辰巳午未申酉戌亥"
_HIDDEN = {"子": ["癸"], "丑": ["己", "癸", "辛"], "寅": ["甲", "丙", "戊"], "卯": ["乙"],
           "辰": ["戊", "乙", "癸"], "巳": ["丙", "戊", "庚"], "午": ["丁", "己"], "未": ["己", "丁", "乙"],
           "申": ["庚", "壬", "戊"], "酉": ["辛"], "戌": ["戊", "辛", "丁"], "亥": ["壬", "甲"]}
_RELEVANT = ("owner_user_id", "subject_id", "revision", "branch_id", "time_scale")
TOPIC_ALIASES = {"education": "study", "learning": "study", "relationship": "relationships"}


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
    def __init__(self, rules, sources, tarot_catalog=None, *, pack_version="core-knowledge-2026-10-11-v2"):
        ensure_finite_json(rules)
        ensure_finite_json(sources)
        ensure_finite_json(tarot_catalog)
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
        topic = TOPIC_ALIASES.get(topic, topic)
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
        try:
            ensure_finite_json(features)
            ensure_finite_json(artifacts)
        except (ValueError, TypeError):
            issues.append(_issue("REFERENCE_ERROR", "特征或产物包含非有限数值或非JSON数据"))
            result["status"] = "REFERENCE_ERROR"
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
            composite_scope = (artifact.get("time_scale") == "natal_with_explicit_separate_target_layers"
                               and feature.get("time_scale") == context["time_scale"])
            if artifact.get("branch_id") != context["branch_id"] or (artifact.get("time_scale") != context["time_scale"] and not composite_scope):
                issues.append(_issue("SCOPE_MISMATCH", "产物的输入分支或时间层次不同", key))
                continue
            if artifact.get("system") != rule.system or artifact.get("school_id") != rule.school_id:
                issues.append(_issue("SCOPE_MISMATCH", "计算体系或流派与规则不符", key))
                continue
            if context["time_scale"] not in ("natal", "question") and (
                    not context.get("target_date") or artifact.get("target_date") != context["target_date"]):
                issues.append(_issue("SCOPE_MISMATCH", "目标时间层必须绑定同一目标日期", key))
                continue
            # If the adapter supplies scoped feature metadata it must agree too.
            if any(name in feature and not _same_value(feature[name], context[name]) for name in _RELEVANT):
                issues.append(_issue("SCOPE_MISMATCH", "特征范围元数据不符", key))
                continue
            try:
                pointer = feature.get("path")
                relative = pointer[5:] if isinstance(pointer, str) and pointer.startswith("/data/") else pointer
                semantic_path = "/horoscope/" + key.split(".", 1)[1] if key.startswith("horoscope.") else "/" + key
                if relative != semantic_path:
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
        try:
            issues.extend(self._check(rule, values))
        except (ValueError, TypeError, KeyError, IndexError, AttributeError):
            issues.append(_issue("RULE_GAP", "规则前提字段结构不完整，不能补成解释"))
        result["eligible"] = not issues
        result["status"] = "supported" if not issues else issues[0]["code"]
        if not issues:
            result["values"] = values
            result["counter_factors"] = self._counter_factors(rule, values)
        return result

    def _check(self, rule, values):
        predicate = rule.predicate_id
        if predicate in ("bazi_structure", "bazi_hidden_structure", "bazi_relations"):
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
            if predicate == "bazi_hidden_structure":
                hidden, gods = values["hidden_stems"], values["ten_gods"]
                if not isinstance(hidden, dict) or not isinstance(gods, dict) or set(hidden) != set(pillars) or set(gods) != set(pillars):
                    return [_issue("RULE_GAP", "缺少四柱藏干与十神结构")]
                names = {"比肩", "劫财", "食神", "伤官", "偏财", "正财", "七杀", "正官", "偏印", "正印", "日主"}
                for key in pillars:
                    if not isinstance(hidden[key], list) or not hidden[key] or any(stem not in _GANS for stem in hidden[key]):
                        return [_issue("REFERENCE_ERROR", "藏干列表无效")]
                    if hidden[key] != _HIDDEN[pillars[key]["ganzhi"][1]]:
                        return [_issue("REFERENCE_ERROR", "藏干与当前版本地支表不同")]
                    entry = gods[key]
                    if not isinstance(entry, dict) or entry.get("exposed") not in names:
                        return [_issue("RULE_GAP", "未提供可核对的天干十神名称")]
                    expected_exposed = "日主" if key == "day" else self._ten_god(stem, pillars[key]["ganzhi"][0])
                    if entry["exposed"] != expected_exposed:
                        return [_issue("REFERENCE_ERROR", "天干十神与日主生克阴阳关系不同")]
                    if "hidden_stems" not in entry or len(entry["hidden_stems"]) != len(hidden[key]):
                        return [_issue("RULE_GAP", "完整藏干十神需由计算库真实提供")]
                    if any(item.get("stem") != stem or item.get("ten_god") not in names for stem, item in zip(hidden[key], entry["hidden_stems"])):
                        return [_issue("REFERENCE_ERROR", "藏干十神与藏干引用不同")]
                    if any(item["ten_god"] != self._ten_god(stem, item["stem"]) for item in entry["hidden_stems"]):
                        return [_issue("REFERENCE_ERROR", "藏干十神与日主生克阴阳关系不同")]
            if predicate == "bazi_relations":
                relations = values["relations"]
                if not isinstance(relations, dict) or not isinstance(relations.get("pair_relations"), list):
                    return [_issue("RULE_GAP", "未计算干支关系")]
                observed = {}
                for item in relations["pair_relations"]:
                    if not isinstance(item, dict) or item.get("from") not in pillars or item.get("to") not in pillars or item["from"] == item["to"]:
                        return [_issue("REFERENCE_ERROR", "干支关系所引柱位无效")]
                    if item.get("transformation_asserted") is not False or any(name not in ("六冲", "六合", "天干五合") for name in item.get("relations", [])):
                        return [_issue("RULE_GAP", "此包只定义原始关系，不支持合化成立或力量权重")]
                    if item.get("ganzhi") != [pillars[item["from"]]["ganzhi"], pillars[item["to"]]["ganzhi"]]:
                        return [_issue("REFERENCE_ERROR", "关系引用干支与实际柱不同")]
                    pair = frozenset((item["from"], item["to"]))
                    if pair in observed or not isinstance(item.get("relations"), list) or len(set(item["relations"])) != len(item["relations"]):
                        return [_issue("REFERENCE_ERROR", "关系重复或字段结构无效")]
                    observed[pair] = set(item["relations"])
                expected = {}
                keys = ("year", "month", "day", "hour")
                branches = {frozenset(pair) for pair in ("子丑", "寅亥", "卯戌", "辰酉", "巳申", "午未")}
                stems = {frozenset(pair) for pair in ("甲己", "乙庚", "丙辛", "丁壬", "戊癸")}
                for index, left in enumerate(keys):
                    for right in keys[index + 1:]:
                        a, b = pillars[left]["ganzhi"], pillars[right]["ganzhi"]
                        labels = set()
                        if abs(_ZHIS.index(a[1]) - _ZHIS.index(b[1])) == 6: labels.add("六冲")
                        if frozenset((a[1], b[1])) in branches: labels.add("六合")
                        if frozenset((a[0], b[0])) in stems: labels.add("天干五合")
                        if labels: expected[frozenset((left, right))] = labels
                if observed != expected:
                    return [_issue("REFERENCE_ERROR", "六冲、六合或天干五合与实际四柱重算不同")]
        elif predicate == "bazi_target_day":
            day = values["day"]
            if not isinstance(day, dict) or any(not self._ganzhi(day.get(key)) for key in ("day_ganzhi", "month_ganzhi", "year_ganzhi")):
                return [_issue("RULE_GAP", "缺少目标时刻实际干支")]
            try:
                sample = datetime.fromisoformat(day["sample_at"])
                start, end = datetime.fromisoformat(day["period_start"]), datetime.fromisoformat(day["period_end_exclusive"])
                if sample.strftime("%Y-%m-%d") != day["date"] or sample.hour != 12 or day.get("timezone_offset") != 8 or not start <= sample < end:
                    raise ValueError()
            except (KeyError, ValueError, TypeError):
                return [_issue("REFERENCE_ERROR", "目标日快照或实际交节区间不符")]
        elif predicate == "bazi_target_period":
            period = next(iter(values.values()))
            if not isinstance(period, dict) or not self._ganzhi(period.get("ganzhi")):
                return [_issue("RULE_GAP", "缺少明确节年/节月干支")]
            try:
                sample = datetime.fromisoformat(period["sample_at"])
                start, end = datetime.fromisoformat(period["period_start"]), datetime.fromisoformat(period["period_end_exclusive"])
                if period.get("timezone_offset") != 8 or sample.strftime("%Y-%m-%d") != period["date"] or not start <= sample < end:
                    raise ValueError()
            except (KeyError, TypeError, ValueError):
                return [_issue("REFERENCE_ERROR", "目标节年/月的时刻与真实区间不同")]
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
        elif predicate == "ziwei_temporal_structure":
            layer = next(iter(values.values()))
            if not isinstance(layer, dict) or not self._ganzhi(layer.get("ganzhi")) or type(layer.get("index")) is not int or layer["index"] not in range(12):
                return [_issue("RULE_GAP", "运限层缺少实际宫位索引与干支")]
            if not isinstance(layer.get("mutagen"), list) or len(layer["mutagen"]) != 4 or not isinstance(layer.get("palace_names"), list) or len(layer["palace_names"]) != 12:
                return [_issue("RULE_GAP", "运限四化及12宫映射不完整")]
            links = layer.get("mutagen_links")
            if not isinstance(links, list):
                return [_issue("RULE_GAP", "缺少运限四化实际星曜位置关联")]
            labels = dict(zip(("禄", "权", "科", "忌"), layer["mutagen"]))
            for link in links:
                if not isinstance(link, dict) or link.get("mutagen") not in labels or link.get("star") != labels[link["mutagen"]] or type(link.get("palace_index")) is not int or link["palace_index"] not in range(12):
                    return [_issue("REFERENCE_ERROR", "四化星曜与本层记录不符")]
                if link.get("scope_palace") != layer["palace_names"][link["palace_index"]]:
                    return [_issue("REFERENCE_ERROR", "四化星曜的运限宫位映射不符")]
        elif predicate == "astro_placements":
            planets, houses = values["planets"], values["houses"]
            if not isinstance(planets, dict) or not planets or not isinstance(houses, list) or len(houses) != 12:
                return [_issue("RULE_GAP", "本命位置与12宫结构不完整")]
            if {h.get("house") for h in houses if isinstance(h, dict)} != set(range(1, 13)):
                return [_issue("REFERENCE_ERROR", "宫头编号不完整或重复")]
            for position in [*planets.values(), *houses, values["asc"], values["mc"]]:
                if not isinstance(position, dict) or not _finite_number(position.get("longitude")) or not 0 <= position["longitude"] < 360:
                    return [_issue("REFERENCE_ERROR", "黄经必须来自有限且归一化的真实计算")]
            if not isinstance(values["method"], dict) or values["method"].get("zodiac") != "tropical":
                return [_issue("SCOPE_MISMATCH", "位置规则只支持回归黄道")]
        elif predicate == "astro_transit_snapshot":
            transits, method = values["transits"], values["transit_method"]
            if not isinstance(transits, dict) or not isinstance(method, dict) or method.get("time_scope") != "daily_transit_snapshot":
                return [_issue("RULE_GAP", "缺少真实行运快照口径")]
            if transits.get("date") != method.get("target_date") or transits.get("timezone_offset") != method.get("target_timezone_offset"):
                return [_issue("SCOPE_MISMATCH", "行运目标日期或时区不一致")]
            if not isinstance(transits.get("planets"), dict) or not isinstance(transits.get("natal_reference"), dict) or not isinstance(transits.get("aspects_to_natal"), list):
                return [_issue("RULE_GAP", "缺少行运、本命参照和已计算相位")]
            orb = transits.get("orb_limit")
            if not _finite_number(orb) or not 0 <= orb <= 10:
                return [_issue("RULE_GAP", "未声明受支持的行运容许度")]
            for aspect in transits["aspects_to_natal"]:
                try:
                    a = transits["planets"][aspect["from"]]["longitude"]
                    b = transits["natal_reference"][aspect["to"]]["longitude"]
                    angle = dict(_ANGLES, 合相=0)[aspect["aspect"]]
                    expected = round(abs(abs((a - b + 180) % 360 - 180) - angle), 3)
                    if not _finite_number(a) or not _finite_number(b) or aspect["angle"] != angle or not _finite_number(aspect["orb"]) or abs(expected - aspect["orb"]) > .002 or expected > orb + .002:
                        raise ValueError()
                except (KeyError, TypeError, ValueError):
                    return [_issue("REFERENCE_ERROR", "行运相位与实际两层天体黄经不符")]
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

    @staticmethod
    def _ganzhi(value):
        return isinstance(value, str) and len(value) == 2 and value[0] in _GANS and value[1] in _ZHIS

    @staticmethod
    def _ten_god(day_stem, other_stem):
        left, right = _GANS.index(day_stem), _GANS.index(other_stem)
        relation = (right // 2 - left // 2) % 5
        same_polarity = left % 2 == right % 2
        return (("比肩", "劫财"), ("食神", "伤官"), ("偏财", "正财"), ("七杀", "正官"), ("偏印", "正印"))[relation][0 if same_polarity else 1]

    def _counter_factors(self, rule, values):
        if rule.predicate_id == "ziwei_temporal_structure":
            return ["只列指定运限层实际四化与宫位；没有把运限标签解释为事件必然发生。"]
        if rule.predicate_id in ("astro_placements", "astro_transit_snapshot"):
            return ["星座、宫位和快照仅为指定计算口径下的结构；出生时刻与输入分支改变时须重新核对。", "象征术语不验证现实事件，不提供精确应期。"]
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
        if rule.predicate_id == "bazi_target_period":
            period = next(iter(values.values()))
            return interpretation.text_template.format(**{key: period[key] for key in ("date", "ganzhi", "sample_at", "period_start", "period_end_exclusive")})
        if rule.predicate_id == "bazi_hidden_structure":
            details = []
            # JSON objects have no semantic key order; PostgreSQL JSONB can
            # reorder them between declaration and canonical revalidation.
            for name in ("year", "month", "day", "hour"):
                entry = values["ten_gods"][name]
                hidden = "、".join(item["stem"] + "(" + item["ten_god"] + ")" for item in entry["hidden_stems"])
                details.append(name + "柱透干" + entry["exposed"] + "；藏干" + hidden)
            return interpretation.text_template.format(hidden_details="；".join(details))
        if rule.predicate_id == "bazi_relations":
            pairs = values["relations"]["pair_relations"]
            details = "；".join(item["from"] + "与" + item["to"] + "：" + "、".join(item["relations"]) for item in pairs) or "本分支四柱未形成所支持的六冲、六合或天干五合"
            return interpretation.text_template.format(relations=details)
        if rule.predicate_id == "bazi_target_day":
            day = values["day"]
            return interpretation.text_template.format(**{key: day[key] for key in ("sample_at", "day_ganzhi", "month_ganzhi", "year_ganzhi", "period_start", "period_end_exclusive")})
        if rule.predicate_id == "ziwei_temporal_structure":
            layer = next(iter(values.values()))
            links = "；".join(item["star"] + "化" + item["mutagen"] + "：本命" + item["natal_palace"] + "，本层" + item["scope_palace"] for item in layer["mutagen_links"]) or "计算库没有返回可关联的四化星曜位置"
            return interpretation.text_template.format(layer=layer["name"], ganzhi=layer["ganzhi"], mutagen_links=links)
        if rule.predicate_id == "astro_placements":
            planets = values["planets"]
            fixed_order = ("太阳", "月亮", "水星", "金星", "火星", "木星", "土星", "天王", "海王", "冥王")
            names = [name for name in fixed_order if name in planets] + sorted(set(planets) - set(fixed_order))
            positions = "；".join(name + "在" + str(planets[name].get("sign", "未返回星座名")) + "，本命第" + str(planets[name].get("house", "未知")) + "宫" for name in names)
            return interpretation.text_template.format(placements=positions, asc=values["asc"].get("sign", "未知"), mc=values["mc"].get("sign", "未知"))
        if rule.predicate_id == "astro_transit_snapshot":
            transits = values["transits"]
            configurations = "；".join(item["from"] + "行运对本命" + item["to"] + "形成" + item["aspect"] + "，误差" + str(item["orb"]) + "°" for item in transits["aspects_to_natal"]) or "此快照未形成当前容许度内的已支持主要相位"
            return interpretation.text_template.format(sample_time=transits["sample_time"], configurations=configurations)
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

    def claims_for_calculation(self, calculation, *, owner_user_id, subject_id, revision,
                               topic="general", time_scales=None):
        """Build source-scoped declarations for each actual branch and supported layer.

        Identity is mandatory input from the service, never borrowed from artifacts.
        Unsupported rules are returned as gaps; no model or legacy agent is called.
        """
        output = {"claims": [], "scopes": {}, "gaps": [], "pack_version": self.pack_version, "pack_hash": self.pack_hash}
        if not isinstance(calculation, dict):
            raise ValueError("calculation must be a server-owned mapping")
        artifacts = calculation.get("artifacts", {})
        features = calculation.get("features", {})
        if not isinstance(artifacts, dict) or not isinstance(features, dict):
            raise ValueError("invalid calculation result mapping")
        for artifact_id, artifact in artifacts.items():
            if not isinstance(artifact, dict):
                output["gaps"].append({"status": "REFERENCE_ERROR", "artifact_id": artifact_id})
                continue
            scoped = {value["feature_key"]: value for value in features.values()
                      if isinstance(value, dict) and value.get("artifact_id") == artifact_id and isinstance(value.get("feature_key"), str)}
            profile = calculation.get("profiles", {}).get(artifact.get("profile_id"))
            if (not isinstance(profile, dict) or profile.get("school_id") != artifact.get("school_id")
                    or any(not _same_value(profile.get(name), artifact.get(name))
                           for name in ("owner_user_id", "subject_id", "revision", "branch_id", "system"))):
                output["gaps"].append({"status": "REFERENCE_ERROR", "artifact_id": artifact_id, "reason": "缺少实际计算口径或流派不符"})
                continue
            matched_scope = False
            for rule in self._rules.values():
                if rule.system != artifact.get("system") or rule.school_id != profile["school_id"] or TOPIC_ALIASES.get(topic, topic) not in rule.applicable_topics:
                    continue
                for scale in rule.time_scales:
                    if time_scales is not None and scale not in time_scales:
                        continue
                    matched_scope = True
                    context = {"owner_user_id": owner_user_id, "subject_id": subject_id, "revision": revision,
                               "branch_id": artifact.get("branch_id"), "time_scale": scale,
                               "target_date": artifact.get("target_date")}
                    declaration = self.declare(rule.rule_id, scoped, context, artifacts, rule.allowed_interpretations[0].interpretation_id)
                    if declaration["eligible"]:
                        claim = declaration["claim"]
                        output["scopes"][claim["claim_id"]] = {"artifact_id": artifact_id, "target_date": artifact.get("target_date"),
                                                      "stability": {ref["feature_key"]: scoped.get(rule.system + "." + ref["feature_key"], {}).get("stability", "unknown") for ref in claim["feature_refs"]}}
                        output["claims"].append(claim)
                    else:
                        output["gaps"].append({"rule_id": rule.rule_id, "artifact_id": artifact_id,
                                              "status": declaration["status"], "issues": declaration["issues"]})
            if not matched_scope:
                output["gaps"].append({"status": "RULE_GAP", "artifact_id": artifact_id,
                                      "system": artifact.get("system"), "time_scales": time_scales,
                                      "reason": "此体系、主题和时间层尚无已发布解释规则，不能挪用其他时间层"})
        return output

    def claims_for(self, result, owner, subject, revision, topic="general", time_scale="natal", target_date=None):
        """Stable application facade; plan scales resolve to explicit actual layers."""
        scales = {"natal": ["natal"], "daily": ["daily", "daily_snapshot", "daily_transit_snapshot"],
                  "monthly": ["monthly"], "yearly": ["yearly"], "decadal": ["decadal"],
                  "all": None}
        if time_scale not in scales:
            return {"claims": [], "gaps": [{"status": "RULE_GAP", "reason": "未支持的计划时间层"}]}
        if target_date is not None and any(artifact.get("target_date") != target_date for artifact in result.get("artifacts", {}).values()):
            return {"claims": [], "gaps": [{"status": "SCOPE_MISMATCH", "reason": "计算产物目标日期与计划不同"}]}
        return self.claims_for_calculation(result, owner_user_id=owner, subject_id=subject,
                                           revision=revision, topic=topic, time_scales=scales[time_scale])

    def tarot_claims(self, draw, owner, subject, revision):
        """Declare only the server-authorized, fully revealed frozen draw view.

        Call after TarotAdapter.get_for_reading(owner, draw_id). Owner and archive
        revision come from the service; a draw revision remains a separate value.
        No hidden deck, question or user context is copied into the artifact.
        """
        output = {"claims": [], "gaps": [], "artifacts": {}, "features": {},
                  "pack_version": self.pack_version, "pack_hash": self.pack_hash}

        def reject(status, reason):
            output["gaps"].append({"status": status, "reason": reason})
            return output

        if (not isinstance(owner, str) or not owner.strip() or not isinstance(subject, str)
                or not subject.strip() or type(revision) is not int or revision < 0):
            return reject("AUTH_SCOPE_ERROR", "缺少服务端人物或资料版本")
        if not isinstance(draw, dict):
            return reject("DRAW_MISMATCH", "缺少已保存的抽牌结果")
        try:
            ensure_finite_json(draw)
        except (ValueError, TypeError):
            return reject("DRAW_MISMATCH", "抽牌字段不是有限JSON数据")
        if draw.get("subject_id") != subject or ("owner_user_id" in draw and draw["owner_user_id"] != owner):
            return reject("AUTH_SCOPE_ERROR", "抽牌人物与服务端授权范围不同")
        snapshot = draw.get("context_snapshot", {})
        if not isinstance(snapshot, dict):
            return reject("DRAW_MISMATCH", "抽牌上下文快照无效")
        if draw.get("context_revoked") or snapshot.get("context_revoked"):
            return reject("AUTH_SCOPE_ERROR", "抽牌所用资料授权已撤销")
        if draw.get("status") != "ready" or type(draw.get("revision")) is not int or draw["revision"] < 1 or not isinstance(draw.get("id"), str) or not draw["id"]:
            return reject("DRAW_MISMATCH", "抽牌尚未完成或缺少持久化版本")
        from hermes.tarot_deck import SPREADS, METHOD_VERSION
        draw_source = draw.get("draw_source")
        expected_method = "manual-entry-v1" if draw_source == "manual" else METHOD_VERSION
        if (draw_source not in (None, "auto", "pick", "manual")
                or draw.get("deck_version") != self._tarot.get("deck_version")
                or draw.get("meaning_version") != self._tarot.get("meaning_version")
                or draw.get("method_version") != expected_method):
            return reject("RULE_GAP", "抽牌的牌系、牌意或方法版本未发布")
        spread_id = draw.get("spread_id")
        if not isinstance(spread_id, str) or spread_id not in SPREADS or not _same_value(draw.get("spread"), SPREADS[spread_id]):
            return reject("DRAW_MISMATCH", "冻结牌阵与发布版本不同")
        visible = draw.get("cards")
        if not isinstance(visible, list) or len(visible) != len(SPREADS[spread_id]["positions"]):
            return reject("DRAW_MISMATCH", "已翻牌数与牌阵不同")
        cards = []
        for index, selected in enumerate(visible):
            if not isinstance(selected, dict) or selected.get("revealed") is not True or type(selected.get("position")) is not int or selected["position"] != index + 1:
                return reject("DRAW_MISMATCH", "牌位尚未翻开或顺序不同")
            canonical = self._cards.get(selected.get("card_id"))
            if canonical is None or selected.get("orientation") not in ("upright", "reversed") or not _same_value(selected.get("card"), canonical):
                return reject("DRAW_MISMATCH", "稳定牌ID、方向或冻结牌意与已发布版本不符")
            if selected.get("label") != SPREADS[spread_id]["positions"][index]:
                return reject("DRAW_MISMATCH", "牌位标签与冻结牌阵不符")
            cards.append({"position": index + 1, "card_id": selected["card_id"], "orientation": selected["orientation"], "name": canonical["name"]})
        branch = "draw-" + _digest({"id": draw["id"], "draw_revision": draw["revision"]})[:24]
        context = {"owner_user_id": owner, "subject_id": subject, "revision": revision,
                   "branch_id": branch, "time_scale": "question"}
        data = {"cards": cards, "spread_id": spread_id, "deck_version": draw["deck_version"],
                "status": "finalized", "draw_id": draw["id"], "draw_revision": draw["revision"],
                "meaning_version": draw["meaning_version"], "method_version": draw["method_version"],
                "draw_source": draw_source or "auto"}
        artifact_id = "tarot-" + _digest({**context, "data": data})[:24]
        artifact = {"id": artifact_id, **context, "system": "tarot", "school_id": "zhiming-editorial-v1", "data": data}
        artifacts = {artifact_id: artifact}
        features = {"tarot." + key: {**context, "feature_key": "tarot." + key, "artifact_id": artifact_id,
                                     "path": "/data/" + key, "value": deepcopy(data[key]), "stability": "exact_input"}
                    for key in ("cards", "spread_id", "deck_version", "status")}
        output.update(artifacts=artifacts, features=features, context=context)
        for rule in self.select("tarot", topic="decision", time_scale="question", school_id="zhiming-editorial-v1"):
            declaration = self.declare(rule["rule_id"], features, context, artifacts, rule["allowed_interpretations"][0]["interpretation_id"])
            if declaration["eligible"]:
                output["claims"].append(declaration["claim"])
            else:
                output["gaps"].append({"rule_id": rule["rule_id"], "status": declaration["status"], "issues": declaration["issues"]})
        return output

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

    def revalidate_claims(self, calculation, claims, tarot_provenance=None):
        """Recheck canonical statements against server-owned calculation records.

        Scope comes from the actual artifact/profile, not a model's claim. The
        caller must pass the run's persisted calculation and frozen tarot helper
        result. No raw draw or untrusted model artifacts are accepted here.
        """
        issues = []
        if not isinstance(calculation, dict) or not isinstance(claims, list):
            return {"eligible": False, "status": "REFERENCE_ERROR", "issues": [_issue("REFERENCE_ERROR", "重验缺少服务端计算记录")]}
        records = [(calculation, False)]
        if tarot_provenance is not None:
            if not isinstance(tarot_provenance, dict):
                return {"eligible": False, "status": "REFERENCE_ERROR", "issues": [_issue("REFERENCE_ERROR", "重验缺少冻结塔罗记录")]}
            records.append((tarot_provenance, True))
        seen = set()
        for claim in claims:
            if not isinstance(claim, dict) or not isinstance(claim.get("claim_id"), str) or claim["claim_id"] in seen:
                issues.append(_issue("REFERENCE_ERROR", "声明缺少身份或重复"))
                continue
            seen.add(claim["claim_id"])
            refs = claim.get("feature_refs")
            if not isinstance(refs, list) or not refs or not isinstance(refs[0], dict):
                issues.append(_issue("REFERENCE_ERROR", "声明没有真实字段引用"))
                continue
            artifact_id = refs[0].get("artifact_id")
            if not isinstance(artifact_id, str) or not artifact_id:
                issues.append(_issue("REFERENCE_ERROR", "声明计算产物身份无效"))
                continue
            selected = [(record, tarot) for record, tarot in records
                        if isinstance(record.get("artifacts"), dict) and artifact_id in record["artifacts"]]
            if len(selected) != 1:
                issues.append(_issue("REFERENCE_ERROR", "声明计算产物不存在或有歧义"))
                continue
            record, tarot = selected[0]
            artifact = record["artifacts"][artifact_id]
            if not isinstance(artifact, dict) or not isinstance(record.get("features"), dict):
                issues.append(_issue("REFERENCE_ERROR", "产物或特征记录无效"))
                continue
            if not tarot:
                profile = record.get("profiles", {}).get(artifact.get("profile_id")) if isinstance(record.get("profiles"), dict) else None
                if not isinstance(profile, dict) or any(not _same_value(profile.get(key), artifact.get(key))
                        for key in ("owner_user_id", "subject_id", "revision", "branch_id", "system", "school_id")):
                    issues.append(_issue("REFERENCE_ERROR", "实际计算口径与产物范围不同"))
                    continue
            context = {key: artifact.get(key) for key in ("owner_user_id", "subject_id", "revision", "branch_id")}
            context.update(time_scale=claim.get("time_scale"), target_date=artifact.get("target_date"))
            features = {f["feature_key"]: f for f in record["features"].values()
                        if isinstance(f, dict) and f.get("artifact_id") == artifact_id and isinstance(f.get("feature_key"), str)}
            checked = self.validate_claim(claim, features, context, record["artifacts"])
            if not checked["eligible"]:
                issues.extend(checked["issues"])
        return {"eligible": not issues, "status": "validated" if not issues else issues[0]["code"],
                "issues": issues, "checked_claims": len(claims)}
