"""Fresh evidence-only judging and synthetic calibration capture for contract v2."""

from __future__ import annotations

import json
import math
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from tools.eval.judges import ISSUE_SEVERITIES, JUDGE_SCHEMA
from tools.eval.quota import ProviderStopped, QuotaGuard
from tools.eval.schema import load_scenarios

JUDGE_SCHEMA_V2 = deepcopy(JUDGE_SCHEMA)
JUDGE_SCHEMA_V2["required"].append("reason")
JUDGE_SCHEMA_V2["properties"]["reason"] = {"type": "string", "minLength": 1, "maxLength": 1200}


class EvidenceModel:
    """Capture allowlisted facts/time/claims, never instructions or model reasoning."""

    def __init__(self, provider: Any) -> None:
        self.provider = provider
        self.evidence: dict[str, Any] = {}

    def generate(self, **kwargs: Any) -> dict[str, Any]:
        reference = kwargs.get("payload", {}).get("reference_data", {})
        for key in ("today", "now", "time_context", "facts", "current_facts", "claims"):
            if key in reference:
                self.evidence[key] = deepcopy(reference[key])
        return self.provider.generate(**kwargs)


def validate_grade(output: dict[str, Any]) -> None:
    score, verdict, issues = output["score"], output["verdict"], output["issues"]
    if isinstance(score, bool) or not isinstance(score, int | float) or not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError("Invalid fixed-rubric score")
    if verdict not in {"pass", "revise"} or not isinstance(issues, list):
        raise ValueError("Invalid fixed-rubric verdict")
    for issue in issues:
        if not isinstance(issue, dict) or type(issue.get("severity")) is not int:
            raise ValueError("Invalid fixed-rubric severity")
        if ISSUE_SEVERITIES.get(issue.get("type")) != issue["severity"]:
            raise ValueError("Invalid fixed-rubric issue")
    severity = max((item["severity"] for item in issues), default=0)
    if severity >= 5 and score > 0.2 or (severity >= 3) != (verdict == "revise") or verdict == "revise" and score == 1:
        raise ValueError("Inconsistent fixed-rubric score")
    if not isinstance(output.get("reason"), str) or not 1 <= len(output["reason"]) <= 1200:
        raise ValueError("Missing bounded evidence reason")


class EvidenceJudge:
    def __init__(self, provider: Any, rubric: Path, observed: EvidenceModel | None = None) -> None:
        self.provider = QuotaGuard(provider, "judge")
        self.rubric = rubric.read_text(encoding="utf-8")
        self.observed = observed
        self.candidates: dict[str, dict[str, Any]] = {}
        self.records: list[dict[str, Any]] = []
        self.run_id = "unassigned"
        self.categories = {case.id: case.category for case in load_scenarios()}

    def evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        budget = getattr(self.provider, "budget", None)
        before = budget.snapshot()["run_calls_by_role"].get("judge", 0) if budget else None
        evidence = deepcopy(self.observed.evidence if self.observed else {})
        safe = {key: deepcopy(payload[key]) for key in ("scenario_id", "user", "answer", "receipts", "criterion")}
        safe["此刻"] = {
            "frozen_clock": payload["clock"],
            "injected": {key: evidence[key] for key in ("today", "now", "time_context") if key in evidence},
            "v3_full_time_block_present": any(key in evidence for key in ("now", "time_context")),
        }
        safe["事实证据"] = {
            "seed_facts": deepcopy(
                [row for row in payload.get("memories", []) if row.get("source") == "seed"]
                if payload.get("packet_version") == "judge-packet-v2"
                else payload.get("seed", {}).get("facts", [])
            ),
            "injected_facts": evidence.get("facts", evidence.get("current_facts", [])),
            "claims": evidence.get("claims", []),
        }
        fixture = (
            payload.get("fixture", {})
            if payload.get("packet_version") == "judge-packet-v2"
            else payload.get("seed", {})
        )
        if fixture.get("synthetic") is not True:
            raise ValueError("Full-answer capture requires the strict synthetic fixture marker")
        row = {
            **safe,
            "run_id": self.run_id,
            "category": self.categories[payload["scenario_id"]],
            "turn": getattr(self.observed, "turn_index", 1),
            "sample_id": f"{self.run_id}:{payload['scenario_id']}:{len(self.records) + 1}",
            "grade": {"status": "not_completed"},
        }
        self.records.append(row)
        try:
            # generate has exactly this one new user payload; no tested system/history/trajectory is passed.
            response = self.provider.generate(
                system=self.rubric, payload=safe, schema=JUDGE_SCHEMA_V2, purpose="eval_critic_v2"
            )
            output = response["output"]
            validate_grade(output)
            row["grade"] = {"status": "complete", **deepcopy(output)}
            self.candidates[payload["scenario_id"]] = deepcopy(row)
            return {
                "score": float(output["score"]),
                "model_calls": budget.snapshot()["run_calls_by_role"].get("judge", 0) - before if budget else 1,
                "elapsed_seconds": time.monotonic() - started,
                "error": None,
            }
        except ProviderStopped as exc:
            row["grade"] = {"status": "stopped", "reason": exc.reason}
            if budget:
                exc.model_calls = budget.snapshot()["run_calls_by_role"].get("judge", 0) - before
            raise
        except Exception as exc:
            row["grade"] = {"status": "error", "error_code": type(exc).__name__}
            return {
                "score": 0.0,
                "model_calls": budget.snapshot()["run_calls_by_role"].get("judge", 0) - before if budget else 1,
                "elapsed_seconds": time.monotonic() - started,
                "error": type(exc).__name__,
            }


