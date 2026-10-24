"""Ephemeral pre-clear eligibility only: no clear-stop, claim, execution, or CLI."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from mingjing_core.models.quota_delegated_session import require_active
from tools.eval.lifecycle_identity import LifecycleError
from tools.eval.quota_resume_evidence import ResumeEvidence, gather, require, typed


class QuotaResumeWitness:
    __slots__ = ()

    def __new__(cls) -> QuotaResumeWitness:
        raise LifecycleError("QUOTA_RESUME_OPAQUE_WITNESS_REQUIRED")

    def __reduce__(self) -> Any:
        raise LifecycleError("QUOTA_RESUME_WITNESS_NOT_SERIALIZABLE")


@dataclass(frozen=True, repr=False)
class _Entry:
    witness: QuotaResumeWitness
    target: Any
    repo: Any
    control: Any
    binding: Any
    guard: Any
    session: Any
    context: object
    evidence: ResumeEvidence


@dataclass(frozen=True)
class EligibilitySummary:
    evidence_sha256: str
    run_id: str
    epoch: int
    turn: int
    seq: int
    reset_at: str
    consumed_ns: int
    has_text: bool
    execution_authority: bool = False
    central_stop_cleared: bool = False
    model_calls: int = 0


_LIVE: dict[int, _Entry] = {}
_ACTIVE: ContextVar[object | None] = ContextVar("quota_resume_preclear_context", default=None)


def _session(target: Any, binding: Any, guard: Any) -> Any:
    try:
        session = require_active()
    except Exception:
        raise LifecycleError("QUOTA_RESUME_SESSION_REJECTED") from None
    require(
        session.phase == "core"
        and session.guard is guard
        and session.approval.candidate == binding.candidate_commit
        and binding.scenario_id in session.scenarios
        and session.approval.equivalent is not None
        and binding.model == ("k3-256k" if session.approval.equivalent else "k3")
        and target.model == binding.model
    )
    return session


def _read(target: Any, control: Any, binding: Any, guard: Any) -> ResumeEvidence:
    try:
        return gather(target, control, binding, guard)
    except Exception:
        raise LifecycleError("QUOTA_RESUME_EVIDENCE_REJECTED") from None


@contextmanager
def eligible_quota5h(target: Any, control: Any, binding: Any, guard: Any) -> Iterator[QuotaResumeWitness]:
    typed(target, control, binding, guard)
    session = _session(target, binding, guard)
    evidence = _read(target, control, binding, guard)
    witness = object.__new__(QuotaResumeWitness)
    context = object()
    entry = _Entry(witness, target, target.repo, control, binding, guard, session, context, evidence)
    _LIVE[id(witness)] = entry
    token = _ACTIVE.set(context)
    try:
        yield witness
    finally:
        _LIVE.pop(id(witness), None)
        _ACTIVE.reset(token)


def check(witness: QuotaResumeWitness, *, target: Any, control: Any, binding: Any, guard: Any) -> EligibilitySummary:
    require(type(witness) is QuotaResumeWitness)
    entry = _LIVE.get(id(witness))
    require(entry is not None and entry.witness is witness)
    try:
        typed(target, control, binding, guard)
        require(
            entry.target is target
            and entry.repo is target.repo
            and entry.control is control
            and entry.binding is binding
            and entry.guard is guard
            and _ACTIVE.get() is entry.context
            and _session(target, binding, guard) is entry.session
        )
        current = _read(target, control, binding, guard)
        require(current == entry.evidence)
        require(_LIVE.get(id(witness)) is entry and _ACTIVE.get() is entry.context)
    except BaseException:
        _LIVE.pop(id(witness), None)
        raise
    return EligibilitySummary(
        current.sha256,
        current.run_id,
        current.epoch,
        current.turn,
        current.seq,
        current.reset_at,
        current.consumed_ns,
        current.has_text,
    )
