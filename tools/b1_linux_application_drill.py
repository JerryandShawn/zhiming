"""Plan by default; explicit offline runtime/backfill/fcntl application rehearsal."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from tools.b1_linux_application_drill_contracts import ApplicationBlocked, ApplicationRequest, require
from tools.b1_linux_application_drill_process import run_worker
from tools.b1_restore_replay import protected_output
from tools.core_incremental_contracts import EXPECTED_MANIFEST, TARGET


def plan() -> dict[str, Any]:
    return {
        "schema": "b1-linux-application-plan-v1",
        "target": TARGET,
        "manifest_sha256": EXPECTED_MANIFEST,
        "phases": ["runtime", "backfill", "fence"],
        "default_side_effects": False,
        "runtime": "actual Linux Core Python 3.11/exact locked packages/installed Requires-Dist; no installs",
        "backfill": "synthetic-only primary dry/apply/repeat; fixed b9; exact separate owner",
        "fence": "actual Linux flock and exec; inert CLI/temporary paths; no DB or systemd",
        "bootstrap_checkpoint_backup": "not-yet-wired",
        "B7": "separate-reviewed-existing-entry-required",
        "linux_actual_execution": "blocked-environment",
        "publication": False,
        "models": 0,
        "sends": 0,
    }


def execute(request: ApplicationRequest, output: Path) -> dict[str, Any]:
    from mingjing_core.timekit.clock import get_clock

    require(output.is_absolute() and output.parent.is_dir() and not output.exists(), "NEW_APPLICATION_OUTPUT")
    require(not output.is_symlink() and not any(path.is_symlink() for path in output.parents), "NEW_APPLICATION_OUTPUT")
    result = run_worker(request)
    receipt = {
        "schema": "b1-local-application-drill-v1" if request.local_drill else "b1-linux-application-drill-v1",
        "operation_id": request.operation_id,
        "phase": request.phase,
        "target": TARGET,
        "manifest_sha256": EXPECTED_MANIFEST,
        "at": get_clock().now().astimezone(ZoneInfo("Asia/Shanghai")).isoformat(),
        "admissible_linux": not request.local_drill,
        "publication": False,
        "models": 0,
        "sends": 0,
        "stage_acceptance": False,
        **result,
    }
    protected_output(output, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--local-drill", action="store_true")
    for name in ("operation-id", "phase", "candidate-source", "candidate-python", "output"):
        parser.add_argument("--" + name)
    args = parser.parse_args()
    if not args.apply:
        print(json.dumps(plan(), sort_keys=True))
        return 0
    try:
        require(
            all(
                getattr(args, name.replace("-", "_"))
                for name in ("operation-id", "phase", "candidate-source", "candidate-python", "output")
            ),
            "APPLICATION_INPUTS",
        )
        request = ApplicationRequest(
            args.operation_id, args.phase, Path(args.candidate_source), Path(args.candidate_python), args.local_drill
        )
        value = execute(request, Path(args.output))
    except ApplicationBlocked as error:
        print(json.dumps({"status": "blocked", "code": str(error)}))
        return 2
    except Exception:
        print(json.dumps({"status": "blocked", "code": "APPLICATION_FAILED_DETAILS_WITHHELD"}))
        return 2
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
