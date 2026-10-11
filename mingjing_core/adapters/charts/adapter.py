"""Source-scoped deterministic features and honest, bounded time sampling."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

from ...domain.calculation import CalculationArtifact, CalculationFeature, CalculationProfile, TimeBranch
from ...domain.json_values import ensure_finite_json


SCHOOLS = {"bazi": "ziping-yueling-v1", "ziwei": "sanhe-structure-v1",
           "astro": "tropical-major-aspects-v1"}
ROOT = Path(__file__).resolve().parents[3]
SAMPLE_WARNING = "出生时间分支仅为有限采样；采样内一致不证明连续区间完整稳定"


def stable_id(prefix, value):
    digest = hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":"), allow_nan=False).encode()).hexdigest()[:24]
    return prefix + digest


def parse_datetime(value):
    if not isinstance(value, str):
        raise ValueError("出生民用时间必须为明确日期时间")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?", value.strip()):
        raise ValueError("出生民用时间必须明确到分钟；只有日期不能补为已知午夜")
    parsed = datetime.fromisoformat(value.strip())
    if parsed.tzinfo is not None:
        raise ValueError("出生时间应为民用时间，时区偏移另填；不允许重复转换")
    if parsed.second or parsed.microsecond:
        raise ValueError("当前计算引擎精度为分钟，不能静默截断秒")
    return parsed


def validated_number(value, field, lower, upper, exclusive=False):
    if isinstance(value, bool) or value is None:
        raise ValueError("缺少已提供的" + field)
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(field + "无效") from None
    if not math.isfinite(number) or not (lower < number < upper if exclusive else lower <= number <= upper):
        raise ValueError(field + "超出范围")
    return number


class ChartAdapter:
    def __init__(self, owner_user_id, python=None, runner=None, *, timeout=45):
        if not isinstance(owner_user_id, str) or not owner_user_id:
            raise ValueError("owner_user_id is required")
        self.owner_user_id = owner_user_id
        self.python = python or os.environ.get("CHART_PYTHON") or sys.executable
        self.runner = runner or self._run
        self.timeout = validated_number(timeout, "计算超时秒数", 1, 120)

    def _run(self, system, args):
        process = subprocess.run([self.python, "-X", "utf8", str(Path(__file__).with_name("worker.py"))],
                                  input=json.dumps({"system": system, "args": args}, allow_nan=False),
                                  capture_output=True, encoding="utf-8", timeout=self.timeout)
        if process.returncode:
            # Keep raw stderr out of user responses: it may contain birth values.
            kind = "missing_chart_dependency" if "ModuleNotFoundError" in process.stderr else "chart_engine_failure"
            raise RuntimeError(kind)
        if len(process.stdout) > 8_000_000:
            raise RuntimeError("chart_output_limit_exceeded")
        value = json.loads(process.stdout)
        ensure_finite_json(value)
        return value

    def run(self, archive, date, requested_systems, revision, subject):
        """Synchronous pure calculation entrypoint; async callers use a worker thread."""
        return self.calculate(archive, date, requested_systems, revision, subject)

    def _branches(self, birth, subject_id, revision):
        timing = birth.get("time", {}) if isinstance(birth.get("time"), dict) else {}
        precision = timing.get("precision", birth.get("time_precision", birth.get("precision")))
        nominal = birth.get("solar_datetime", timing.get("civil_datetime"))
        uncertainty = birth.get("time_uncertainty_minutes", timing.get("uncertainty_minutes"))
        interval = birth.get("time_interval", timing.get("interval"))
        if birth.get("time_unknown"):
            precision = "unknown"
        if precision is None:
            precision = "approximate" if uncertainty else "exact" if nominal else "unknown"
        if precision not in ("exact", "approximate", "interval", "unknown"):
            raise ValueError("出生时间精度必须为 exact/approximate/interval/unknown")
        sampling_range = None
        if precision == "exact":
            if uncertainty not in (None, 0, 0.0, "0"):
                raise ValueError("exact出生时间与非零误差范围冲突，需明确采用的精度")
            points = [parse_datetime(nominal)]
        elif precision == "approximate":
            center = parse_datetime(nominal)
            delta = validated_number(uncertainty, "出生时间误差分钟", 0, 1440)
            if delta == 0:
                raise ValueError("approximate出生时间需要大于0的误差范围")
            # Keep minute precision explicit. The input must not claim a
            # precision the legacy minute engines cannot represent.
            if not delta.is_integer():
                raise ValueError("当前计算引擎仅支持整分钟出生时间误差")
            left, right = center - timedelta(minutes=delta), center + timedelta(minutes=delta)
            points = [left, center, right]
            sampling_range = {"start": left.strftime("%Y-%m-%d %H:%M"),
                              "end": right.strftime("%Y-%m-%d %H:%M"), "inclusive": True}
        elif precision == "interval":
            if not isinstance(interval, dict):
                raise ValueError("interval出生时间需要time_interval.start/end")
            left, right = parse_datetime(interval.get("start")), parse_datetime(interval.get("end"))
            minutes = int((right - left).total_seconds() / 60)
            if minutes <= 0 or minutes > 48 * 60:
                raise ValueError("出生时间区间须大于0且不超过48小时")
            points = sorted({left + timedelta(minutes=round(minutes * fraction / 4))
                             for fraction in range(5)})
            sampling_range = {"start": left.strftime("%Y-%m-%d %H:%M"),
                              "end": right.strftime("%Y-%m-%d %H:%M"), "inclusive": True}
        else:
            date = birth.get("solar_date", timing.get("date"))
            if not date and isinstance(nominal, str):
                date = nominal[:10]
            if not date:
                raise ValueError("出生时刻未知且缺少可计算的阳历出生日期")
            day = datetime.strptime(date, "%Y-%m-%d")
            # Candidate sample instants, not a fabricated confirmed noon time.
            points = [day.replace(hour=hour) for hour in (0, 6, 12, 18, 23)]
            sampling_range = {"start": day.strftime("%Y-%m-%d 00:00"),
                              "end": day.strftime("%Y-%m-%d 23:59"), "inclusive": True}
        output = []
        for point in points:
            civil = point.strftime("%Y-%m-%d %H:%M")
            ident = stable_id("time-", [self.owner_user_id, subject_id, revision, precision, civil, sampling_range])
            output.append(TimeBranch(id=ident, owner_user_id=self.owner_user_id,
                subject_id=subject_id, revision=revision, input_precision=precision,
                civil_datetime=civil, coverage="exact_input" if precision == "exact" else "sampled_not_continuous",
                confirmed_birth_time=precision == "exact" and birth.get("confirmation_status") == "confirmed",
                sampling_range=sampling_range,
                warnings=[] if precision == "exact" else [SAMPLE_WARNING]).model_dump())
        return output

    def calculate(self, archive, date, requested_systems, revision, subject):
        result = {"artifacts": {}, "features": {}, "profiles": {}, "branches": [], "errors": []}
        subject_id = subject.get("id", subject.get("subject_id")) if isinstance(subject, dict) else subject
        claimed_owner = subject.get("owner_user_id", self.owner_user_id) if isinstance(subject, dict) else self.owner_user_id
        if claimed_owner != self.owner_user_id or not isinstance(subject_id, str) or not subject_id:
            result["errors"].append({"code": "AUTH_SCOPE_ERROR", "reason": "人物归属不匹配"})
            return result
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise ValueError("revision must be a nonnegative integer")
        if not isinstance(archive, dict):
            raise ValueError("archive must be an authorized profile mapping")
        try:
            ensure_finite_json(archive)
        except ValueError:
            result["errors"].append({"code": "MISSING_INPUT", "reason": "出生资料含非有限数值或不支持的数据类型"})
            return result
        tagged_owner = archive.get("owner_user_id", archive.get("owner"))
        tagged_subject = archive.get("subject_id")
        if tagged_owner not in (None, self.owner_user_id) or tagged_subject not in (None, subject_id):
            result["errors"].append({"code": "AUTH_SCOPE_ERROR", "reason": "档案归属不匹配"})
            return result
        if not isinstance(date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            raise ValueError("target date must be YYYY-MM-DD")
        datetime.strptime(date, "%Y-%m-%d")
        if not isinstance(requested_systems, (list, tuple, set)):
            raise ValueError("requested_systems must be a sequence")
        if any(not isinstance(system, str) for system in requested_systems):
            raise ValueError("requested_systems entries must be named capabilities")
        requested = list(dict.fromkeys(requested_systems))
        systems = [system for system in requested if system in SCHOOLS]
        for unknown in requested:
            if unknown not in SCHOOLS:
                result["errors"].append({"code": "RULE_GAP", "system": str(unknown), "reason": "未实现的计算体系"})
        if not systems:
            return result
        user = archive.get("user", {})
        if not isinstance(user, dict):
            result["errors"].append({"code": "MISSING_INPUT", "reason": "人物档案结构无效"})
            return result
        birth = user.get("birth", {})
        if not isinstance(birth, dict):
            result["errors"].append({"code": "MISSING_INPUT", "reason": "缺少出生资料"})
            return result
        try:
            branches = self._branches(birth, subject_id, revision)
        except (ValueError, TypeError) as error:
            result["errors"].append({"code": "MISSING_INPUT", "reason": str(error)})
            return result
        result["branches"] = branches
        location = birth.get("location", {})
        if not isinstance(location, dict):
            result["errors"].append({"code": "MISSING_INPUT", "reason": "出生地点结构无效"})
            return result
        for system in systems:
            try:
                lng = validated_number(location.get("lng"), "出生地经度", -180, 180)
                tz = validated_number(birth.get("timezone_offset", location.get("timezone_offset")),
                                      "出生时UTC偏移（含当时夏令时）", -14, 14)
                lat = validated_number(location.get("lat"), "出生地纬度", -90, 90, exclusive=True) if system == "astro" else None
                gender = user.get("gender")
                if system in ("bazi", "ziwei") and gender not in ("男", "女"):
                    raise ValueError("缺少大运/紫微引擎所需且已明确提供的性别计算参数")
                if birth.get("calendar", "solar") not in ("solar", "gregorian", "阳历"):
                    raise ValueError("本适配器需要已转换且有来源的阳历日期；不猜测阴历或闰月")
            except (ValueError, TypeError) as error:
                result["errors"].append({"code": "MISSING_INPUT", "system": system, "reason": str(error)})
                continue
            for branch in branches:
                args = {"datetime": branch["civil_datetime"], "lng": lng, "tz": tz, "date": date}
                if system in ("bazi", "ziwei"):
                    args["gender"] = gender
                if system == "astro":
                    args["lat"] = lat
                try:
                    raw = deepcopy(self.runner(system, args))
                    ensure_finite_json(raw)
                    if not isinstance(raw, dict):
                        raise ValueError("calculation runner did not return an object")
                    data = raw.get("data", raw)
                    metadata = raw.get("metadata", {})
                    if not isinstance(data, dict) or not isinstance(metadata, dict):
                        raise ValueError("invalid calculation artifact")
                    self._attach(system, data, metadata, birth, args, branch, result, date, revision, subject_id,
                                  {"education": "study"}.get(archive.get("calculation_topic"), archive.get("calculation_topic", "general")))
                except (RuntimeError, ValueError, TypeError, KeyError, IndexError, OSError, subprocess.SubprocessError) as error:
                    result["errors"].append({"code": "CALCULATION_ERROR", "system": system,
                        "branch_id": branch["id"], "reason": str(error)[:240],
                        "requested_method": self._requested_method(system), "actual_method": None,
                        "fallback": [], "warnings": ["计算失败，未静默改宫制、改出生时间或返回另一张盘"]})
        self._stability(result)
        return result

    @staticmethod
    def _requested_method(system):
        return {"bazi": {"year_month": "UTC+8_exact_jie_boundary", "day_hour": "local_mean_solar_time",
                          "equation_of_time": False, "day_sect": 2, "dayun_sect": 1},
                "ziwei": {"calendar": "py_iztro_by_solar_defaults", "time": "local_mean_solar_time",
                           "links": "two_trines_and_opposition", "equation_of_time": False},
                "astro": {"ephemeris": "Moshier", "houses": "Placidus", "zodiac": "tropical",
                           "natal_aspect_orb": 6, "transit_aspect_orb": 2,
                           "transit_snapshot_timezone_offset": 8}}[system]

    def _attach(self, system, data, metadata, birth, args, branch, result, date, revision, subject_id, topic):
        # Method changes, source changes and fact revisions all change IDs.
        hashes = {system + ".py": hashlib.sha256((ROOT / "hermes" / (system + ".py")).read_bytes()).hexdigest(),
                  "core_chart_adapter.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  "core_chart_worker.py": hashlib.sha256(Path(__file__).with_name("worker.py").read_bytes()).hexdigest()}
        warnings = list(dict.fromkeys(branch["warnings"] + metadata.get("warnings", []) +
            data.get("quality", {}).get("limitations", [])))
        input_status = birth.get("input_status", {})
        if not input_status:
            warnings.append("出生参数的字段确认状态未在此档案提供；适配器不会把已有值升级为已确认事实")
        actual_method = metadata.get("actual_method", data.get("method", {}))
        if not actual_method:
            raise ValueError("计算引擎没有报告实际计算口径")
        if system == "ziwei":
            self._validate_ziwei(data)
            topic_names = {"general": "命", "career": "官禄", "study": "官禄", "relationships": "夫妻",
                           "finance": "财帛", "family": "父母", "home": "田宅", "health": "疾厄"}
            topic_names.update(decision="命", terminology="命", personal_growth="福德")
            if topic not in topic_names:
                raise ValueError("紫微主题未在确定性宫位映射中声明")
            selected = [palace for palace in data["palaces"]
                        if palace["name"].removesuffix("宫") == topic_names[topic]]
            if len(selected) != 1:
                raise ValueError("紫微主题无法对应唯一真实宫位")
            # Keep the three linked nodes complete, and preserve every other
            # palace separately for any subsequent read-only field request.
            data["topic_palace"] = deepcopy(selected[0])
            data["selected_topic"] = {"topic": topic, "palace_name": selected[0]["name"],
                                      "mapping_version": "topic-palace-selection-v1",
                                      "scope": "选择结构视角，不是现实事件或人生结果断言"}
        if system == "bazi":
            self._derive_bazi(data)
        if system == "astro":
            self._validate_aspects(data)
        profile_id = stable_id("profile-", [self.owner_user_id, subject_id, revision, branch["id"],
                                             system, args, birth, actual_method, hashes,
                                             metadata.get("versions", {}), metadata.get("fallback", [])])
        profile = CalculationProfile(id=profile_id, system=system, school_id=SCHOOLS[system],
            owner_user_id=self.owner_user_id, subject_id=subject_id, revision=revision,
            branch_id=branch["id"], input={"declared_birth": deepcopy(birth),
                "sample_civil_datetime": args["datetime"], "sample_is_confirmed": branch["confirmed_birth_time"],
                "longitude": args["lng"], "latitude": args.get("lat"), "timezone_offset": args["tz"],
                "gender_parameter": args.get("gender"), "calendar": "solar", "input_status": input_status,
                "target_date": date}, requested_method=self._requested_method(system),
            actual_method=actual_method, versions=dict(metadata.get("versions", {}), source_sha256=hashes),
            warnings=warnings, fallback=metadata.get("fallback", [])).model_dump()
        artifact_id = stable_id("chart-", [profile_id, date, data])
        artifact = CalculationArtifact(id=artifact_id, system=system, school_id=SCHOOLS[system], owner_user_id=self.owner_user_id,
            subject_id=subject_id, revision=revision, branch_id=branch["id"], profile_id=profile_id,
            time_scale="natal_with_explicit_separate_target_layers", target_date=date,
            data=data, warnings=warnings).model_dump()
        pending_features = {}
        for key, path, scale in self._feature_paths(system, data):
            value = data
            for step in path.split("/")[2:]:
                value = value[step]
            feature_key = system + "." + key
            ident = feature_key + "@" + branch["id"]
            feature = CalculationFeature(id=ident, feature_key=feature_key, value=deepcopy(value),
                artifact_id=artifact_id, path=path, owner_user_id=self.owner_user_id, subject_id=subject_id,
                revision=revision, branch_id=branch["id"], time_scale=scale,
                stability="exact_input" if branch["coverage"] == "exact_input" else "unknown").model_dump()
            pending_features[ident] = feature
        # Publish a whole branch atomically only after all fields pass validation.
        result["profiles"][profile_id] = profile
        result["artifacts"][artifact_id] = artifact
        result["features"].update(pending_features)
        branch["artifact_ids"].append(artifact_id)
        branch["feature_ids"].extend(pending_features)

    @staticmethod
    def _feature_paths(system, data):
        if system == "bazi":
            natal = ["pillars", "day_master", "method", "hidden_stems", "ten_gods", "month_command",
                     "root_and_exposed_stems", "relations", "wuxing_count", "dayun"]
            paths = [(key, "/data/" + key, "natal" if key != "dayun" else "decadal")
                     for key in natal if key in data]
            paths += [(key, "/data/" + key, scale) for key, scale in
                      (("day", "daily_snapshot"), ("target_liuyue", "monthly_samples_and_exact_jie_intervals"),
                        ("target_liunian", "yearly_samples"), ("target_month", "monthly"),
                        ("target_year", "yearly")) if key in data]
        elif system == "ziwei":
            paths = [(key, "/data/" + key, "natal") for key in ("topic_palace", "palaces", "method", "wuxing_ju") if key in data]
            paths += [("horoscope." + key, "/data/horoscope/" + key, key)
                      for key in ("decadal", "yearly", "monthly", "daily") if key in data.get("horoscope", {})]
        else:
            paths = [(key, "/data/" + key, "natal") for key in
                     ("planets", "aspects", "aspect_orb", "houses", "asc", "mc", "method") if key in data]
            paths += [("calculation_flags." + layer, "/data/calculation_flags/" + layer, scale)
                      for layer, scale in (("natal", "natal"), ("transit_snapshot", "daily_transit_snapshot"))
                      if layer in data.get("calculation_flags", {})]
            if "transits" in data:
                paths.append(("transits", "/data/transits", "daily_transit_snapshot"))
            if "transit_method" in data:
                paths.append(("transit_method", "/data/transit_method", "daily_transit_snapshot"))
        return paths

    @staticmethod
    def _derive_bazi(data):
        pillars = data.get("pillars", {})
        if set(pillars) != {"year", "month", "day", "hour"}:
            raise ValueError("八字四柱不完整")
        day_master = data.get("day_master")
        if not day_master or pillars["day"].get("gan") != day_master:
            raise ValueError("日主与日柱天干不一致")
        hidden = {"子": ["癸"], "丑": ["己", "癸", "辛"], "寅": ["甲", "丙", "戊"],
                  "卯": ["乙"], "辰": ["戊", "乙", "癸"], "巳": ["丙", "戊", "庚"],
                  "午": ["丁", "己"], "未": ["己", "丁", "乙"], "申": ["庚", "壬", "戊"],
                  "酉": ["辛"], "戌": ["戊", "辛", "丁"], "亥": ["壬", "甲"]}
        elements = dict(zip("甲乙丙丁戊己庚辛壬癸", ["木", "木", "火", "火", "土", "土", "金", "金", "水", "水"]))
        expected_hidden = {name: hidden[pillar["zhi"]] for name, pillar in pillars.items()}
        if "hidden_stems" in data and data["hidden_stems"] != expected_hidden:
            raise ValueError("藏干字段与当前适配器声明的表定义不一致")
        data["hidden_stems"] = expected_hidden
        data["month_command"] = {"branch": pillars["month"]["zhi"],
                                   "principal_hidden_stem": hidden[pillars["month"]["zhi"]][0],
                                   "pillar": deepcopy(pillars["month"])}
        # The production worker adds every hidden stem's ten-god from LunarUtil.
        # A runner exposing only legacy pillar fields cannot claim that extra
        # coverage; keep its principal stem detail explicit.
        if "ten_gods" not in data:
            data["ten_gods"] = {name: {"exposed": pillar.get("shishen_gan"),
                                         "branch_principal": pillar.get("shishen_zhi")}
                                for name, pillar in pillars.items()}
        data["root_and_exposed_stems"] = {"same_element_hidden_stem_locations": [
            {"pillar": name, "hidden_stem": stem, "same_stem": stem == day_master}
            for name, stems in data["hidden_stems"].items() for stem in stems
            if elements[stem] == elements[day_master]],
            "exposed_stems": {name: pillar["gan"] for name, pillar in pillars.items()},
            "precision_note": "记录原始通根线索，不给力量权重、旺衰或格局定论"}
        clashes = {frozenset(pair) for pair in ("子午", "丑未", "寅申", "卯酉", "辰戌", "巳亥")}
        combinations = {frozenset(pair) for pair in ("子丑", "寅亥", "卯戌", "辰酉", "巳申", "午未")}
        stem_combinations = {frozenset(pair) for pair in ("甲己", "乙庚", "丙辛", "丁壬", "戊癸")}
        pairs = []
        entries = list(pillars.items())
        for index, (left, p) in enumerate(entries):
            for right, q in entries[index + 1:]:
                relation = []
                if frozenset((p["zhi"], q["zhi"])) in clashes:
                    relation.append("六冲")
                if frozenset((p["zhi"], q["zhi"])) in combinations:
                    relation.append("六合")
                if frozenset((p["gan"], q["gan"])) in stem_combinations:
                    relation.append("天干五合")
                if relation:
                    pairs.append({"from": left, "to": right, "relations": relation,
                                  "ganzhi": [p["ganzhi"], q["ganzhi"]], "transformation_asserted": False})
        data["relations"] = {"pair_relations": pairs, "supported": ["六冲", "六合", "天干五合"],
                             "not_implemented": ["合化成立判定", "刑害破权重", "格局", "调候", "完整旺衰", "用神判定"]}
        # The legacy heuristic remains auditable in engine raw data but is
        # explicitly barred from the public feature/knowledge interface.
        if "xiyongshen" in data:
            data["legacy_heuristic_not_for_interpretation"] = data.pop("xiyongshen")

    @staticmethod
    def _validate_ziwei(data):
        palaces = data.get("palaces", [])
        if len(palaces) != 12 or {p.get("index") for p in palaces} != set(range(12)):
            raise ValueError("紫微必须具有完整且唯一的12宫索引")
        by_index = {p["index"]: p for p in palaces}
        for p in palaces:
            links = p.get("linked_palaces", [])
            expected = [(p["index"] + offset) % 12 for offset in (4, 8, 6)]
            if [link.get("index") for link in links] != expected:
                raise ValueError("紫微三方四正索引不匹配")
            for link in links:
                actual = by_index[link["index"]]
                if any(link.get(key) != actual.get(key) for key in ("name", "ganzhi", "major", "minor")):
                    raise ValueError("紫微关联宫位内容与实际宫不一致")

    @staticmethod
    def _validate_aspects(data):
        planets = data.get("planets", {})
        if not isinstance(planets, dict) or not planets:
            raise ValueError("缺少实际天体位置")
        for position in planets.values():
            validated_number(position.get("longitude"), "天体黄经", 0, 360)
        limit = data.get("aspect_orb")
        if isinstance(limit, bool) or not isinstance(limit, (float, int)) or not math.isfinite(limit) or limit < 0:
            raise ValueError("缺少实际相位容许度")
        angles = {"合相": 0, "六合": 60, "刑相": 90, "拱相": 120, "冲相": 180}
        for aspect in data.get("aspects", []):
            p, q = planets[aspect["from"]], planets[aspect["to"]]
            for position in (p, q):
                validated_number(position.get("longitude"), "天体黄经", 0, 360)
            separation = abs((p["longitude"] - q["longitude"] + 180) % 360 - 180)
            angle = angles.get(aspect.get("aspect"))
            if angle is None or aspect.get("angle") != angle:
                raise ValueError("相位角与相位定义不一致")
            orb = round(abs(separation - angle), 3)
            validated_number(aspect.get("orb"), "相位误差", 0, 180)
            if abs(orb - aspect["orb"]) > .002 or orb > limit + .002:
                raise ValueError("相位orb与真实天体位置不一致")
        transit = data.get("transits", {})
        if "aspects_to_natal" in transit:
            moving = transit.get("planets", {})
            transit_limit = validated_number(transit.get("orb_limit"), "行运容许度", 0, 180)
            for aspect in transit["aspects_to_natal"]:
                p, q = moving[aspect["from"]], planets[aspect["to"]]
                for position in (p, q):
                    validated_number(position.get("longitude"), "行运天体黄经", 0, 360)
                angle = angles.get(aspect.get("aspect"))
                if angle is None or aspect.get("angle") != angle:
                    raise ValueError("行运相位名称与角度不符")
                expected = round(abs(abs((p["longitude"] - q["longitude"] + 180) % 360 - 180) - angle), 3)
                observed = validated_number(aspect.get("orb"), "行运相位误差", 0, 180)
                if abs(expected - observed) > .002 or expected > transit_limit + .002:
                    raise ValueError("行运相位orb与真实天体位置不一致")

    @staticmethod
    def _stability(result):
        grouped = {}
        for feature in result["features"].values():
            grouped.setdefault(feature["feature_key"], []).append(feature)
        for entries in grouped.values():
            if all(entry["stability"] == "exact_input" for entry in entries):
                continue
            # Any failed branch prevents even a claim of stable *all samples*.
            complete = len(entries) == len(result["branches"])
            same = all(entry["value"] == entries[0]["value"] for entry in entries)
            for entry in entries:
                entry["stability"] = "sampled_stable" if complete and same else "conditional"


# Both spellings use the same implementation, never a legacy controller.
ChartsAdapter = ChartAdapter
