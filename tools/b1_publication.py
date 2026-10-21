"""Explicit verify/open/config-rollback after an independently verified DB restore."""

from __future__ import annotations

import argparse
import json
from contextlib import AbstractContextManager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from mingjing_core.timekit.clock import Clock, get_clock
from tools.b1_publication_contracts import (
    ZONE, Plan, PublicationRejected, authorize, controller_hash, require, validate_review,
)
from tools.core_incremental_contracts import LIVE_UNITS, PREVIOUS, TARGET


class PublicationPort(Protocol):
    def review(self, plan: Plan) -> bytes: ...
    def guard(self, plan: Plan) -> None: ...
    def fence(self, plan: Plan) -> AbstractContextManager[None]: ...
    def snapshot(self, plan: Plan, *, restored: bool = False) -> dict[str, Any]: ...
    def restore_unit(self, unit: str, *, active: bool, enabled: bool) -> None: ...
    def health(self, plan: Plan) -> None: ...
    def opening_checks(self, plan: Plan) -> None: ...
    def open_gate(self, plan: Plan, at: datetime) -> None: ...
    def opened_at(self, plan: Plan) -> datetime | None: ...
    def restore_original_files(self, plan: Plan) -> None: ...
    def keep_closed(self, plan: Plan) -> None: ...


def verify_snapshot(value: dict[str, Any], *, restored: bool) -> None:
    require(value.get("schema") == (4 if restored else 7), "PUBLICATION_DATABASE_SCHEMA")
    for key in ("identity_verified", "checksums_verified", "runtime_safe", "files_verified", "env_verified",
                "release_verified", "rollback_ready", "maintenance", "fence_held"):
        require(value.get(key) is True, "PUBLICATION_NOT_READY_" + key.upper())
    require(value.get("queues") == {"queued": 0, "running": 0, "leases": 0}, "PUBLICATION_NONEMPTY_QUEUE")
    require(type(value.get("other_sessions")) is int and value["other_sessions"] == 0, "PUBLICATION_UNFENCED_CLIENT")
    require(value.get("writers_stopped") == list(LIVE_UNITS), "PUBLICATION_WRITER_ACTIVE")


def activate(plan: Plan, port: PublicationPort, clock: Clock) -> dict[str, Any]:
    web = "mingjingtai.service"
    port.restore_unit(web, active=True, enabled=plan.raw["unit_states"][web]["enabled"])
    port.health(plan)
    # The original background workers do not share the Web maintenance gate.
    # Therefore the first public opening is explicitly recorded before they start.
    port.opening_checks(plan)
    now = clock.now().astimezone(ZONE)
    require(plan.start <= now < plan.end, "WINDOW_ENDED_BEFORE_OPEN")
    port.open_gate(plan, now)
    for unit in LIVE_UNITS:
        state = plan.raw["unit_states"][unit]
        if unit != web:
            port.restore_unit(unit, active=state["active"], enabled=state["enabled"])
    port.health(plan)
    return {"status": "opened", "opened_at": now.isoformat(), "target": TARGET,
            "opening_mode": "web_then_background", "atomic_opening": False,
            "controller_model_calls": 0, "controller_external_sends": 0,
            "background_business_resumed": True, "smoke_request_performed": False}


def execute(
    raw: dict[str, Any], approval: dict[str, Any], port: PublicationPort, *, action: str,
    clock: Clock | None = None, controller: str | None = None,
) -> dict[str, Any]:
    clock = clock or get_clock()
    plan = Plan.parse(raw)
    authorize(plan, approval, action, clock.now(), controller or controller_hash())
    validate_review(plan, port.review(plan))
    port.guard(plan)
    entered = False
    try:
        with port.fence(plan):
            entered = True
            if action == "rollback":
                opened = port.opened_at(plan)
                require(opened is not None and timedelta(0) <= clock.now() - opened <= timedelta(minutes=60),
                        "ROLLBACK_OUTSIDE_FIRST_HOUR")
                port.keep_closed(plan)
                verify_snapshot(port.snapshot(plan, restored=True), restored=True)
                port.restore_original_files(plan)
                return {"status": "rollback_configured_closed", "target": PREVIOUS,
                        "publication": False, "requires_old_package_inner_checks": True,
                        "model_calls": 0, "external_sends": 0}
            verify_snapshot(port.snapshot(plan), restored=False)
            if action == "verify":
                return {"status": "verified_closed", "publication": False,
                        "model_calls": 0, "external_sends": 0}
            return activate(plan, port, clock)
    except BaseException:
        if entered:
            port.keep_closed(plan)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", choices=("verify", "open", "rollback"), required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        raw = json.loads(args.plan.read_text(encoding="utf-8"))
        plan = Plan.parse(raw)
        if not args.apply:
            print(json.dumps({"validated_plan": True, "action": args.action,
                              "controller_sha256": controller_hash(), "publication": False}))
            return 0
        require(args.native and args.approval is not None and args.output is not None,
                "EXPLICIT_NATIVE_APPROVAL_AND_OUTPUT_REQUIRED")
        from tools.b1_publication_native import NativePublicationPort
        from tools.core_incremental_files import private_write, regular

        regular(args.plan, private=True)
        regular(args.approval, private=True)
        approval = json.loads(args.approval.read_text(encoding="utf-8"))
        port = NativePublicationPort()
        try:
            result = execute(plan.raw, approval, port, action=args.action)
            private_write(args.output, (json.dumps(result, sort_keys=True) + "\n").encode())
        except BaseException:
            if port.touched:
                port.keep_closed(plan)
            raise
        print(json.dumps({"status": result["status"], "publication": result.get("status") == "opened"}))
        return 0
    except (Exception, KeyboardInterrupt) as error:
        code = str(error) if isinstance(error, PublicationRejected) else "PUBLICATION_FAILED"
        print(json.dumps({"ok": False, "code": code, "publication": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
