"""CLI definitions remain separate from evaluation and physical authorization."""

from __future__ import annotations

import argparse
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
    return result
