"""A same-candidate scripted gate precedes live v4 target and external judge I/O."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from mingjing_core.models.quota_delegated import resume_delegated
from mingjing_core.models.quota_delegated_session import DelegatedSession
from mingjing_core.models.quota_mode import current_delegated_session
from mingjing_core.models.quota_runtime import CentralLocation
from mingjing_core.models.quota_types import GuardRejected
from tools.member_delegate import candidate_gate


def candidate_provenance(root: Path, candidate: str) -> dict[str, Any]:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    paths = ["mingjing_core", "tools", "config", "requirements-core.lock", "k3-tokenizer.lock.json"]
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--", *paths], cwd=root, text=True)
    if head != candidate or dirty.strip():
        raise GuardRejected("batch_conflict")
    return {"candidate_commit": head, "worktree_clean": True}


@contextmanager
def live_session(args: Any, scenario_ids: Sequence[str]) -> Iterator[DelegatedSession]:
    path, candidate = getattr(args, "scripted_gate", None), getattr(args, "candidate", None)
    if path is None or not candidate:
        raise GuardRejected("manual_start_required")
    guard = CentralLocation.from_environment().guard()
    approval = candidate_gate(path, candidate, guard.clock.now())
    if getattr(args, "resume", False):
        resume_delegated(guard, approval)
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
