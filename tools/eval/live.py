"""A same-candidate scripted gate precedes live v4 target and external judge I/O."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from mingjing_core.models.quota_delegated_session import DelegatedSession
from mingjing_core.models.quota_mode import current_delegated_session
from mingjing_core.models.quota_runtime import CentralLocation
from mingjing_core.models.quota_types import GuardRejected
from tools.member_delegate import candidate_gate
from tools.probe_equivalence_control import ProbeControl
from tools.probe_equivalence_proof import load_core_approval


def candidate_provenance(root: Path, candidate: str) -> dict[str, Any]:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    paths = ["mingjing_core", "tools", "config", "requirements-core.lock", "k3-tokenizer.lock.json"]
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--", *paths], cwd=root, text=True)
    if head != candidate or dirty.strip():
        raise GuardRejected("batch_conflict")
    return {"candidate_commit": head, "worktree_clean": True}


@contextmanager
def live_session(args: Any, scenario_ids: Sequence[str]) -> Iterator[DelegatedSession]:
    # Scenario-result reuse creates a new run/schema. It cannot safely resume a
    # physical quota window until the original run and completed turns persist.
    if getattr(args, "resume", False):
        raise GuardRejected("manual_start_required")
    if getattr(args, "connection_proof", None) is not None:
        from tools.eval.k31_live import core_session

        with core_session(args, scenario_ids) as session:
            yield session
        return
    path, candidate = getattr(args, "scripted_gate", None), getattr(args, "candidate", None)
    proof, schema = getattr(args, "equivalence_proof", None), getattr(args, "control_schema", None)
    if path is None or not candidate or proof is None or not schema:
        raise GuardRejected("manual_start_required")
    guard = CentralLocation.from_environment().guard()
    from tools.eval.runner import _source_digest

    try:
        scripted = candidate_gate(path, candidate, guard.clock.now())
        control = ProbeControl(os.getenv("PROBE_CONTROL_DSN") or os.getenv("CORE_TEST_DSN", ""), schema)
        approval = load_core_approval(guard, scripted, proof, control=control, source_sha256=_source_digest())
    except (OSError, ValueError):
        raise GuardRejected("manual_start_required") from None
    session = DelegatedSession(guard, approval, phase="core", scenario_ids=scenario_ids)
    try:
        with session.activate():
            yield session
    finally:
        session.close()


def update_live_metadata(metadata: dict[str, Any]) -> None:
    session = current_delegated_session()
    if session is None or metadata.get("mode") != "live" or metadata.get("target") != "v4":
        return
    metadata.update(
        central_physical_batch=session.snapshot(),
        actual_ledger_time=session.guard.clock.now().isoformat(),
        scenario_batch_size_unit="scenarios; physical HTTP batches are centrally limited to 10",
        global_physical_concurrency=1,
    )
