"""Narrow eval-only same-run continuation; ordinary runtime never imports evaluator tools."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from mingjing_core.agent.journal import Journal
from mingjing_core.application.agent_thread_scope import assert_thread
from mingjing_core.models.quota_attempt_observer import ModelAttemptUnconfirmed
from mingjing_core.models.quota_delegated_session import require_active
from mingjing_core.repositories.dependencies import lineage_key
from mingjing_core.repositories.postgres import fingerprint


def _require(value):
    if not value:
        raise ModelAttemptUnconfirmed()


@dataclass(repr=False)
class _Execution:
    repo: Any
    guard: Any
    session: Any
    meter: Any
    run: dict
    seq: int
    request_hash: str
    logical: dict
    terminals: tuple[tuple[str, str], ...]
    begun: bool = False
    appended: bool = False
    active: bool = True
    reads: dict = field(default_factory=dict)


class _ExecutionPermit:
    __slots__ = ()

    def __new__(cls):
        raise ModelAttemptUnconfirmed()

    def __reduce__(self):
        raise ModelAttemptUnconfirmed()


_LIVE: dict[int, tuple[_ExecutionPermit, _Execution]] = {}
_ACTIVE: ContextVar[_ExecutionPermit | None] = ContextVar("eval_quota_resume_execution", default=None)


def _scope(selected=None):
    permit = _ACTIVE.get()
    if permit is None:
        return None
    _require(type(permit) is _ExecutionPermit)
    registered = _LIVE.get(id(permit))
    _require(registered is not None and registered[0] is permit)
    value = registered[1]
    _require(value.active and require_active() is value.session and value.session.guard is value.guard)
    if selected is not None:
        step = selected.step
        _require(
            selected.repo is value.repo
            and selected.context.guard is value.guard
            and (step.owner, step.run_id, step.epoch, step.lease_token)
            == (value.run["owner"], value.run["id"], value.run["retry_epoch"], value.run["lease_token"])
        )
    return value


def _logical(repo, run, seq):
    return repo.get(run["owner"], "runtime_step", f"{run['id']}:e{run['retry_epoch']}:agent_model_attempts:{seq}")


@contextmanager
def resume_execution(handoff, repo, run):
    # Deliberately lazy and opt-in: this evaluation branch alone consumes the private same-stack handoff.
    from tools.eval.quota_resume_clear import _consume_handoff
    from tools.eval.quota_resume_evidence import _central

    entry, original_logical = _consume_handoff(handoff, repo, run)
    _require(_ACTIVE.get() is None and getattr(repo._local, "connection", None) is None)
    account, usage, batches = _central(entry.guard, run["id"])
    _require(account["stop_kind"] is None and fingerprint(usage) == entry.evidence.usage_sha256)
    _require(fingerprint(batches) == entry.evidence.batches_sha256)
    logical = _logical(repo, run, entry.evidence.seq)
    _require(fingerprint(logical) == fingerprint(original_logical))
    _require(logical["status"] == "active" and logical["subject_id"] == run["subject"])
    state = _Execution(
        repo,
        entry.guard,
        entry.session,
        entry.target.runtime.meter,
        dict(run),
        entry.evidence.seq,
        fingerprint(run["request"]),
        logical,
        tuple((row["attempt_id"], fingerprint(row)) for row in usage),
    )
    permit = object.__new__(_ExecutionPermit)
    _LIVE[id(permit)] = (permit, state)
    token = _ACTIVE.set(permit)
    try:
        yield
    finally:
        state.active = False
        state.reads.clear()
        _LIVE.pop(id(permit), None)
        _ACTIVE.reset(token)


def forbid_regeneration(repo, original):
    if _ACTIVE.get() is not None:
        _scope()
        raise ModelAttemptUnconfirmed()


def begin_pending(selected):
    state = _scope(selected)
    if state is None or selected.step.seq != state.seq:
        return False
    _require(not state.begun and fingerprint(_logical(state.repo, state.run, state.seq)) == fingerprint(state.logical))
    value = selected.load()
    _require(value["attempts"] and all(item.get("result_kind") == "quota_5h" for item in value["attempts"]))
    expected = dict(state.terminals)
    for item in value["attempts"]:
        row = selected.central(state.guard, None, item["attempt_id"])
        _require(item["state"] == "finished" and expected.get(item["attempt_id"]) == fingerprint(row))
        _require(row["status"] == "quota_5h" and row["finished_at"] is not None)
    state.begun = True
    return True


def prepare_pending(selected):
    state = _scope(selected)
    if state is not None and selected.step.seq == state.seq:
        _require(state.begun and not state.appended)
        _require(fingerprint(_logical(state.repo, state.run, state.seq)) == fingerprint(state.logical))
        state.appended = True


class _CompletedRead:
    __slots__ = ("state", "selected", "proof", "connection", "active")

    def __new__(cls):
        raise ModelAttemptUnconfirmed()

    def __reduce__(self):
        raise ModelAttemptUnconfirmed()

    def authority(self, selected):
        state = _scope(selected)
        _require(self.active and state is self.state and self.selected is selected)
        _require(state.reads.get(id(self)) is self and selected.step.seq < state.seq)
        connection = getattr(state.repo._local, "connection", None)
        _require(connection is not None and (self.connection is None or self.connection is connection))
        self.connection = connection
        selected.context.check()
        run = Journal(state.repo, selected.step.owner)._leased(
            connection, vars(selected.step) | {"id": selected.step.run_id, "retry_epoch": selected.step.epoch}
        )
        _current(self.proof, state, run, selected)


def _current(proof, state, run, selected):
    _require(
        run["runtime"] == "v4"
        and run["cancel_requested_at"] is None
        and run["subject"] == proof.subject
        and fingerprint(run["request"]) == state.request_hash
    )
    state.repo.assert_scope(run["owner"], run["subject"])
    assert_thread(state.repo, run)
    rows = []
    for key, revision in proof.current_versions:
        kind, ident = lineage_key(key).split(":", 1)
        row = state.repo.get(run["owner"], kind, ident, include_deleted=True)
        _require(type(row["revision"]) is int and row["revision"] == revision)
        _require(row["owner"] == run["owner"] and row["subject_id"] == run["subject"])
        _require(row["status"] not in {"deleted", "stopped", "superseded"})
        _require(not state.repo.is_revoked(run["owner"], kind, ident))
        rows.append(row)
    _require(fingerprint(rows) == proof.current_entities_sha256)
    _require(fingerprint(state.repo.revocations(run["owner"])) == proof.revocations_sha256)
    source = state.repo.get(run["owner"], "message", run["request"]["source_message_id"])
    _require(source["status"] == "active" and source.get("role") == "user")
    _require(
        source["content"] == run["request"]["message"] and proof.request_sha256 == selected.snapshot["output_sha256"]
    )
    actual = state.repo.get(run["owner"], "runtime_step", selected.snapshot["id"])
    _require(fingerprint(actual) == fingerprint(selected.snapshot))


def completed_authority(read, selected):
    _require(type(read) is _CompletedRead)
    read.authority(selected)


def completed_terminal(read, selected, row):
    completed_authority(read, selected)
    _require(dict(read.state.terminals).get(row["attempt_id"]) == fingerprint(row))


@contextmanager
def completed_read(selected):
    state = _scope(selected)
    if state is None or selected.step.seq >= state.seq:
        yield None
        return
    from mingjing_core.application.agent_model_calls import RequestLedger
    from mingjing_core.application.agent_model_history_evidence import completed_model_history

    _require(getattr(state.repo._local, "connection", None) is None)
    proof = completed_model_history(
        RequestLedger(state.repo, state.meter, offline=False),
        selected.step.owner,
        selected.step.run_id,
        selected.step.epoch,
        selected.step.seq,
    )
    read = object.__new__(_CompletedRead)
    read.state, read.selected, read.proof, read.connection, read.active = state, selected, proof, None, True
    state.reads[id(read)] = read
    try:
        yield read
    finally:
        read.active = False
        state.reads.pop(id(read), None)
