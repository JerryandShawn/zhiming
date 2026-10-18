"""LF-only c21 reports and independent calibration; archived c2/v1 are read-only."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from tools.eval.contract_v2 import VERSION
from tools.eval.contracts import canonical_hash
from tools.eval.evidence_v2 import EvidenceJudge, export_candidates
from tools.eval.outcomes import is_infrastructure_failure
from tools.eval.report import markdown, summarize
from tools.eval.schema import Scenario
from tools.eval.source_v21 import execution_digest

IDENTITY_KEYS = (
    "source_sha256",
    "scoring_contract_version",
    "judge_model",
    "model",
    "rubric_sha256",
    "judge_schema_sha256",
    "config_sha256",
    "provider_endpoint_sha256",
    "mode",
    "execution_sha256",
    "planned_contracts_sha256",
    "member_ledger_identity",
)


def ledger_identity(path: Path) -> str:
    return hashlib.sha256(os.path.normcase(str(path.resolve())).encode("utf-8")).hexdigest()


def write_json(path: Path, data: dict[str, Any]) -> None:
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(text.replace("\r\n", "\n").encode("utf-8"))
    temporary.replace(path)


def resume_report(output: Path, metadata: dict[str, Any], *, resume: bool) -> dict[str, Any] | None:
    path = output / "run-state-c21.json"
    if not path.exists():
        if resume:
            raise SystemExit("No c21 state exists to resume")
        return None
    if not resume:
        raise SystemExit("c21 state already exists; use --resume with the same frozen source")
    report = json.loads(path.read_text(encoding="utf-8"))
    if any(report["metadata"].get(key) != metadata.get(key) for key in IDENTITY_KEYS):
        raise SystemExit("Cannot resume c21 across frozen source, model, judge or contract changes")
    for case in report["cases"]:
        expected = metadata.get("planned_contracts", {}).get(case["id"])
        if case.get("scenario_contract_sha256") != expected:
            raise SystemExit("Cached c21 scenario contract changed; do not relabel old observations")
    return report


def reusable(case: dict[str, Any]) -> bool:
    return case["status"] in {"passed", "failed", "n/a on v3"} and not is_infrastructure_failure(case)


def publish(report: dict[str, Any], output: Path, scenarios: dict[str, Scenario], judge: EvidenceJudge | None) -> None:
    del scenarios
    if execution_digest() != report["metadata"]["execution_sha256"]:
        report["metadata"].update(status="incomplete", execution_error_code="FrozenSourceChanged", resume_at=None)
    for case in report["cases"]:
        case["scenario_contract_sha256"] = report["metadata"]["planned_contracts"][case["id"]]
    report["metadata"].update(
        scoring_contract_version=VERSION,
        scoring_corpus_sha256=canonical_hash(
            {case["id"]: case["scenario_contract_sha256"] for case in report["cases"] if case["status"] != "n/a on v3"}
        ),
    )
    report["summary"] = summarize(report["cases"])
    if judge:
        report["evidence_full"] = judge.records
    complete = report["metadata"]["status"] == "complete" and report["metadata"]["mode"] == "live"
    status = export_candidates(judge, output.parent / "calibration/candidates-c2.1.md", valid_run=complete)
    report["metadata"]["calibration"] = status
    write_json(output / "run-state-c21.json", report)
    stem = f"{report['metadata']['date']}-{report['metadata']['mode']}-{report['metadata']['target']}-k3-c21"
    write_json(output / (stem + ".json"), report)
    warning = "线上可能受影响：会员周额度已耗尽，全部评测停止。\n\n" if report["metadata"].get("warning") else ""
    write_text(output / (stem + ".md"), warning + markdown(report))
    if report["metadata"]["mode"] == "live":
        write_json(
            output.parent / "baseline-v3-c2.1.status.json",
            {
                "valid": complete,
                "contract_version": VERSION,
                "run_id": report["metadata"]["run_id"],
                "status": report["metadata"]["status"],
                "source_sha256": report["metadata"]["source_sha256"],
                "stop_reason": report["metadata"].get("stop_reason"),
                "resume_at": report["metadata"].get("resume_at"),
                "warning": report["metadata"].get("warning"),
            },
        )
        if complete:
            write_json(output.parent / "baseline-v3-c2.1.json", report)
