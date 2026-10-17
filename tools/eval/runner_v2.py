"""One explicit contract-v2 corpus run; never overwrite the frozen v1 baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mingjing_core.adapters.model import ConfiguredModel  # noqa: E402
from tools.eval.batching import run_batches  # noqa: E402
from tools.eval.contract_v2 import audit_markdown, migrate, stamp_v2  # noqa: E402
from tools.eval.engine import evaluate_scenario  # noqa: E402
from tools.eval.evidence_v2 import JUDGE_SCHEMA_V2, EvidenceJudge, EvidenceModel, export_candidates  # noqa: E402
from tools.eval.outcomes import is_infrastructure_failure  # noqa: E402
from tools.eval.report import summarize, write_report  # noqa: E402
from tools.eval.runner import _metadata  # noqa: E402
from tools.eval.schema import Scenario, load_scenarios  # noqa: E402
from tools.eval.targets.fake_target import FakeTarget  # noqa: E402
from tools.eval.targets.v3_target import V3Target  # noqa: E402

EVAL = Path(__file__).parent


class EvidenceTarget(V3Target):
    def __init__(self, *, observed: EvidenceModel, **kwargs: Any) -> None:
        super().__init__(provider=observed, **kwargs)
        self.observed = observed

    def send(self, turn: dict[str, Any]) -> Any:
        self.observed.evidence.clear()
        return super().send(turn)


def _write(report: dict[str, Any], output: Path, scenarios: dict[str, Scenario], judge: EvidenceJudge | None) -> None:
    stamp_v2(report, scenarios)
    report["summary"] = summarize(report["cases"])
    write_report(report, output)
    export_candidates(judge, output.parent / "calibration/candidates.md", ROOT / "docs/v4/eval/baseline-v3.json")
    if report["metadata"]["status"] == "complete" and report["metadata"]["mode"] == "live":
        (output.parent / "baseline-v3-c2.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def run(mode: str, output: Path, stop_file: Path, once_file: Path) -> int:
    converted = [migrate(scenario) for scenario in load_scenarios()]
    scenarios, audit = [pair[0] for pair in converted], [row for pair in converted for row in pair[1]]
    output.mkdir(parents=True, exist_ok=True)
    (output / "contract-v2-assertion-audit.md").write_text(audit_markdown(audit), encoding="utf-8")
    config = {
        "version": "eval-config-kimi-code-v2.0.0",
        "judge": {
            "model": "k3",
            "provider": "same-model-independent-evidence",
            "rubric": "rubric_v2.md",
            "version": "critic-eval-v2.0.0",
        },
    }
    metadata = _metadata(config, mode, "v3" if mode == "live" else "fake", "k3" if mode == "live" else "scripted-v2")
    metadata.update(
        judge_schema_sha256=hashlib.sha256(json.dumps(JUDGE_SCHEMA_V2, sort_keys=True).encode()).hexdigest(),
        calibration={"human_labels": 0, "agreement": None, "status": "awaiting_brain_labels"},
        independent_context=True,
        planned_scenario_ids=[case.id for case in scenarios],
        v1_comparison="forbidden_cross_contract",
        baseline_adapter="unchanged-v3-ConfiguredModel",
    )
    judge, target = _prepare(mode, stop_file, once_file)
    report: dict[str, Any] = {"metadata": metadata, "cases": [], "batches": []}
    mapping = {scenario.id: scenario for scenario in scenarios}

    def publish() -> None:
        _write(report, output, mapping, judge)

    try:
        run_batches(
            scenarios,
            report,
            lambda scenario: (evaluate_scenario(scenario, target, target_name=metadata["target"], judge=judge), False),
            publish,
            batch_size=10,
        )
    finally:
        target.close()
    complete = len(report["cases"]) == len(scenarios) and not any(
        is_infrastructure_failure(case) for case in report["cases"]
    )
    metadata["status"] = "complete" if complete and not metadata.get("stop_reason") else "incomplete"
    if metadata.get("stop_reason") == "quota":
        stop_file.write_text(json.dumps({"reason": "quota", "role": metadata["stop_role"]}), encoding="utf-8")
    publish()
    call_label = "actual calls" if mode == "live" else "scripted observations (not real requests)"
    print(
        f"c2 {metadata['status']}: {report['summary']['passed']}/{report['summary']['count']}; "
        f"{call_label}={report['summary']['model_calls']}"
    )
    return (
        2
        if metadata.get("stop_reason")
        else int(not complete or mode == "scripted" and report["summary"]["passed"] != report["summary"]["count"])
    )


def _prepare(mode: str, stop_file: Path, once_file: Path) -> tuple[EvidenceJudge | None, Any]:
    if mode == "scripted":
        return None, FakeTarget()
    if stop_file.exists() or once_file.exists():
        raise SystemExit("Night policy: quota circuit is open or the single c2 corpus run already started")
    if (
        os.getenv("KIMI_MODEL") != "k3"
        or os.getenv("KIMI_BASE_URL", "").rstrip("/") != "https://api.kimi.com/coding/v1"
    ):
        raise SystemExit("Only the approved local Kimi Code k3 configuration may run")
    if not os.getenv("KIMI_API_KEY"):
        raise SystemExit("Configure KIMI_API_KEY in the process environment")
    from tools.eval.targets.local_db import local_dsn, verify_local_postgres

    verify_local_postgres(local_dsn(os.getenv("CORE_TEST_DSN", "")))
    observed = EvidenceModel(ConfiguredModel(model="k3"))
    target = EvidenceTarget(observed=observed, model="k3")
    judge = EvidenceJudge(ConfiguredModel(model="k3"), EVAL / "rubric_v2.md", observed)
    once_file.parent.mkdir(parents=True, exist_ok=True)
    with once_file.open("x", encoding="utf-8") as handle:
        json.dump({"mode": "live", "contract": "v2", "resume_authorized": False}, handle)
    return judge, target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["scripted", "live"], default="scripted")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/v4/eval/c2")
    parser.add_argument("--stop-file", type=Path, required=True)
    parser.add_argument("--once-file", type=Path, required=True)
    args = parser.parse_args()
    os.environ["LANGSMITH_TRACING"] = os.environ["LANGCHAIN_TRACING_V2"] = "false"
    return run(args.mode, args.output, args.stop_file, args.once_file)


if __name__ == "__main__":
    raise SystemExit(main())
