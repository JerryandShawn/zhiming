"""Compare the new ModelPort against a complete frozen old-v3 c21 baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from psycopg.conninfo import conninfo_to_dict  # noqa: E402

from mingjing_core.adapters.model import ConfiguredModel  # noqa: E402
from mingjing_core.models.legacy import PortBackedModel  # noqa: E402
from mingjing_core.models.registry import ModelRegistry  # noqa: E402
from mingjing_core.timekit.clock import SystemClock  # noqa: E402
from tools.eval.contract_v2 import VERSION, migrate, scenario_v21_hash  # noqa: E402
from tools.eval.contracts import canonical_hash  # noqa: E402
from tools.eval.engine_v21 import evaluate_scenario  # noqa: E402
from tools.eval.evidence_v2 import EvidenceJudge, EvidenceModel  # noqa: E402
from tools.eval.member_budget import MemberBudget  # noqa: E402
from tools.eval.quota import ProviderStopped  # noqa: E402
from tools.eval.runner_v2 import EvidenceTarget, configuration, metadata_for  # noqa: E402
from tools.eval.schema import Scenario, load_scenarios  # noqa: E402
from tools.eval.source_v21 import execution_digest, verify_source  # noqa: E402
from tools.eval.state_v21 import IDENTITY_KEYS, ledger_identity, reusable, write_json, write_text  # noqa: E402
from tools.eval.targets.local_db import local_dsn, verify_local_postgres  # noqa: E402

SUBSET_IDS = ("T01", "T02", "T03", "T04", "T05", "R01", "R02", "R03", "S01", "S02")
STATE_NAME = "port-subset-state-v21.json"


def preflight(baseline: Path, ledger: Path, freeze: Path) -> tuple[dict[str, Any], dict[str, Any], list[Scenario]]:
    source = verify_source(freeze)
    parent = json.loads(baseline.read_text(encoding="utf-8"))
    config = configuration("live")
    expected = metadata_for("live", config)
    cases = [migrate(case)[0] for case in load_scenarios()]
    planned = {case.id: scenario_v21_hash(case) for case in cases}
    expected.update(
        execution_sha256=execution_digest(),
        planned_contracts=planned,
        planned_contracts_sha256=canonical_hash(planned),
        member_ledger_identity=ledger_identity(ledger),
    )
    metadata = parent.get("metadata", {})
    paired = [case for case in parent.get("cases", []) if case.get("id") in SUBSET_IDS]
    if (
        metadata.get("status") != "complete"
        or metadata.get("mode") != "live"
        or metadata.get("target") != "v3"
        or metadata.get("baseline_adapter") != "unchanged-v3-ConfiguredModel"
        or metadata.get("synthetic_only") is not True
        or len(planned) != 80
        or {case["id"] for case in parent.get("cases", [])} != set(planned)
        or len(parent.get("cases", [])) != 80
        or any(not reusable(case) for case in parent["cases"])
        or any(metadata.get(key) != expected.get(key) for key in IDENTITY_KEYS)
        or source["source_sha256"] != expected["source_sha256"]
        or source["execution_sha256"] != expected["execution_sha256"]
        or any(case.get("scenario_contract_sha256") != planned[case["id"]] for case in parent["cases"])
        or any(
            type(case.get("score")) not in (int, float)
            or not math.isfinite(case["score"])
            or not 0 <= case["score"] <= 1
            for case in paired
        )
    ):
        raise SystemExit("P1 subset requires the complete valid same-source k3/k3-256k c21 baseline")
    expected.update(
        run_id=metadata["run_id"],
        baseline_sha256=hashlib.sha256(baseline.read_bytes()).hexdigest(),
        scoring_contract_version=VERSION,
        status="incomplete",
        phase="P1-model-port-subset",
        target="v3",
        adapter="ModelPort-v2/anthropic_messages",
        port_role="evaluation",
        stop_on_quota=True,
        compared_scenario_ids=list(SUBSET_IDS),
        baseline_score_unchanged=True,
    )
    by_id = {case.id: case for case in cases}
    return parent, expected, [by_id[identity] for identity in SUBSET_IDS]


def prepare(budget: MemberBudget, parent: dict[str, Any]) -> tuple[EvidenceJudge, EvidenceTarget]:
    if (
        os.getenv("KIMI_MODEL") != "k3"
        or os.getenv("KIMI_BASE_URL", "").rstrip("/") != "https://api.kimi.com/coding/v1"
        or not os.getenv("KIMI_API_KEY")
    ):
        raise SystemExit("P1 subset requires the approved membership k3 process configuration")
    dsn = local_dsn(os.getenv("CORE_TEST_DSN", ""))
    if conninfo_to_dict(dsn).get("dbname") != "core_test_e1":
        raise SystemExit("P1 subset only uses the dedicated core_test_e1 database")
    verify_local_postgres(dsn)
    snapshot = budget.snapshot()
    prior = parent["metadata"].get("membership", {})
    if snapshot["run_calls_total"] < prior.get("run_calls_total", 0) or not prior.get("run_calls_total"):
        raise SystemExit("P1 subset refuses a reset or missing baseline membership ledger")
    registry = ModelRegistry()
    handles = registry.resolve("evaluation")
    if (
        len(handles) != 1
        or handles[0].provider != "kimi_code"
        or handles[0].model != "k3"
        or handles[0].protocol != "anthropic_messages"
        or handles[0].base_url.rstrip("/") != "https://api.kimi.com/coding/v1"
    ):
        raise SystemExit("P1 subset evaluation role must resolve only to the same membership k3")
    provider = PortBackedModel(registry, role="evaluation", stop_on_quota=True)
    observed = EvidenceModel(provider)
    target = EvidenceTarget(observed=observed, model="k3", budget=budget, dsn=dsn)
    judge = EvidenceJudge(
        ConfiguredModel(model="k3-256k", role="critic"), Path(__file__).with_name("rubric_v21.md"), observed
    )
    judge.provider.budget = budget
    judge.run_id = parent["metadata"]["run_id"] + ":port-subset"
    return judge, target


def load_state(output: Path, metadata: dict[str, Any], *, resume: bool) -> dict[str, Any]:
    path = output / STATE_NAME
    if not path.exists():
        if resume:
            raise SystemExit("No P1 port-subset state exists to resume")
        return {"metadata": metadata, "cases": [], "evidence_full": []}
    if not resume:
        raise SystemExit("P1 port-subset state exists; use --resume with unchanged identities")
    report = json.loads(path.read_text(encoding="utf-8"))
    keys = (*IDENTITY_KEYS, "run_id", "baseline_sha256", "adapter", "port_role", "compared_scenario_ids")
    if any(report["metadata"].get(key) != metadata.get(key) for key in keys):
        raise SystemExit("Cannot resume P1 subset with changed source, baseline, model or ledger")
    for case in report["cases"]:
        if case.get("scenario_contract_sha256") != metadata["planned_contracts"].get(case["id"]):
            raise SystemExit("Cannot relabel cached P1 subset observations")
    return report


def save(
    report: dict[str, Any], output: Path, budget: MemberBudget, judge: EvidenceJudge, parent: dict[str, Any]
) -> None:
    metadata = report["metadata"]
    if execution_digest() != metadata["execution_sha256"]:
        metadata.update(status="incomplete", execution_error_code="FrozenSourceChanged", resume_at=None)
    metadata["membership"] = budget.snapshot()
    metadata["new_real_calls"] = metadata["membership"]["run_calls_total"] - metadata["calls_before"]
    if metadata["membership"].get("reason") == "quota_weekly":
        metadata.update(status="incomplete", warning="线上可能受影响", resume_at=None)
    report["evidence_full"] = judge.records
    baseline = {case["id"]: case for case in parent["cases"]}
    for case in report["cases"]:
        case["scenario_contract_sha256"] = metadata["planned_contracts"][case["id"]]
    paired = [case for case in report["cases"] if reusable(case)]
    if metadata["status"] != "complete":
        report.pop("comparison", None)
    if len(paired) == len(SUBSET_IDS) and metadata["status"] == "complete":
        old = sum(baseline[case["id"]]["score"] for case in paired) / len(paired)
        new = sum(case["score"] for case in paired) / len(paired)
        report["comparison"] = {
            "baseline_score": old,
            "model_port_score": new,
            "delta_percentage_points": round((new - old) * 100, 4),
            "within_5pp_decline": new >= old - 0.05,
            "same_contract_model_and_rubric": True,
        }
    lines = [
        "# P1 新端口子集对比（契约 v2.1）",
        "",
        "适配器：ModelPort v2；被测 k3，独立评审 k3-256k。",
        "与完整旧 v3 基线中的同十个场景成对比较；本文件不改写基线。",
        "",
        f"状态：{metadata['status']}；本阶段新增真实调用：{metadata['new_real_calls']}。",
        "",
        "| 场景 | 旧适配器得分 | 新端口状态 / 得分 |",
        "| --- | --- | --- |",
    ]
    lines += [
        f"| {case['id']} | {baseline[case['id']]['score']} | {case['status']} / {case['score']} |"
        for case in report["cases"]
    ]
    lines += [
        "",
        "比较结果：" + json.dumps(report.get("comparison"), ensure_ascii=False),
        "",
        "未完成或基础设施失败时不产生有效分数差；完整合成回答与评审证据见同目录JSON。",
        "",
    ]
    if metadata.get("warning"):
        lines = ["线上可能受影响：周额度错误已停止全部调用。", "", *lines]
    write_json(output / STATE_NAME, report)
    write_json(output / "port-subset-v21.json", report)
    write_text(output / "port-subset-v21.md", "\n".join(lines))


def execute(
    report: dict[str, Any],
    scenarios: list[Scenario],
    target: EvidenceTarget,
    judge: EvidenceJudge,
    budget: MemberBudget,
    output: Path,
    parent: dict[str, Any],
) -> None:
    known = {case["id"]: case for case in report["cases"] if reusable(case)}
    if len(known) == len(SUBSET_IDS):
        report["metadata"]["status"] = "complete"
        return
    budget.before_batch(list(SUBSET_IDS))
    for scenario in scenarios:
        if scenario.id in known:
            continue
        if execution_digest() != report["metadata"]["execution_sha256"]:
            raise SystemExit("Frozen P1 subset source changed; no further requests are allowed")
        report["metadata"]["active_scenario_id"] = scenario.id
        case = evaluate_scenario(scenario, target, target_name="v3", judge=judge)
        known[scenario.id] = case
        report["cases"] = [known[item] for item in SUBSET_IDS if item in known]
        if case.get("stop_reason"):
            raise ProviderStopped(
                case["stop_reason"], case.get("stop_role", "target"), resume_at=budget.snapshot().get("resume_at")
            )
        save(report, output, budget, judge, parent)
    budget.finish_batch()
    pending = [identity for identity in SUBSET_IDS if identity not in known or not reusable(known[identity])]
    report["metadata"].update(
        status="incomplete" if pending else "complete", pending_scenario_ids=pending, stop_reason=None, resume_at=None
    )


def run(baseline: Path, ledger: Path, freeze: Path, output: Path, *, resume: bool = False) -> int:
    if output.resolve() == baseline.parent.resolve():
        raise SystemExit("P1 subset requires its own output directory")
    parent, metadata, scenarios = preflight(baseline, ledger, freeze)
    budget = MemberBudget(ledger, metadata["run_id"])
    report = load_state(output, metadata, resume=resume)
    prior_count = report["metadata"].get("membership", {}).get("run_calls_total", 0)
    if budget.snapshot()["run_calls_total"] < prior_count:
        raise SystemExit("P1 subset refuses rolled-back membership state")
    report["metadata"].setdefault("calls_before", budget.snapshot()["run_calls_total"])
    report["metadata"].update(status="incomplete", stop_reason=None, resume_at=None)
    judge, target = prepare(budget, parent)
    judge.records = list(report["evidence_full"])
    try:
        if budget.snapshot().get("reason") == "quota_5h":
            budget.resume_once()
        execute(report, scenarios, target, judge, budget, output, parent)
    except ProviderStopped as exc:
        report["metadata"].update(status="incomplete", stop_reason=exc.reason, resume_at=exc.resume_at)
        if exc.reason == "quota_weekly":
            report["metadata"]["warning"] = "线上可能受影响"
    except BaseException as exc:
        report["metadata"].update(status="incomplete", execution_error_code=type(exc).__name__, resume_at=None)
        raise
    finally:
        try:
            target.close()
        except BaseException as exc:
            report["metadata"].update(status="incomplete", cleanup_error_code=type(exc).__name__, resume_at=None)
            raise
        finally:
            save(report, output, budget, judge, parent)
    return 0 if report["metadata"]["status"] == "complete" else 3 if report["metadata"].get("resume_at") else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--freeze-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--follow", action="store_true")
    args = parser.parse_args()
    os.environ["LANGSMITH_TRACING"] = os.environ["LANGCHAIN_TRACING_V2"] = "false"
    while True:
        status = run(args.baseline, args.ledger, args.freeze_manifest, args.output, resume=args.resume)
        if not args.follow or status != 3:
            return status
        report = json.loads((args.output / STATE_NAME).read_text(encoding="utf-8"))
        wake = datetime.fromisoformat(report["metadata"]["resume_at"])
        while SystemClock().now().astimezone(UTC) < wake:
            time.sleep(min(60, max(0.1, (wake - SystemClock().now().astimezone(UTC)).total_seconds())))
        args.resume = True


if __name__ == "__main__":
    raise SystemExit(main())
