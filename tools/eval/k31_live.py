"""Trusted R16 core scope consumes a live connection proof rechecked in PG."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager

from mingjing_core.models.quota_delegated_session import DelegatedSession
from mingjing_core.models.quota_runtime import CentralLocation
from mingjing_core.models.quota_types import GuardRejected
from tools.eval.k31_control import K31Control, core_approval
from tools.eval.r11_gate import candidate_r11


@contextmanager
def core_session(args, scenario_ids):
    if (
        args.equivalence_proof is not None
        or args.scripted_gate is None
        or not args.candidate
        or not args.control_schema
    ):
        raise GuardRejected("manual_start_required")
    path = args.connection_proof
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
        raise GuardRejected("manual_start_required")
    guard = CentralLocation.from_environment().guard()
    scripted = candidate_r11(args.scripted_gate, args.candidate, guard.clock.now())
    control = K31Control(os.getenv("PROBE_CONTROL_DSN", ""), args.control_schema)
    approval = core_approval(guard, scripted, json.loads(path.read_text(encoding="utf-8")), control)
    session = DelegatedSession(guard, approval, phase="core", scenario_ids=scenario_ids)
    try:
        with session.activate():
            yield session
    finally:
        session.close()
