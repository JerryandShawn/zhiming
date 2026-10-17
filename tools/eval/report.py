"""Privacy-limited report serialization and baseline comparisons."""

import json
import re
from pathlib import Path
from typing import Any

from tools.eval.outcomes import is_infrastructure_failure

COMPARISON_REASONS = {
    "current_not_live": "本次为框架回放，不能和实测能力成绩比较",
    "baseline_not_live": "基线不是实测能力成绩",
    "current_incomplete": "本次运行尚未完整完成",
    "baseline_incomplete": "基线运行尚未完整完成",
    "baseline_missing": "尚无可用基线",
    "judge_contract_missing": "缺少固定评审协议信息",
    "judge_contract_changed": "评审模型、rubric 或提交协议不同",
    "applicable_scenarios_differ": "实际参与计分的场景范围不同",
    "scores_unavailable": "缺少可比较的分数",
}
JUDGE_COMPARISON_KEYS = (
    "judge_model",
    "judge_provider",
    "judge_schema_sha256",
    "rubric_version",
    "rubric_sha256",
)


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
        f"本报告观测调用：{summary['model_calls']}；耗时：{summary['elapsed_seconds']:.3f} 秒",
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
        label = f"对比基线：{comparison['baseline']}；"
        if "score_delta" in comparison:
            label += f"总分变化 {comparison['score_delta']:+.1%}"
        else:
            label += "不可比较：" + COMPARISON_REASONS[comparison["reason"]]
        lines.extend(["", label])
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
    lines.extend(_batch_lines(report))
    previews = [(case["id"], preview) for case in report["cases"] for preview in case.get("previews", [])]
    if previews:
        lines.extend(["", "## 合成场景回答预览（每轮最多 200 字）", ""])
        lines.extend(f"- {identity}：{preview.replace(chr(10), ' ')}" for identity, preview in previews)
    return "\n".join(lines) + "\n"


def _batch_lines(report: dict[str, Any]) -> list[str]:
    if not report.get("batches"):
        return []
    lines = [
        "",
        "## 分批实际调用（新增为实际请求，继承为缓存观测）",
        "",
        "| 执行/批次 | 场景 | 新增目标/评审 | 继承目标/评审 | 新增模型耗时（秒） |",
        "| --- | --- | --- | --- | --- |",
    ]
    for batch in report["batches"]:
        new, inherited = batch["new_usage"], batch["inherited_usage"]
        seconds = new["target_model_elapsed_seconds"] + new["judge_model_elapsed_seconds"]
        lines.append(
            f"| {batch['attempt']}/{batch['batch']} | {', '.join(batch['scenario_ids'])} | "
            f"{new['target_model_calls']}/{new['judge_model_calls']} | "
            f"{inherited['target_model_calls']}/{inherited['judge_model_calls']} | {seconds:.3f} |"
        )
    metadata = report["metadata"]
    usage = metadata.get("execution_usage", {})
    if usage:
        lines.extend(
            [
                "",
                f"本次新增实际调用：{usage['new_usage']['model_calls']}；"
                f"缓存继承观测调用：{usage['inherited_usage']['model_calls']}；"
                f"历史累计实际调用（含失败请求）：{usage['historical_actual_usage']['model_calls']}。",
            ]
        )
    if metadata.get("stop_reason"):
        reason = "额度限制" if metadata["stop_reason"] == "quota" else "供应商 HTTP 故障"
        lines.extend(["", f"因{reason}已停止；需用户明确决定后显式使用 --resume 继续。"])
    return lines


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
    comparison: dict[str, Any] = {"baseline": baseline_path.name, "comparable": False}
    report["comparison"] = comparison
    if report["metadata"].get("mode") != "live" or report["metadata"].get("target") == "fake":
        comparison["reason"] = "current_not_live"
        return
    if not baseline_path.is_file():
        comparison["reason"] = "baseline_missing"
        return
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    reason = _comparison_reason(report, baseline)
    if reason:
        comparison["reason"] = reason
        return
    previous, current = baseline["summary"]["score"], report["summary"]["score"]
    if previous is None or current is None:
        comparison["reason"] = "scores_unavailable"
        return
    comparison.update(comparable=True, score_delta=round(current - previous, 6))


def _comparison_reason(current: dict[str, Any], baseline: dict[str, Any]) -> str | None:
    for label, report in (("current", current), ("baseline", baseline)):
        metadata = report["metadata"]
        if metadata.get("mode") != "live" or metadata.get("target") == "fake":
            return label + "_not_live"
        if metadata.get("status") != "complete" or any(is_infrastructure_failure(case) for case in report["cases"]):
            return label + "_incomplete"
        if any(not metadata.get(key) for key in JUDGE_COMPARISON_KEYS):
            return "judge_contract_missing"
    if any(current["metadata"][key] != baseline["metadata"][key] for key in JUDGE_COMPARISON_KEYS):
        return "judge_contract_changed"
    current_ids = {case["id"] for case in current["cases"] if case["status"] != "n/a on v3"}
    baseline_ids = {case["id"] for case in baseline["cases"] if case["status"] != "n/a on v3"}
    return "applicable_scenarios_differ" if current_ids != baseline_ids else None