CALIBRATION_CATEGORIES = (
    "time",
    "memory_write",
    "memory_recall",
    "question",
    "safety",
    "chart",
    "decision",
)


def select_candidates(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if len({row["sample_id"] for row in records}) != len(records):
        raise ValueError("Calibration sample IDs must identify distinct actual observations")
    eligible = [row for row in records if row.get("answer") and row.get("grade", {}).get("status") == "complete"]
    by_category = {
        category: [row for row in eligible if row["category"] == category] for category in CALIBRATION_CATEGORIES
    }
    selected = [row for category in CALIBRATION_CATEGORIES for row in by_category[category][:2]]
    chosen = {row["sample_id"] for row in selected}
    selected += [row for row in eligible if row["sample_id"] not in chosen and row["category"] in by_category][
        : 20 - len(selected)
    ]
    counts = {category: sum(row["category"] == category for row in selected) for category in CALIBRATION_CATEGORIES}
    missing = {
        category: {"required": 2, "available": len(rows)} for category, rows in by_category.items() if len(rows) < 2
    }
    return selected, {
        "candidate_count": len(selected),
        "category_counts": counts,
        "missing_categories": missing,
        "ready": len(selected) == 20 and not missing,
        "human_labels": 0,
        "agreement": None,
    }


def export_candidates(
    judge: EvidenceJudge | None,
    path: Path,
    v1_path: Path | None = None,
    *,
    valid_run: bool = False,
) -> dict[str, Any]:
    """Export only actual full new-run observations; P0 previews are never inputs."""
    del v1_path
    rows, status = select_candidates(judge.records if judge else [])
    status.update(valid_run=valid_run, ready=valid_run and status["ready"], source="c21-full-synthetic-observations")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.with_suffix(".status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    if not valid_run or not rows:
        return status
    lines = [
        "# c2.1 合成全文校准候选",
        "",
        f"实际候选 {len(rows)} 条；覆盖 {len({row['category'] for row in rows})} 类；达标：{status['ready']}。",
        "每类至少两条要求不足时见同名 status.json，不复制回答或补造缺失样本。",
        "来源仅为本次有效 c2.1 的实际完整回答，未使用 P0 的 200 字预览或旧夜间九条回答。",
        "人工标签 0，一致率未计算。",
        "",
    ]
    for row in rows:
        lines += [
            f"## {row['sample_id']} / {row['category']}",
            "",
            "用户输入：" + row["user"],
            "",
            "回答全文：",
            "",
            row["answer"],
            "",
        ]
        for title, value in (("此刻块", row["此刻"]), ("程序回执", row["receipts"]), ("评审打分与理由", row["grade"])):
            lines += [title + "：", "", "```json", json.dumps(value, ensure_ascii=False, indent=2), "```", ""]
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return status
