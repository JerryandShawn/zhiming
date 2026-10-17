"""Fresh evidence-only judging and synthetic calibration capture for contract v2."""

from __future__ import annotations

import json
import math
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from tools.eval.judges import ISSUE_SEVERITIES, JUDGE_SCHEMA
from tools.eval.quota import QuotaGuard
from tools.eval.schema import load_scenarios

JUDGE_SCHEMA_V2 = deepcopy(JUDGE_SCHEMA)
JUDGE_SCHEMA_V2["required"].append("reason")
JUDGE_SCHEMA_V2["properties"]["reason"] = {"type": "string", "minLength": 1, "maxLength": 1200}
CALIBRATION_IDS = (
    "T01",
    "T05",
    "T14",
    "M02",
    "M03",
    "M04",
    "M10",
    "M11",
    "R01",
    "R02",
    "R03",
    "R04",
    "Q01",
    "Q03",
    "Q04",
    "S01",
    "S02",
    "S03",
    "C04",
    "D02",
)


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

    def evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        evidence = deepcopy(self.observed.evidence if self.observed else {})
        safe = {key: deepcopy(payload[key]) for key in ("scenario_id", "user", "answer", "receipts", "criterion")}
        safe["此刻"] = {
            "frozen_clock": payload["clock"],
            "injected": {key: evidence[key] for key in ("today", "now", "time_context") if key in evidence},
            "v3_full_time_block_present": any(key in evidence for key in ("now", "time_context")),
        }
        safe["事实证据"] = {
            "seed_facts": deepcopy(payload.get("seed", {}).get("facts", [])),
            "injected_facts": evidence.get("facts", evidence.get("current_facts", [])),
            "claims": evidence.get("claims", []),
        }
        if payload["scenario_id"] in CALIBRATION_IDS:
            self.candidates[payload["scenario_id"]] = {**safe, "grade": {"status": "not_completed"}}
        try:
            # generate has exactly this one new user payload; no tested system/history/trajectory is passed.
            response = self.provider.generate(
                system=self.rubric, payload=safe, schema=JUDGE_SCHEMA_V2, purpose="eval_critic_v2"
            )
            output = response["output"]
            validate_grade(output)
            if payload["scenario_id"] in CALIBRATION_IDS:
                self.candidates[payload["scenario_id"]] = {**safe, "grade": deepcopy(output)}
            return {
                "score": float(output["score"]),
                "model_calls": 1,
                "elapsed_seconds": time.monotonic() - started,
                "error": None,
            }
        except Exception as exc:
            return {
                "score": 0.0,
                "model_calls": 1,
                "elapsed_seconds": time.monotonic() - started,
                "error": type(exc).__name__,
            }


def export_candidates(judge: EvidenceJudge | None, path: Path, v1_path: Path) -> None:
    prior = json.loads(v1_path.read_text(encoding="utf-8")) if v1_path.exists() else {"cases": []}
    cases = {case["id"]: case for case in prior["cases"]}
    scenarios = {scenario.id: scenario for scenario in load_scenarios()}
    lines = [
        "# 合成校准候选（20 条；尚待大脑标注）",
        "",
        "人工一致率：未计算，尚无人工标签。不得声称 ≥80%。",
        "P0 v1 仅留前200字预览，原全文未保存；以下逐项区分原预览与此次 c2 重跑全文。",
        "c2 全文可作为替代校准集，能否替代 P0 原全文请大脑决定。不得把预览扩写成原回答。",
        "",
    ]
    for identity in CALIBRATION_IDS:
        row = judge.candidates.get(identity) if judge else None
        lines.extend([f"## {identity}", ""])
        scenario = scenarios[identity]
        lines.extend(["用户输入：" + scenario.turns[0].user, "", "场景冻结时刻：" + scenario.clock, ""])
        previews = cases.get(identity, {}).get("previews", [])
        lines.extend(["P0 原预览（不是全文）：", "", "\n\n".join(previews) or "无回答预览（运行未产生最终回答）。", ""])
        if row:
            lines.extend(
                [
                    "来源：本夜获准 c2 基线重跑；仅合成资料。",
                    "",
                    "用户输入：" + row["user"],
                    "",
                    "v3 c2 回答全文：",
                    "",
                    row["answer"],
                    "",
                    "此刻块：",
                    "",
                    "```json",
                    json.dumps(row["此刻"], ensure_ascii=False, indent=2),
                    "```",
                    "",
                    "回执清单：",
                    "",
                    "```json",
                    json.dumps(row["receipts"], ensure_ascii=False, indent=2),
                    "```",
                    "",
                    "评审员 v2：",
                    "",
                    "```json",
                    json.dumps(row["grade"], ensure_ascii=False, indent=2),
                    "```",
                    "",
                ]
            )
        else:
            lines.extend(["原P0全文、实际注入此刻、程序回执与v2评分所需证据未保留，无法补全；不得伪造。", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
