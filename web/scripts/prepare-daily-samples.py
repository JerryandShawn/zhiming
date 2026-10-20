"""Verify pinned synthetic P8 evidence offline and emit a closed public projection."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

COMMIT = "b51470b8e32eb72b8151df4eca7eee2e1584bee5"
PREFIX = "docs/v4/contracts/samples/daily_transit/"
OUTPUT = Path(__file__).resolve().parents[1] / "src/night/today/data"
SCHOOLS = {
    "bazi": "项目口径 · 子平五行阴阳十神算式",
    "ziwei": "安装 py-iztro 默认四化口径",
    "astro": "Swiss Moshier · 地心热带黄道 · 统一容许度",
}
PLANETS = {"太阳", "月亮", "水星", "金星", "火星", "木星", "土星", "天王", "海王", "冥王"}
GODS = {"比肩", "劫财", "食神", "伤官", "正财", "偏财", "正官", "七杀", "正印", "偏印"}


def require(condition: bool) -> None:
    if not condition:
        # Source values and parameters never enter diagnostics.
        raise ValueError("daily_public_projection_verification_failed")


def digest(value: object) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(body.encode("utf8")).hexdigest()


def read_source(path: str) -> tuple[dict, str]:
    raw = subprocess.run(["git", "show", f"{COMMIT}:{path}"], check=True, capture_output=True).stdout
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def pointer(root: object, path: str) -> object:
    require(isinstance(path, str) and path.startswith("/") and not re.search(r"~(?![01])", path))
    value = root
    for part in path[1:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            require(re.fullmatch(r"0|[1-9][0-9]*", key) is not None and int(key) < len(value))
            value = value[int(key)]
        else:
            require(isinstance(value, dict) and key in value)
            value = value[key]
    return value


def verify_alias(root: dict, row: dict) -> None:
    value_hash = digest(pointer(root, row["path"]))
    require(value_hash == row["value_sha256"])
    require(row["claim_id"] == "claim-" + digest([root["document_id"], row["path"], value_hash]))


def verify(root: dict, entry: dict) -> None:
    require(root["version"] == "p8-daily-transit-v1")
    require(root["effects"] == {"model_calls": 0, "writes": 0, "alias_registry": "ephemeral_only"})
    require(root["data"]["date"] == entry["date"] and root["document_id"] == entry["document_id"])
    body = {key: root[key] for key in ["version", "scope", "data", "rule_hits", "sources"]}
    require(root["document_id"] == "tool-" + digest(body))
    require(len(root["rule_hits"]) == entry["hits"] and len(root["aliases"]["c"]) == entry["c"])
    require(len(root["aliases"]["r"]) == entry["r"] == len(root["rule_hits"]))
    paths = sorted({path for hit in root["rule_hits"] for path in hit["evidence_paths"]})
    require(len(paths) == len(root["aliases"]["c"]))
    names = {}
    for number, (path, row) in enumerate(zip(paths, root["aliases"]["c"], strict=True), 1):
        require(path.startswith("/data/") and row["path"] == path and row["alias"] == f"c{number}")
        verify_alias(root, row)
        names[path] = row["alias"]
    for index, (hit, row) in enumerate(zip(root["rule_hits"], root["aliases"]["r"], strict=True)):
        require(hit["met"] is True and bool(hit["school"]) and bool(hit["source"]))
        require(row["alias"] == f"r{index + 1}" and row["path"] == f"/rule_hits/{index}")
        require(row["rule_id"] == hit["rule_id"])
        require(row["evidence_aliases"] == [names[path] for path in hit["evidence_paths"]])
        verify_alias(root, row)
    date = entry["date"]
    expected = datetime.fromisoformat(date + "T04:00:00+00:00")
    require(datetime.fromisoformat(root["data"]["snapshot_at_utc"].replace("Z", "+00:00")) == expected)
    require(datetime.fromisoformat(root["data"]["snapshot_at"]) == expected)
    require(root["data"]["time_basis"]["primary"]["basis"] == "true_solar")


def describe_hit(hit: dict, day: dict) -> tuple[str, str]:
    context = hit["context"]
    system, kind = context["system"], context["kind"]
    if system == "bazi" and kind == "ten_god":
        require(context["layer"] == "daily" and context["ten_god"] in GODS)
        require(context["ten_god"] == day["stem_ten_god"])
        return "八字 · 今日盘面", f"{day['ganzhi']}日，流干相对本命日干为{context['ten_god']}。这是传统结构标签，现实安排仍由你决定。"
    if system == "ziwei" and kind == "mutagen":
        require(context["layer"] == "daily" and context["mutagen"] in ["禄", "权", "科", "忌"])
        require(context["natal_palace"] in ["命宫", "兄弟", "夫妻", "子女", "财帛", "疾厄", "迁移", "仆役", "官禄", "田宅", "福德", "父母"])
        return "紫微 · 流日四化", f"流日化{context['mutagen']}落入本命{context['natal_palace']}宫。宫名是盘面标签，不据此判断关系或现实事件。"
    require(system == "astro" and kind == "aspect")
    require(context["from"] in PLANETS and context["to"] in PLANETS)
    require(context["aspect"] in ["合相", "六合", "刑相", "拱相", "冲相"])
    require(context["orb_limit"] == 2 and 0 <= context["orb_degrees"] <= 2)
    return "星象 · 正午快照", (
        f"行运{context['from']}与本命{context['to']}{context['aspect']}，"
        f"实际误差{context['orb_degrees']:.2f}°，容许度{context['orb_limit']:g}°。只展示一个瞬间，不代表整天。"
    )


def evidence_summary(root: dict, path: str) -> str:
    value = pointer(root, path)
    if path == "/data/bazi/snapshot/day":
        return f"当日{value['ganzhi']} · 流干十神{value['stem_ten_god']}"
    if path == "/data/bazi/natal_pillars/day":
        return "本命日柱参与十神比对；出生原始资料不进入晨报。"
    if path.startswith("/data/ziwei/horoscope/daily/mutagen/"):
        require(isinstance(value, str) and re.fullmatch(r"[\u3400-\u9fff]{1,6}", value) is not None)
        return f"流日四化关联星曜：{value}"
    if path.startswith("/data/ziwei/natal/palaces/"):
        name = value.get("name")
        require(isinstance(name, str) and re.fullmatch(r"[\u3400-\u9fff]{1,6}", name) is not None)
        return f"本命宫位中已解析的星曜：{name}"
    if path.startswith("/data/astro/aspects/"):
        require(value["from"] in PLANETS and value["to"] in PLANETS)
        return f"{value['from']}与{value['to']}{value['aspect']} · 误差{value['orb_degrees']:.2f}°"
    if path == "/data/astro/orb_limit_degrees":
        require(value == 2)
        return f"本次统一容许度：{value:g}°"
    require(re.fullmatch(r"/data/astro/(natal|transit)_planets/[^/]+/longitude", path) is not None)
    planet = path.split("/")[-2]
    require(planet in PLANETS and isinstance(value, (int, float)) and 0 <= value < 360)
    label = "本命" if "/natal_planets/" in path else "行运"
    return f"{label}{planet}黄经：{value:.2f}°"


def project(root: dict, entry: dict, source_hash: str) -> dict:
    data, day = root["data"], root["data"]["bazi"]["snapshot"]["day"]
    require(re.fullmatch(r"[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]", day["ganzhi"]) is not None)
    hits = list(enumerate(root["rule_hits"]))
    selected = [next((index, hit) for index, hit in hits if hit["context"].get("layer") == "daily" and hit["context"]["kind"] == "ten_god")]
    selected.append(next((index, hit) for index, hit in hits if hit["context"].get("layer") == "daily" and hit["context"]["kind"] == "mutagen"))
    aspects = [(index, hit) for index, hit in hits if hit["context"]["kind"] == "aspect"]
    require(bool(aspects))
    selected.append(next(((index, hit) for index, hit in aspects if hit["context"]["from"] == "月亮"), aspects[0]))
    refs, highlights, evidence = {}, [], []
    chart_aliases = {row["alias"]: row for row in root["aliases"]["c"]}
    for index, hit in selected:
        title, summary = describe_hit(hit, day)
        alias = root["aliases"]["r"][index]
        names = [alias["alias"], *alias["evidence_aliases"]]
        bindings = [{"date": entry["date"], "documentId": root["document_id"], "alias": name} for name in names]
        highlights.append({"id": hit["rule_id"], "system": hit["context"]["system"], "title": title, "summary": summary, "school": SCHOOLS[hit["context"]["system"]], "refs": bindings})
        for binding in bindings:
            name = binding["alias"]
            if name in refs:
                continue
            refs[name] = binding
            evidence.append({"ref": binding, "label": f"{name} · {'规则依据' if name.startswith('r') else '盘面依据'}", "summary": summary if name.startswith("r") else evidence_summary(root, chart_aliases[name]["path"])})
    snapshot = datetime.fromisoformat(data["snapshot_at_utc"].replace("Z", "+00:00")).astimezone(timezone(timedelta(hours=8))).isoformat()
    return {
        "date": entry["date"], "documentId": root["document_id"], "snapshotAtBeijing": snapshot,
        "basis": "true_solar", "hasBeijingComparison": bool(data["time_basis"]["comparisons"]),
        "dayGanzhi": day["ganzhi"], "dayTenGod": day["stem_ten_god"],
        "highlights": highlights, "evidence": evidence,
        "limits": ["合成人物阿远的本机实际引擎样例，未接入你的资料。", "北京时间12:00的单点快照；仅选列部分实际命中，不是全天或择时结论。", "传统条件与数值相位不证明现实预测有效；现实安排优先。"],
        "provenance": {
            "sourceCommit": COMMIT, "sourceFile": PREFIX + entry["file"], "sourceSha256": source_hash,
            "mode": "published-synthetic-engine", "contractStatus": "aligned" if data["snapshot_at"] == snapshot else "offset_normalized",
            "integrity": "document-and-alias-digests-verified",
        },
    }


def main() -> None:
    manifest, manifest_hash = read_source(PREFIX + "manifest.json")
    require(manifest["mode"] == "scripted_synthetic_actual_engine" and manifest["real_model_requests"] == 0)
    entries, outputs = manifest["files"], []
    require([entry["date"] for entry in entries] == [f"2026-10-{day}" for day in range(21, 28)])
    # Verify the entire batch before emitting any browser-visible projection.
    for entry in entries:
        source, source_hash = read_source(PREFIX + entry["file"])
        verify(source, entry)
        outputs.append(project(source, entry, source_hash))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for value in outputs:
        (OUTPUT / f"{value['date']}.json").write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    provenance = {"sourceCommit": COMMIT, "sourceManifestSha256": manifest_hash, "files": [{"date": item["date"], "documentId": item["documentId"], **item["provenance"]} for item in outputs], "realModelRequests": 0, "rawBirthExported": False, "scopeExported": False}
    (OUTPUT / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"verified_documents": len(outputs), "public_files": len(outputs) + 1, "real_model_requests": 0}))


if __name__ == "__main__":
    main()
