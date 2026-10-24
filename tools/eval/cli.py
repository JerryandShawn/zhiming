"""CLI definitions remain separate from evaluation and physical authorization."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

EVAL_ROOT = Path(__file__).parent
ROOT = EVAL_ROOT.parents[1]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Strict synthetic corpus evaluation")
    result.add_argument("--mode", choices=["scripted", "live"], default="scripted")
    result.add_argument("--target", choices=["fake", "v3", "v4"], default=None)
    result.add_argument("--suite", choices=["default", "core30"], default="default")
    result.add_argument("--model", default="kimi")
    result.add_argument(
        "--models", help="Comma-separated primary model names; gated v4 permits one proof-selected model"
    )
    result.add_argument("--config", type=Path, default=EVAL_ROOT / "config.yaml")
    result.add_argument("--scenarios", type=Path, default=EVAL_ROOT / "scenarios")
    result.add_argument("--scenario", help="Comma-separated scenario IDs")
    result.add_argument("--scripted-gate", type=Path, help="Same-candidate completed scripted gate for live/v4")
    result.add_argument("--candidate", help="Exact clean candidate commit to record and verify")
    result.add_argument(
        "--equivalence-proof", type=Path, help="Read-only proof rechecked against control and central PG"
    )
    result.add_argument("--control-schema", help="Previously initialized independent probe_ control schema")
    result.add_argument("--output", type=Path, default=ROOT / "docs/v4/eval")
    result.add_argument(
        "--batch-size", type=int, choices=range(1, 11), default=10, help="Scenario count; not physical HTTP"
    )
    result.add_argument("--validate", "--validate-only", action="store_true", dest="validate_only")
    result.add_argument("--self-test", action="store_true")
    result.add_argument(
        "--resume", action="store_true", help="Reuse matching scenario results; not durable same-run recovery"
    )
    result.add_argument("--lifecycle-session", help="Exact previously saved eval- session; current turn only")
    result.add_argument("--lifecycle-schema", help="Previously initialized independent eval_control_ schema")
    result.add_argument("--lifecycle-scenario", help="Exact core30 scenario bound to the saved session")
    return result


def lifecycle_selection(args: argparse.Namespace) -> bool:
    values = [getattr(args, "lifecycle_" + key, None) for key in ("session", "schema", "scenario")]
    if all(value is None for value in values):
        return False
    from tools.eval.targets.v4_core30 import CORE30_IDS

    if (
        any(value is None for value in values)
        or (args.mode, args.target, args.suite) != ("live", "v4", "core30")
        or args.resume
        or args.validate_only
        or args.self_test
        or args.scenario
        or args.scenarios.resolve() != (EVAL_ROOT / "scenarios").resolve()
        or re.fullmatch(r"eval-[a-f0-9]{32}", values[0] or "") is None
        or re.fullmatch(r"eval_control_[a-z0-9_]{1,49}", values[1] or "") is None
        or values[2] not in CORE30_IDS
    ):
        raise SystemExit("Lifecycle selection requires all three exact flags and live/v4/core30 without other modes")
    return True
