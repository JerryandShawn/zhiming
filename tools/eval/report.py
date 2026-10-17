"""Privacy-limited report serialization and baseline comparisons."""

import json
import re
from pathlib import Path
from typing import Any


def summarize(cases: list[dict[str, Any]]) -> dict[str, Any]:
    applicable = [case for case in cases if case["status"] != "n/a on v3"]
    categories: dict[str, dict[str, Any]] = {}
    for case in cases:
        group = categories.setdefault(
            case["category"],
            {"count": 0, "passed": 0, "points": 0.0, "not_applicable": 0},
        )
        if case["status"] == "n/a on v3":
            group["not_applicable"] += 1
            continue
        group["count"] += 1
        group["passed"] += case["status"] == "passed"
        group["points"] += case["score"]
    for group in categories.values():
        group["score"] = round(group["points"] / group["count"], 6) if group["count"] else None
    points = sum(case["score"] for case in applicable)
    return {
        "count": len(applicable),
        "passed": sum(case["status"] == "passed" for case in applicable),
        "not_applicable": len(cases) - len(applicable),
        "points": round(points, 6),
        "score": round(points / len(applicable), 6) if applicable else None,
        "categories": categories,
        "model_calls": sum(case.get("model_calls", 0) for case in applicable),
        "target_model_calls": sum(case.get("target_model_calls", 0) for case in applicable),
        "judge_model_calls": sum(case.get("judge_model_calls", 0) for case in applicable),
        "elapsed_seconds": round(sum(case.get("elapsed_seconds", 0) for case in applicable), 3),
    }


def _percentage(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def markdown(report: dict[str, Any]) -> str:
    header, summary = report["metadata"], report["summary"]
    lines = [
        f"# {header['date']} {header['mode']} / {header['target']} / {header['model']}",
        "",
        f"Rubric：{header['rubric_version']}；SHA256：{header['rubric_sha256']}",
        f"评审模型：{header['judge_model']}；配置：{header['config_version']}",
        f"执行状态：{header.get('status', 'unknown')}；源码 SHA256：{header.get('source_sha256', 'unavailable')}",
        f"总分：{_percentage(summary['score'])}；通过 {summary['passed']}/{summary['count']}；"
        f"n/a on v3：{summary['not_applicable']}",
        f"模型调用：{summary['model_calls']}；耗时：{summary['elapsed_seconds']:.3f} 秒",
        f"其中被测模型 {summary['target_model_calls']} 次，评审模型 {summary['judge_model_calls']} 次。",
        "",
        "| 分类 | 通过/可运行 | 得分 |",
        "| --- | --- | --- |",
    ]
    for name, group in summary["categories"].items():
        lines.append(f"| {name} | {group['passed']}/{group['count']} | {_percentage(group['score'])} |")
    if header.get("status") == "incomplete":
        lines.extend(["", "本次实测未完成；零分包含运行或评审错误，不能作为 v3 能力基线。"])
    comparison = report.get("comparison")
    if comparison:
        lines.extend(
            [
                "",
                f"对比基线：{comparison['baseline']}；总分变化 {comparison['score_delta']:+.1%}",
            ]
        )
    lines.extend(
        [
            "",
            "| 场景 | 状态 | 得分 | 失败断言 | 调用 | 耗时（秒） |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for case in report["cases"]:
        failed = ", ".join(case.get("failed_assertions", [])) or "—"
        lines.append(
            f"| {case['id']} | {case['status']} | {_percentage(case['score'])} | {failed} | "
            f"{case.get('model_calls', 0)} | {case.get('elapsed_seconds', 0):.3f} |"
        )
    previews = [(case["id"], preview) for case in report["cases"] for preview in case.get("previews", [])]
    if previews:
        lines.extend(["", "## 合成场景回答预览（每轮最多 200 字）", ""])
        lines.extend(f"- {identity}：{preview.replace(chr(10), ' ')}" for identity, preview in previews)
    return "\n".join(lines) + "\n"


def write_report(report: dict[str, Any], directory: Path, *, baseline: bool = False) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    header = report["metadata"]
    model = re.sub(r"[^\w.-]+", "_", header["model"])
    stem = f"{header['date']}-{header['mode']}-{header['target']}-{model}"
    json_path, md_path = directory / f"{stem}.json", directory / f"{stem}.md"
    serialized = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    _atomic_write(json_path, serialized)
    _atomic_write(md_path, markdown(report))
    if baseline:
        _atomic_write(directory / "baseline-v3.json", serialized)
    return json_path, md_path


def _atomic_write(path: Path, contents: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(contents, encoding="utf-8")
    temporary.replace(path)


def add_comparison(report: dict[str, Any], baseline_path: Path) -> None:
    if not baseline_path.is_file():
        return
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    previous, current = baseline["summary"]["score"], report["summary"]["score"]
    if previous is not None and current is not None:
        report["comparison"] = {
            "baseline": baseline_path.name,
            "score_delta": round(current - previous, 6),
        }
