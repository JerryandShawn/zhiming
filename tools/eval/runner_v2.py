"""E1 c21 runner: frozen old-v3 source, bounded membership batches, full synthetic evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from mingjing_core.adapters.model import ConfiguredModel  # noqa: E402
from mingjing_core.timekit.clock import SystemClock  # noqa: E402
from tools.eval.contract_v2 import (  # noqa: E402
    VERSION,
    audit_markdown,
    migrate,
    scenario_v21_hash,
)
from tools.eval.contracts import canonical_hash  # noqa: E402
from tools.eval.engine_v21 import evaluate_scenario  # noqa: E402
from tools.eval.evidence_v2 import (  # noqa: E402
    JUDGE_SCHEMA_V2,
    EvidenceJudge,
    EvidenceModel,
)
from tools.eval.member_budget import MemberBudget  # noqa: E402
from tools.eval.outcomes import is_infrastructure_failure  # noqa: E402
from tools.eval.quota import ProviderStopped  # noqa: E402
from tools.eval.runner import _metadata  # noqa: E402
from tools.eval.schema import Scenario, load_scenarios  # noqa: E402
from tools.eval.source_v21 import (  # noqa: E402
    execution_digest,
    freeze_source,
    verify_source,
)
from tools.eval.state_v21 import (  # noqa: E402
    ledger_identity,
    publish,
    resume_report,
    reusable,
    write_text,
)
from tools.eval.targets.fake_target import FakeTarget  # noqa: E402
from tools.eval.targets.v3_target import V3Target  # noqa: E402

EVAL = Path(__file__).parent


def e1_dsn() -> str:
    from psycopg.conninfo import conninfo_to_dict

    from tools.eval.targets.local_db import local_dsn

    dsn = local_dsn(os.getenv("CORE_TEST_DSN", ""))
    if conninfo_to_dict(dsn).get("dbname") != "core_test_e1":
        raise SystemExit("E1 requires its isolated core_test_e1 database; never use the mainline test database")
    return dsn


class EvidenceTarget(V3Target):
    def __init__(self, *, observed: EvidenceModel, budget: MemberBudget | None = None, **kwargs: Any) -> None:
        super().__init__(provider=observed, **kwargs)
        self.observed, self.budget = observed, budget

    def reset(self, seed: dict[str, Any]) -> None:
        super().reset(seed)
        self.model.provider.budget = self.budget

    def send(self, turn: dict[str, Any]) -> Any:
        self.observed.evidence.clear()
        self.observed.turn_index = turn["_index"]
        before = self.budget.snapshot()["run_calls_by_role"]["target"] if self.budget else None
        result = super().send(turn)
        if self.budget:
            result.model_calls = self.budget.snapshot()["run_calls_by_role"]["target"] - before
        return result


def configuration(mode: str) -> dict[str, Any]:
    config = yaml.safe_load((EVAL / "config_v2.yaml").read_text(encoding="utf-8"))
    if config["contract_version"] != VERSION or config["judge"]["model"] != "k3-256k":
        raise SystemExit("The reviewed c21 target/judge contract is fixed")
    config["judge"]["model"] = "k3-256k"
    return config


def metadata_for(mode: str, config: dict[str, Any]) -> dict[str, Any]:
    metadata = _metadata(config, mode, "v3" if mode == "live" else "fake", "k3" if mode == "live" else "scripted-c21")
    metadata.update(
        judge_schema_sha256=hashlib.sha256(json.dumps(JUDGE_SCHEMA_V2, sort_keys=True).encode()).hexdigest(),
        scoring_contract_version=VERSION,
        independent_context=True,
        v1_comparison="forbidden_cross_contract",
        baseline_adapter="unchanged-v3-ConfiguredModel",
        report_namespace="c21",
    )
    return metadata


def _prepare(
    mode: str,
    stop_file: Path | None = None,
    once_file: Path | None = None,
    *,
    budget: MemberBudget | None = None,
    freeze: Path | None = None,
) -> tuple[EvidenceJudge | None, Any]:
    if mode == "scripted":
        return None, FakeTarget()
    if any(path and path.exists() for path in (stop_file, once_file)):
        raise SystemExit("Legacy single c2 corpus flags are archived; choose independent c21 state")
    verify_source(freeze)
    if budget is None:
        raise SystemExit("c21 live requires the shared membership ledger")
    if (
        os.getenv("KIMI_MODEL") != "k3"
        or os.getenv("KIMI_BASE_URL", "").rstrip("/") != "https://api.kimi.com/coding/v1"
    ):
        raise SystemExit("Only the approved membership target k3 configuration may run E1")
    if not os.getenv("KIMI_API_KEY"):
        raise SystemExit("Configure the target key through the process environment")
    from tools.eval.targets.local_db import verify_local_postgres

    verify_local_postgres(e1_dsn())
    observed = EvidenceModel(ConfiguredModel(model="k3", role="evaluation"))
    target = EvidenceTarget(observed=observed, model="k3", budget=budget)
    judge = EvidenceJudge(ConfiguredModel(model="k3-256k", role="critic"), EVAL / "rubric_v21.md", observed)
    judge.provider.budget = budget
    return judge, target


def _stop(report: dict[str, Any], exc: ProviderStopped, budget: MemberBudget | None) -> None:
    report["metadata"].update(status="incomplete", stop_reason=exc.reason, resume_at=exc.resume_at, stop_role=exc.role)
    if budget:
        report["metadata"]["membership"] = budget.snapshot()
    if exc.reason == "quota_weekly":
        report["metadata"]["warning"] = "线上可能受影响"


def _close_publish(
    target: Any,
    report: dict[str, Any],
    scenarios: list[Scenario],
    output: Path,
    judge: EvidenceJudge | None,
    budget: MemberBudget | None,
) -> None:
    try:
        target.close()
    except BaseException as exc:
        report["metadata"].update(status="incomplete", execution_error_code=type(exc).__name__)
        raise
    finally:
        completed_ids = {case["id"] for case in report["cases"] if reusable(case)}
        report["metadata"]["pending_scenario_ids"] = [case.id for case in scenarios if case.id not in completed_ids]
        if budget:
            report["metadata"]["membership"] = budget.snapshot()
        publish(report, output, {case.id: case for case in scenarios}, judge)


def _case_halted(report: dict[str, Any], case: dict[str, Any], budget: MemberBudget | None) -> bool:
    if case.get("stop_reason"):
        snap = budget.snapshot() if budget else {}
        raise ProviderStopped(case["stop_reason"], case.get("stop_role", "target"), resume_at=snap.get("resume_at"))
    if is_infrastructure_failure(case):
        report["metadata"].update(
            status="incomplete",
            execution_error_code="InfrastructureFailure",
            failure_scenario_id=case["id"],
            resume_at=None,
        )
        return True
    return False


def _batches(
    scenarios: list[Scenario],
    report: dict[str, Any],
    target: Any,
    judge: EvidenceJudge | None,
    budget: MemberBudget | None,
    output: Path,
    limit: int | None,
) -> None:
    mapping = {case.id: case for case in scenarios}
    known = {case["id"]: case for case in report["cases"] if reusable(case)}
    for scenario in scenarios:
        if "v3" not in scenario.targets and report["metadata"]["mode"] == "live":
            known[scenario.id] = evaluate_scenario(scenario, target, target_name="v3", judge=judge)
    completed = 0
    for offset in range(0, len(scenarios), 10):
        batch = scenarios[offset : offset + 10]
        pending = [case for case in batch if case.id not in known]
        if not pending:
            continue
        if budget:
            budget.before_batch([case.id for case in batch])
        entry = {"number": offset // 10 + 1, "scenario_ids": [case.id for case in batch], "executed_ids": []}
        report["c21_batches"].append(entry)
        for scenario in pending:
            if execution_digest() != report["metadata"]["execution_sha256"]:
                raise SystemExit("Frozen E1 execution data changed; no further requests are allowed")
            report["metadata"]["active_scenario_id"] = scenario.id
            case = evaluate_scenario(scenario, target, target_name=report["metadata"]["target"], judge=judge)
            known[scenario.id] = case
            entry["executed_ids"].append(scenario.id)
            report["cases"] = [known[item.id] for item in scenarios if item.id in known]
            if _case_halted(report, case, budget):
                entry["status"] = "incomplete"
                return
            if budget:
                report["metadata"]["membership"] = budget.snapshot()
            publish(report, output, mapping, judge)
        if budget:
            budget.finish_batch()
            report["metadata"]["membership"] = budget.snapshot()
        entry["status"] = "complete"
        completed += 1
        if limit and completed >= limit:
            break
    report["cases"] = [known[item.id] for item in scenarios if item.id in known]
    report["metadata"]["pending_scenario_ids"] = [item.id for item in scenarios if item.id not in known]
    if len(known) == len(scenarios) and all(reusable(case) for case in report["cases"]):
        report["metadata"]["status"] = "complete"
    elif budget:
        snapshot = budget.snapshot()
        last = snapshot.get("last_batch_finished_at")
        if last:
            from datetime import timedelta

            report["metadata"]["resume_at"] = (datetime.fromisoformat(last) + timedelta(minutes=20)).isoformat()


def _result_code(mode: str, report: dict[str, Any], budget: MemberBudget | None) -> int:
    summary = report["summary"]
    print(f"c21 {report['metadata']['status']}: {summary['passed']}/{summary['count']}; mode={mode}", flush=True)
    if mode == "live":
        print(
            json.dumps(
                {"membership": budget.snapshot() if budget else {}, "resume_at": report["metadata"].get("resume_at")}
            ),
            flush=True,
        )
    if report["metadata"]["status"] == "complete":
        return int(mode == "scripted" and summary["passed"] != summary["count"])
    return 3 if report["metadata"].get("resume_at") else 2


def run(
    mode: str,
    output: Path,
    stop_file: Path | None = None,
    once_file: Path | None = None,
    *,
    ledger: Path | None = None,
    freeze: Path | None = None,
    resume: bool = False,
    max_batches: int | None = None,
) -> int:
    converted = [migrate(case) for case in load_scenarios()]
    scenarios = [pair[0] for pair in converted]
    if len(scenarios) != 80:
        raise SystemExit("c21 only uses the frozen eighty-case corpus, never v2.2 extensions")
    config = configuration(mode)
    metadata = metadata_for(mode, config)
    planned = {case.id: scenario_v21_hash(case) for case in scenarios}
    metadata.update(
        execution_sha256=execution_digest(), planned_contracts=planned, planned_contracts_sha256=canonical_hash(planned)
    )
    metadata["member_ledger_identity"] = ledger_identity(ledger) if mode == "live" and ledger else None
    prior = resume_report(output, metadata, resume=resume)
    run_id = prior["metadata"]["run_id"] if prior else "c21-" + uuid.uuid4().hex
    budget = MemberBudget(ledger, run_id) if mode == "live" and ledger else None
    if (
        prior
        and budget
        and budget.snapshot()["run_calls_total"] < prior["metadata"].get("membership", {}).get("run_calls_total", 0)
    ):
        raise SystemExit("Membership ledger lost actual-call history; never reset or replace the E1 ledger")
    if mode == "live":
        metadata["execution_source"] = verify_source(freeze)
    report = prior or {"metadata": metadata, "cases": [], "batches": [], "c21_batches": [], "evidence_full": []}
    report["metadata"].update(status="incomplete", run_id=run_id, stop_reason=None, resume_at=None)
    judge, target = _prepare(mode, stop_file, once_file, budget=budget, freeze=freeze)
    if judge:
        judge.run_id, judge.records = run_id, list(report.get("evidence_full", []))
    rows = [row for _, audit in converted for row in audit]
    write_text(output / "contract-v2.1-assertion-audit.md", audit_markdown(rows))
    try:
        if budget and budget.snapshot().get("reason") == "quota_5h":
            budget.resume_once()
        _batches(scenarios, report, target, judge, budget, output, max_batches if mode == "live" else None)
    except ProviderStopped as exc:
        _stop(report, exc, budget)
    except BaseException as exc:
        report["metadata"].update(status="incomplete", execution_error_code=type(exc).__name__)
        raise
    finally:
        _close_publish(target, report, scenarios, output, judge, budget)
    return _result_code(mode, report, budget)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["scripted", "live"], default="scripted")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument(
        "--stop-file", type=Path, help="Legacy scripted CI compatibility; never read or write it in scripted mode"
    )
    parser.add_argument(
        "--once-file", type=Path, help="Legacy scripted CI compatibility; live must use independent c21 state"
    )
    parser.add_argument("--freeze-manifest", type=Path)
    parser.add_argument("--freeze-source", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-batches", type=int, default=1)
    parser.add_argument(
        "--follow", action="store_true", help="Wait between bounded batches; auto-resume a first 5h stop once"
    )
    parser.add_argument(
        "--calibration-only",
        action="store_true",
        help="One independent D02 sample after the valid baseline; excluded from its score",
    )
    args = parser.parse_args()
    if args.freeze_source:
        freeze_source(args.freeze_source)
        return 0
    if args.max_batches < 1:
        parser.error("--max-batches must be positive")
    os.environ["LANGSMITH_TRACING"] = os.environ["LANGCHAIN_TRACING_V2"] = "false"
    output = args.output or ROOT / ("docs/v4/eval/c21" if args.mode == "live" else "docs/v4/evidence/P1/c21-scripted")
    while True:
        if args.calibration_only:
            from tools.eval.calibration_v21 import run_calibration

            if args.mode != "live":
                parser.error("--calibration-only requires live mode and a valid baseline")
            status = run_calibration(output, args.ledger, args.freeze_manifest)
        else:
            status = run(
                args.mode,
                output,
                args.stop_file,
                args.once_file,
                ledger=args.ledger,
                freeze=args.freeze_manifest,
                resume=args.resume,
                max_batches=args.max_batches,
            )
        if not args.follow or status != 3:
            return status
        state_name = "calibration-only-c21.json" if args.calibration_only else "run-state-c21.json"
        report = json.loads((output / state_name).read_text(encoding="utf-8"))
        wake = datetime.fromisoformat(report["resume_at"] if args.calibration_only else report["metadata"]["resume_at"])
        while SystemClock().now().astimezone(UTC) < wake:
            time.sleep(min(60, max(0.1, (wake - SystemClock().now().astimezone(UTC)).total_seconds())))
        args.resume = True


if __name__ == "__main__":
    raise SystemExit(main())
