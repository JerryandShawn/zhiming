"""Issue one v7 delegated batch after a same-candidate scripted gate; no model I/O."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mingjing_core.models.quota_delegated import (  # noqa: E402
    DelegatedApproval,
    approval_from_gate,
    begin_delegated_batch,
    resume_delegated,
)
from mingjing_core.models.quota_runtime import CentralLocation  # noqa: E402
from mingjing_core.models.quota_types import GuardRejected  # noqa: E402
from tools.manual_grant_io import write_private_receipt  # noqa: E402


def candidate_gate(path: Path, candidate: str, now: datetime) -> DelegatedApproval:
    root = Path(__file__).resolve().parents[1]
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    paths = [
        "mingjing_core",
        "tools",
        "config",
        "requirements-core.lock",
        "k3-tokenizer.lock.json",
    ]
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--", *paths], cwd=root, text=True)
    if head != candidate or dirty.strip() or path.stat().st_size > 16384:
        raise GuardRejected("batch_conflict")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("synthetic") is not False:
        raise GuardRejected("manual_start_required")
    from tools.eval.runner import _source_digest

    if value.get("source_sha256") != _source_digest():
        raise GuardRejected("batch_conflict")
    return approval_from_gate(value, candidate, now)


def _rejected(error: Exception) -> int:
    print(json.dumps({"ok": False, "code": getattr(error, "code", "DELEGATION_REJECTED"), "model_calls": 0}))
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scripted-gate", type=Path, required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--phase", choices=("equivalence", "core"), default="equivalence")
    parser.add_argument("--batch-id")
    parser.add_argument("--scenario", action="append", default=[])
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--resume-ready", action="store_true")
    args = parser.parse_args(argv)
    try:
        guard = CentralLocation.from_environment().guard()
        approval = candidate_gate(args.scripted_gate, args.candidate, guard.clock.now())
        if args.resume_ready:
            resumed = resume_delegated(guard, approval)
            print(json.dumps({"ok": True, "resumed": resumed, "model_calls": 0}))
            return 0
        if args.receipt is None or args.receipt.exists() or not args.receipt.parent.is_dir():
            raise GuardRejected("manual_start_required")
        receipt = begin_delegated_batch(
            guard,
            approval,
            phase=args.phase,
            batch_id=args.batch_id,
            scenario_ids=args.scenario,
        )
        try:
            protection = write_private_receipt(args.receipt, receipt)
        except OSError:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "code": "DELEGATION_CREATED_RECEIPT_WRITE_FAILED",
                        "model_calls": 0,
                        "batch_id": receipt["batch_id"],
                        "expires_at": receipt["expires_at"],
                    }
                )
            )
            return 2
        print(
            json.dumps(
                {
                    "ok": True,
                    "schema": receipt["schema"],
                    "model_calls": 0,
                    "protection": protection,
                }
            )
        )
        return 0
    except Exception as error:
        return _rejected(error)


if __name__ == "__main__":
    raise SystemExit(main())
