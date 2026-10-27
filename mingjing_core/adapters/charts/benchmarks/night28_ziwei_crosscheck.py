"""Offline crosscheck of actual daily transformations against a separate path."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import platform
import random
from collections import Counter
from datetime import date, timedelta, timezone
from pathlib import Path
from typing import Any

from ....timekit.clock import get_clock
from ..daily_transit import prepare_natal
from ..daily_transit_ziwei import ziwei_day
from ..tool_evidence import content_hash
from ..worker import iztro_provenance, version
from .daily_transit_samples import sample_natal
from .handoff_offline import offline_runtime
from .night28_ziwei_reference import (
    ANCHOR,
    TABLE,
    day_ganzhi,
    independent_links,
    pinned_table,
)

SEED = 20261020


def target_days() -> list[date]:
    rng = random.Random(SEED)
    first, end = date(1986, 1, 1), date(1992, 1, 1)
    days = {date(2026, 10, day) for day in range(21, 28)}
    days.update((date(1988, 2, 29), date(1986, 5, 4), date(1991, 9, 15)))
    while len(days) < 1000:
        days.add(first + timedelta(days=rng.randrange((end - first).days)))
    return sorted(days)


def research_natal() -> dict[str, Any]:
    natal = sample_natal()
    natal.update(
        owner_user_id="synthetic-reference-owner",
        subject_id="synthetic-reference-subject-1980",
        operation_id="synthetic-reference-daily-crosscheck",
    )
    natal["birth"]["date"] = "1980-03-12"
    return natal


def _normalize(links: list[dict]) -> list[dict]:
    return [
        {
            "mutagen": row["mutagen"],
            "star": row["star"],
            "status": row["status"],
            "locations": [
                {key: item[key] for key in ("palace_index", "natal_palace")}
                for item in row["locations"]
            ],
        }
        for row in links
    ]


def compare_days(prepared: Any, days: list[date]) -> dict[str, Any]:
    if len(days) != len(set(days)):
        raise ValueError("reference_duplicate_target_dates")
    differences, stems = [], Counter()
    for value in days:
        actual = ziwei_day(prepared, value.isoformat())
        links = _normalize(actual["transformations"]["daily"]["links"])
        expected = independent_links(prepared.ziwei_ast, value)
        ganzhi = actual["horoscope"]["daily"]["ganzhi"]
        stems[day_ganzhi(value)[0]] += 1
        if ganzhi != day_ganzhi(value) or links != expected:
            differences.append(
                {
                    "date": value.isoformat(),
                    "actual_ganzhi": ganzhi,
                    "reference_ganzhi": day_ganzhi(value),
                    "actual": links,
                    "reference": expected,
                }
            )
    return {
        "dates": len(days),
        "stem_coverage": dict(stems),
        "differences": differences,
        "difference_count": len(differences),
        "target_dates_sha256": hashlib.sha256(
            json.dumps([day.isoformat() for day in days]).encode()
        ).hexdigest(),
        "target_year_counts": dict(Counter(str(day.year) for day in days)),
    }


def _code_provenance() -> dict[str, str]:
    files = [Path(__file__), Path(inspect.getfile(independent_links))]
    files += [Path(inspect.getfile(ziwei_day)), Path(inspect.getfile(content_hash))]
    return {
        path.name: hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for path in files
    }


def run_crosscheck() -> dict[str, Any]:
    platform.system()
    with offline_runtime():
        natal, days = research_natal(), target_days()
        prepared = prepare_natal(natal, days[0].isoformat())
        lunar = prepared.bazi_engine.Solar.fromYmdHms(2000, 1, 7, 12, 0, 0).getLunar()
        if lunar.getDayInGanZhiExact() != "甲子":
            raise ValueError("reference_day_anchor_not_confirmed")
        table_proof = pinned_table()
        result = compare_days(prepared, days)
    return {
        "contract": "p8-ziwei-daily-independent-implementation-v1",
        "mode": "scripted_synthetic_crosscheck",
        "recorded_at_beijing": get_clock()
        .now()
        .astimezone(timezone(timedelta(hours=8)))
        .isoformat(timespec="seconds"),
        "seed": SEED,
        "natal_fixture": "synthetic_reference_1980_variant_not_canonical_ayuan",
        "natal_request_sha256": content_hash(natal),
        "shared_natal_palaces_sha256": content_hash(prepared.ziwei_natal["palaces"]),
        "scope": {
            key: natal[key]
            for key in ("owner_user_id", "subject_id", "revision", "operation_id")
        },
        "snapshot_time_index": 6,
        "primary": "actual_ast_horoscope_then_existing_p8_temporal_star_lookup",
        "reference": "stdlib_civil_day_count_then_pinned_table_then_raw_ast_star_scan",
        "anchor": {
            "date": ANCHOR.isoformat(),
            "ganzhi": "甲子",
            "checked_against": "installed_lunar_python",
        },
        "table_source": table_proof,
        "versions": {"py-iztro": version("py-iztro"), **iztro_provenance()},
        "code_sha256": _code_provenance(),
        **result,
        "comparison_cell_count": 4 * result["dates"],
        "real_model_requests": 0,
        "server_requests": 0,
        "writes_to_profiles": 0,
        "limits": [
            "独立实现日计数、四化选择、宫位扫描；本命星位与具名表源共用，不是第二个独立排盘引擎或学派真值。",
            "甲子锚经现有历法库核对，不宣称独立历史原刊或天文校准；全部目标日期显式午时。",
            "1000日期仅为软件一致性；无现实预测分数，不参与冻结的时辰倒推。",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 紫微流日四化：两种实现交叉核对（2026-10-20，北京时间）",
        "",
        f"实际记录时刻：{report['recorded_at_beijing']}。",
        f"实际{report['dates']}个不重复日期、{report['comparison_cell_count']}个四化落点，差异{report['difference_count']}。",
        "这衡量两个软件路径在共同前提下的一致性，没有现实预测准确率。",
        "",
        "主路径：实际ast.horoscope(date,6)→现有P8飞化层→本命星位。",
        "参考路径：stdlib日期差→显式甲子锚→独立40格具名表→"
        "原始typed ast宫位星曜逐项扫描。",
        "参考路径不调用现有飞化函数、日期干支函数或星位lookup。",
        "",
        "参考表逐格与安装的iztro-2.5.0.min.js原文定位核对，保留Unicode字符区间与整文件SHA256。",
        "定位的是库本身默认表，不能据此宣布古籍原刊或所有流派一致。",
        f"源bundle SHA256：`{report['table_source']['sha256']}`。",
        "",
        "| 目标年 | 日期数 |",
        "| --- | ---: |",
    ]
    lines += [
        f"| {year} | {count} |" for year, count in report["target_year_counts"].items()
    ]
    lines += ["", "| 日干 | 日期数 |", "| --- | ---: |"]
    lines += [f"| {stem} | {report['stem_coverage'].get(stem, 0)} |" for stem in TABLE]
    lines += ["", "## 差异与限制", ""]
    lines += [json.dumps(row, ensure_ascii=False) for row in report["differences"]]
    if not report["differences"]:
        lines.append(
            "本批次未观察到差异；不能推论未采样日期、其他学派或本命星位本身已独立验证。"
        )
    lines += [
        "",
        *report["limits"],
        "",
        "合成人物采用1980变体，以覆盖1986–1991目标日期；不是改写canonical阿远1994出生资料。",
        "固定seed=20261020，1000个不重复日期包含闰日及10-21至27；范围与名单SHA见JSON。",
        "模型请求0、服务器请求0、档案写入0。输出无真实用户资料或题库正文。",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scripted independent Ziwei crosscheck"
    )
    parser.add_argument("--mode", choices=("scripted",), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = run_crosscheck()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf8",
        newline="\n",
    )
    args.output.with_suffix(".md").write_text(
        render_markdown(report), encoding="utf8", newline="\n"
    )
    print(
        json.dumps(
            {
                "dates": report["dates"],
                "differences": report["difference_count"],
                "model_calls": 0,
            }
        )
    )
    return int(bool(report["difference_count"]))


if __name__ == "__main__":
    raise SystemExit(main())
