"""CLI for strict corpus validation, deterministic replay and real v3 baselines."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from mingjing_core.timekit.clock import get_clock  # noqa: E402
from tools.eval.batching import run_batches  # noqa: E402
from tools.eval.cli import lifecycle_selection, parser  # noqa: E402
from tools.eval.contracts import stamp_contracts  # noqa: E402
from tools.eval.engine import evaluate_scenario  # noqa: E402
from tools.eval.judges import JUDGE_SCHEMA, ModelJudge  # noqa: E402
from tools.eval.outcomes import is_infrastructure_failure  # noqa: E402
from tools.eval.report import add_comparison, summarize, write_report  # noqa: E402
from tools.eval.schema import Scenario, load_scenarios  # noqa: E402
from tools.eval.targets.base import Target  # noqa: E402

EVAL_ROOT = Path(__file__).parent


def _source_digest() -> str:
    candidates = list((ROOT / "tools/eval").rglob("*.py")) + list(
        ROOT.glob("requirements*.lock")
    )
    candidates += list((ROOT / "tools/eval/fixtures").glob("*.yaml"))
    runtime_config = ROOT / "config/runtime.yaml"
    if runtime_config.is_file():
        candidates.append(runtime_config)
    candidates += [
        path
        for path in (
            ROOT / "config/models.yaml",
            ROOT / "config/models.first-release.yaml",
            ROOT / "k3-tokenizer.lock.json",
        )
        if path.is_file()
    ]
    candidates += [
        path
        for path in (ROOT / "mingjing_core").rglob("*")
        if path.suffix in {".py", ".md", ".json", ".sql"}
    ]
    digest = hashlib.sha256()
    for path in sorted(candidates):
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(b"\x00")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _endpoint_digest() -> str:
    try:
        parsed = urlsplit(os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1"))
        normalized = f"{parsed.scheme}://{parsed.hostname}:{parsed.port or ''}{parsed.path.rstrip('/')}"
    except ValueError:
        raise ValueError("模型服务地址格式不可用") from None
    return hashlib.sha256(normalized.encode()).hexdigest()


def _metadata(
    config: dict[str, Any], mode: str, target: str, model: str
) -> dict[str, Any]:
    rubric = EVAL_ROOT / config["judge"]["rubric"]
    metadata = {
        "date": get_clock()
        .now()
        .astimezone(ZoneInfo("Asia/Shanghai"))
        .date()
        .isoformat(),
        "mode": mode,
        "target": target,
        "model": model,
        "judge_model": config["judge"]["model"]
        if mode == "live"
        else "not called (scripted)",
        "judge_provider": config["judge"].get("provider", "configured-model-v3"),
        "judge_schema_sha256": hashlib.sha256(
            json.dumps(JUDGE_SCHEMA, sort_keys=True).encode()
        ).hexdigest(),
        "rubric_version": config["judge"]["version"],
        "rubric_sha256": hashlib.sha256(rubric.read_bytes()).hexdigest(),
        "config_version": config["version"],
        "config_sha256": hashlib.sha256(
            json.dumps(config, sort_keys=True).encode()
        ).hexdigest(),
        "source_sha256": _source_digest(),
        "provider_endpoint_sha256": _endpoint_digest() if mode == "live" else None,
        "synthetic_only": True,
        "status": "running",
    }
    if target == "v4":
        metadata.update(
            evaluation_scope="real local PG + scripted ports/codec mocks; no live quality claim",
            external_provider_requests=0,
            u4_parser="actual shared U4 parser; original message time and owner timezone",
        )
        if mode == "live":
            metadata.update(
                evaluation_scope="production AgentRuntime + actual U4 + pinned local official K3 meter; synthetic PG",
                judge_model=model,
                judge_provider="locked ModelRegistry critic",
            )
    return metadata


def _target(
    name: str, model: str, mode: str = "scripted", suite: str = "default"
) -> Target:
    if name == "v4":
        if mode == "live":
            if suite == "core30":
                from tools.eval.targets.v4_core30 import Core30LiveTarget

                return Core30LiveTarget(model=model)
            from tools.eval.targets.v4_live import V4LiveTarget

            return V4LiveTarget(model=model)
        from tools.eval.targets.v4_target import V4Target

        return V4Target()
    if name == "fake":
        from tools.eval.targets.fake_target import FakeTarget

        return FakeTarget()
    from tools.eval.targets.v3_target import V3Target

    return V3Target(model=model)


def _fingerprint(scenario: Scenario, metadata: dict[str, Any]) -> str:
    keys = (
        "mode",
        "target",
        "model",
        "judge_model",
        "judge_provider",
        "judge_schema_sha256",
        "rubric_version",
        "rubric_sha256",
        "config_version",
        "config_sha256",
        "source_sha256",
        "provider_endpoint_sha256",
        "candidate_commit",
        "evaluation_suite",
    )
    fixed = {key: metadata.get(key) for key in keys}
    payload = {"scenario": scenario.model_dump(mode="json"), "metadata": fixed}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _resume_report(
    args: argparse.Namespace, metadata: dict[str, Any]
) -> dict[str, Any]:
    if not args.resume:
        return {}
    changed_source = False
    for path in sorted(args.output.glob("*.json"), reverse=True):
        if path.name == "baseline-v3.json":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        identity = (
            "target",
            "model",
            "mode",
            "config_sha256",
            "provider_endpoint_sha256",
        )
        same_run = all(
            data["metadata"].get(key) == metadata.get(key) for key in identity
        )
        if same_run and data["metadata"].get("source_sha256") != metadata.get(
            "source_sha256"
        ):
            changed_source = True
            continue
        keys = (
            "target",
            "model",
            "mode",
            "rubric_sha256",
            "config_sha256",
            "source_sha256",
            "provider_endpoint_sha256",
            "candidate_commit",
            "evaluation_suite",
        )
        if all(data["metadata"].get(key) == metadata.get(key) for key in keys):
            return data
    if changed_source:
        raise SystemExit(
            "Cannot resume across execution sources; use the preserved frozen execution snapshot"
        )
    return {}


def _reusable_cases(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        case["id"]: case
        for case in report.get("cases", [])
        if case["status"] in {"passed", "failed", "n/a on v3"}
        and not is_infrastructure_failure(case)
    }


def _resume_cases(
    args: argparse.Namespace, metadata: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    return _reusable_cases(_resume_report(args, metadata))


def _observe_case(
    scenario: Scenario,
    target: Target,
    judge: ModelJudge | None,
    metadata: dict[str, Any],
    previous: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    fingerprint = _fingerprint(scenario, metadata)
    cached = previous.get(scenario.id)
    reused = bool(cached and cached.get("fingerprint") == fingerprint)
    tracker = getattr(getattr(judge, "provider", None), "tracker", None)
    judge_before = tracker.external_calls if tracker is not None else 0
    case = (
        deepcopy(cached)
        if reused
        else evaluate_scenario(
            scenario, target, target_name=metadata["target"], judge=judge
        )
    )
    if not reused and metadata["target"] == "v4":
        case["v4_evidence"] = target.case_evidence()
        case["v4_evidence"]["judge_external_provider_requests"] = (
            tracker.external_calls - judge_before if tracker is not None else 0
        )
    case["fingerprint"] = fingerprint
    return case, reused


def _publish(report: dict[str, Any], output: Path) -> None:
    report["summary"] = summarize(report["cases"])
    write_report(report, output)


def _run(
    args: argparse.Namespace,
    scenarios: list[Scenario],
    config: dict[str, Any],
    model: str,
) -> int:
    metadata = _metadata(config, args.mode, args.target, model)
    metadata.update(getattr(args, "candidate_provenance", {}))
    metadata["evaluation_suite"] = getattr(args, "suite", "default")
    metadata["unavailable_retry"] = getattr(args, "unavailable_retry", 0)
    if getattr(args, "fresh_questions_from", None) is not None:
        metadata["fresh_questions_from_sha256"] = hashlib.sha256(
            args.fresh_questions_from.read_bytes()
        ).hexdigest()
    prior_report = _resume_report(args, metadata)
    previous = _reusable_cases(prior_report)
    report: dict[str, Any] = {
        "metadata": metadata,
        "cases": [],
        "batches": deepcopy(prior_report.get("batches", [])),
    }
    metadata["planned_scenario_ids"] = [scenario.id for scenario in scenarios]
    scenario_map = {scenario.id: scenario for scenario in scenarios}
    judge = None
    if args.mode == "live" and args.target == "v4":
        from tools.eval.targets.v4_live_judge import V4LiveJudge

        judge = V4LiveJudge(model, EVAL_ROOT / config["judge"]["rubric"])
    elif args.mode == "live":
        judge = ModelJudge(
            config["judge"]["model"], EVAL_ROOT / config["judge"]["rubric"]
        )
    target = _target(args.target, model, args.mode, getattr(args, "suite", "default"))
    for scenario in scenarios:
        cached = previous.get(scenario.id)
        if cached and cached.get("fingerprint") == _fingerprint(scenario, metadata):
            report["cases"].append(deepcopy(cached))
        elif args.target == "v3" and "v3" not in scenario.targets:
            report["cases"].append(
                evaluate_scenario(scenario, target, target_name="v3")
            )
    try:
        run_batches(
            scenarios,
            report,
            lambda scenario: _observe_case(scenario, target, judge, metadata, previous),
            lambda: _publish_contract_report(report, args.output, scenario_map),
            batch_size=getattr(args, "batch_size", 10),
        )
    finally:
        target.close()
    stamp_contracts(report, scenario_map)
    return _finish(args, scenarios, report)


def _publish_contract_report(
    report: dict[str, Any], output: Path, scenarios: dict[str, Scenario]
) -> None:
    if (
        report["metadata"].get("mode") == "live"
        and report["metadata"].get("target") == "v4"
    ):
        from tools.eval.live import update_live_metadata

        update_live_metadata(report["metadata"])
        report["metadata"].update(
            physical_requests=sum(
                case.get("model_calls", 0) for case in report["cases"]
            ),
            external_provider_requests=sum(
                case.get("v4_evidence", {}).get("external_provider_requests", 0)
                + case.get("v4_evidence", {}).get("judge_external_provider_requests", 0)
                for case in report["cases"]
            ),
        )
    stamp_contracts(report, scenarios)
    _publish(report, output)


def _finish(
    args: argparse.Namespace, scenarios: list[Scenario], report: dict[str, Any]
) -> int:
    metadata = report["metadata"]
    complete = (
        len(report["cases"]) == len(scenarios)
        and not any(is_infrastructure_failure(case) for case in report["cases"])
        and not metadata.get("stop_reason")
    )
    metadata["status"] = "complete" if complete else "incomplete"
    core_accepted = True
    if getattr(args, "suite", "default") == "core30":
        from tools.eval.targets.v4_core30 import acceptance

        metadata["core30_acceptance"] = acceptance(report["cases"])
        core_accepted = metadata["core30_acceptance"]["accepted"]
    add_comparison(report, args.output / "baseline-v3.json")
    baseline = (
        complete
        and args.mode == "live"
        and args.target == "v3"
        and not args.scenario
        and len(scenarios) == 80
    )
    paths = write_report(report, args.output, baseline=baseline)
    summary = report["summary"]
    print(
        f"Result: {summary['passed']}/{summary['count']}; n/a on v3: {summary['not_applicable']}"
    )
    print(
        "Reports: "
        + ", ".join(
            str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
            for path in paths
        )
    )
    return (
        2
        if metadata.get("stop_reason")
        else int(
            not complete
            or not core_accepted
            or args.mode == "scripted"
            and summary["passed"] != summary["count"]
        )
    )


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    args.target = args.target or ("v3" if args.mode == "live" else "fake")
    lifecycle_selection(args)
    if args.unavailable_retry and (
        args.mode != "live"
        or args.target != "v4"
        or args.suite != "core30"
        or args.fresh_questions_from is None
    ):
        raise SystemExit("R22 retry requires same-source core30 fresh-question report")
    if (args.mode, args.target) not in {
        ("scripted", "fake"),
        ("live", "v3"),
        ("scripted", "v4"),
        ("live", "v4"),
    }:
        raise SystemExit(
            "Supported modes: scripted/fake, scripted/v4, live/v3 and gated live/v4"
        )
    if args.suite == "core30":
        from tools.eval.targets.v4_core30 import load_core30

        if (
            args.target != "v4"
            or args.scenario
            or args.scenarios.resolve() != (EVAL_ROOT / "scenarios").resolve()
        ):
            raise SystemExit(
                "core30 requires v4 and its exact isolated selection; no custom scenario subset"
            )
        scenarios = load_core30()
        if args.fresh_questions_from is not None:
            from tools.eval.k31_results import pending_questions

            if (
                args.mode != "live"
                or args.connection_proof is None
                or args.resume
                or not args.candidate
            ):
                raise SystemExit(
                    "R12 fresh questions require R16 live proof and a new invocation"
                )
            previous = json.loads(args.fresh_questions_from.read_text(encoding="utf-8"))
            pending = pending_questions(
                previous,
                args.candidate,
                _source_digest(),
                unavailable_retry=args.unavailable_retry,
            )
            scenarios = [scenario for scenario in scenarios if scenario.id in pending]
    else:
        if args.fresh_questions_from is not None:
            raise SystemExit(
                "R12 fresh questions require the original core30 selection"
            )
        if (
            args.target == "v4"
            and args.scenarios.resolve() == (EVAL_ROOT / "scenarios").resolve()
        ):
            args.scenarios = EVAL_ROOT / "scenarios_v4"
        scenarios = load_scenarios(args.scenarios)
    if not scenarios:
        raise SystemExit("No scenarios found")
    if (
        args.suite != "core30"
        and args.scenarios.resolve() == (EVAL_ROOT / "scenarios").resolve()
        and len(scenarios) != 80
    ):
        raise SystemExit(f"Expected 80 corpus scenarios, found {len(scenarios)}")
    print(f"Validated {len(scenarios)}/{len(scenarios)} scenarios")
    if args.validate_only:
        return 0
    if args.candidate:
        from tools.eval.live import candidate_provenance

        private_output = (ROOT / "private/candidate-eval" / args.candidate).resolve()
        if not args.output.resolve().is_relative_to(private_output):
            raise SystemExit(
                "Candidate reports require private/candidate-eval/<candidate> output"
            )
        args.candidate_provenance = candidate_provenance(ROOT, args.candidate)
    if args.scenario:
        requested = set(args.scenario.split(","))
        scenarios = [scenario for scenario in scenarios if scenario.id in requested]
        if requested != {scenario.id for scenario in scenarios}:
            raise SystemExit("Unknown scenario ID")
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    if args.mode == "live" and not (
        os.getenv("KIMI_API_KEY") or os.getenv("MOONSHOT_API_KEY")
    ):
        raise SystemExit(
            "Live preflight failed: provide KIMI_API_KEY or MOONSHOT_API_KEY through process environment"
        )
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    scripted_model = "scripted-v4" if args.target == "v4" else "scripted-v1"
    models = (
        (args.models or args.model).split(",")
        if args.mode == "live"
        else [scripted_model]
    )
    status = _run_models(args, scenarios, config, models)
    if status == 2:
        return 2
    if args.self_test:
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/v4/test_eval_framework.py", "-q"],
            cwd=ROOT,
            check=False,
        )
        status = max(status, completed.returncode)
    return status


def _run_models(
    args: argparse.Namespace,
    scenarios: list[Scenario],
    config: dict[str, Any],
    models: list[str],
) -> int:
    lifecycle = lifecycle_selection(args)
    if getattr(args, "mode", None) == "live" and getattr(args, "target", None) == "v4":
        from tools.eval.live import live_session
        from tools.eval.model_selection import selected_model

        if len(models) != 1:
            raise SystemExit(
                "Live v4 executes one proof-selected model, never a CLI fallback chain"
            )
        with live_session(args, [scenario.id for scenario in scenarios]) as active:
            selected = selected_model()
            if models[0] not in {"kimi", "kimi-main", selected}:
                raise SystemExit(
                    "Requested model differs from the trusted equivalence proof"
                )
            if lifecycle:
                from tools.eval.session_driver import run_session

                return run_session(args, scenarios, config, selected, active)
            return _run(args, scenarios, config, selected)
    status = 0
    for name in models:
        model = config["models"].get(name, name)
        if name in {"kimi", "kimi-main"}:
            model = os.getenv("KIMI_MODEL", model)
        result = _run(args, scenarios, config, model)
        status = max(status, result)
        if result == 2:
            break
    return status


if __name__ == "__main__":
    raise SystemExit(main())
