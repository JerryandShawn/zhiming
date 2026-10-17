"""CLI for strict corpus validation, deterministic replay and real v3 baselines."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from mingjing_core.timekit.clock import get_clock  # noqa: E402
from tools.eval.engine import evaluate_scenario  # noqa: E402
from tools.eval.judges import ModelJudge  # noqa: E402
from tools.eval.report import add_comparison, summarize, write_report  # noqa: E402
from tools.eval.schema import Scenario, load_scenarios  # noqa: E402
from tools.eval.targets.base import Target  # noqa: E402

EVAL_ROOT = Path(__file__).parent


def _source_digest() -> str:
    candidates = list((ROOT / "tools/eval").rglob("*.py")) + list(ROOT.glob("requirements*.lock"))
    candidates += list((ROOT / "tools/eval/fixtures").glob("*.yaml"))
    candidates += [
        path for path in (ROOT / "mingjing_core").rglob("*") if path.suffix in {".py", ".md", ".json", ".sql"}
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


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--mode", choices=["scripted", "live"], default="scripted")
    result.add_argument("--target", choices=["fake", "v3"], default=None)
    result.add_argument("--model", default="kimi")
    result.add_argument("--models", help="Comma-separated primary model names; each gets its own report")
    result.add_argument("--config", type=Path, default=EVAL_ROOT / "config.yaml")
    result.add_argument("--scenarios", type=Path, default=EVAL_ROOT / "scenarios")
    result.add_argument("--scenario", help="Comma-separated scenario IDs")
    result.add_argument("--output", type=Path, default=ROOT / "docs/v4/eval")
    result.add_argument("--validate", "--validate-only", action="store_true", dest="validate_only")
    result.add_argument("--self-test", action="store_true")
    result.add_argument(
        "--resume",
        action="store_true",
        help="Reuse matching completed scenario results",
    )
    return result


def _metadata(config: dict[str, Any], mode: str, target: str, model: str) -> dict[str, Any]:
    rubric = EVAL_ROOT / config["judge"]["rubric"]
    return {
        "date": get_clock().now().astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat(),
        "mode": mode,
        "target": target,
        "model": model,
        "judge_model": config["judge"]["model"] if mode == "live" else "not called (scripted)",
        "rubric_version": config["judge"]["version"],
        "rubric_sha256": hashlib.sha256(rubric.read_bytes()).hexdigest(),
        "config_version": config["version"],
        "config_sha256": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
        "source_sha256": _source_digest(),
        "provider_endpoint_sha256": _endpoint_digest() if mode == "live" else None,
        "synthetic_only": True,
        "status": "running",
    }


def _target(name: str, model: str) -> Target:
    if name == "fake":
        from tools.eval.targets.fake_target import FakeTarget

        return FakeTarget()
    from tools.eval.targets.v3_target import V3Target

    return V3Target(model=model)


def _fingerprint(scenario: Scenario, metadata: dict[str, Any]) -> str:
    fixed = {key: value for key, value in metadata.items() if key not in {"date", "status"}}
    payload = {"scenario": scenario.model_dump(mode="json"), "metadata": fixed}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _resume_cases(args: argparse.Namespace, metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not args.resume:
        return {}
    for path in sorted(args.output.glob("*.json"), reverse=True):
        if path.name == "baseline-v3.json":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        keys = (
            "target",
            "model",
            "mode",
            "rubric_sha256",
            "config_sha256",
            "source_sha256",
            "provider_endpoint_sha256",
        )
        if all(data["metadata"].get(key) == metadata.get(key) for key in keys):
            return {case["id"]: case for case in data["cases"]}
    return {}


def _run(
    args: argparse.Namespace,
    scenarios: list[Scenario],
    config: dict[str, Any],
    model: str,
) -> int:
    metadata = _metadata(config, args.mode, args.target, model)
    report: dict[str, Any] = {"metadata": metadata, "cases": []}
    previous = _resume_cases(args, metadata)
    judge = ModelJudge(config["judge"]["model"], EVAL_ROOT / config["judge"]["rubric"]) if args.mode == "live" else None
    target = _target(args.target, model)
    try:
        for scenario in scenarios:
            fingerprint = _fingerprint(scenario, metadata)
            cached = previous.get(scenario.id)
            case = (
                cached
                if cached and cached.get("fingerprint") == fingerprint
                else evaluate_scenario(scenario, target, target_name=args.target, judge=judge)
            )
            case["fingerprint"] = fingerprint
            report["cases"].append(case)
            report["summary"] = summarize(report["cases"])
            write_report(report, args.output)
            print(f"{scenario.id}: {case['status']} score={case['score']}", flush=True)
    finally:
        target.close()
    complete = not any(
        case.get("error_code") or case.get("judge_error_code") or case.get("target_error_code")
        for case in report["cases"]
    )
    metadata["status"] = "complete" if complete else "incomplete"
    add_comparison(report, args.output / "baseline-v3.json")
    baseline = complete and args.mode == "live" and args.target == "v3" and not args.scenario and len(scenarios) == 80
    paths = write_report(report, args.output, baseline=baseline)
    summary = report["summary"]
    print(f"Result: {summary['passed']}/{summary['count']}; n/a on v3: {summary['not_applicable']}")
    print(
        "Reports: "
        + ", ".join(str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path) for path in paths)
    )
    return int(not complete or args.mode == "scripted" and summary["passed"] != summary["count"])


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    args.target = args.target or ("v3" if args.mode == "live" else "fake")
    if (args.mode, args.target) not in {("scripted", "fake"), ("live", "v3")}:
        raise SystemExit("P0 supports scripted/fake and live/v3 only")
    scenarios = load_scenarios(args.scenarios)
    if not scenarios:
        raise SystemExit("No scenarios found")
    if args.scenarios.resolve() == (EVAL_ROOT / "scenarios").resolve() and len(scenarios) != 80:
        raise SystemExit(f"Expected 80 corpus scenarios, found {len(scenarios)}")
    print(f"Validated {len(scenarios)}/{len(scenarios)} scenarios")
    if args.validate_only:
        return 0
    if args.scenario:
        requested = set(args.scenario.split(","))
        scenarios = [scenario for scenario in scenarios if scenario.id in requested]
        if requested != {scenario.id for scenario in scenarios}:
            raise SystemExit("Unknown scenario ID")
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    if args.mode == "live" and not (os.getenv("KIMI_API_KEY") or os.getenv("MOONSHOT_API_KEY")):
        raise SystemExit("Live preflight failed: provide KIMI_API_KEY or MOONSHOT_API_KEY through process environment")
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    models = (args.models or args.model).split(",") if args.mode == "live" else ["scripted-v1"]
    status = 0
    for name in models:
        model = config["models"].get(name, name)
        if name in {"kimi", "kimi-main"}:
            model = os.getenv("KIMI_MODEL", model)
        status = max(status, _run(args, scenarios, config, model))
    if args.self_test:
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/v4/test_eval_framework.py", "-q"],
            cwd=ROOT,
            check=False,
        )
        status = max(status, completed.returncode)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
