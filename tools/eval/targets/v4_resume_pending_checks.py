"""Fresh same-run pre/post-claim checks after the exact stop clear; no public authority bit."""

from __future__ import annotations

from dataclasses import asdict

from mingjing_core.repositories.postgres import fingerprint
from tools.eval.quota_resume_clear import _peek_handoff, _quiescent
from tools.eval.quota_resume_evidence import _attempts, _budget, _central, _journal, _private, require


def _read(handoff):
    hand = _peek_handoff(handoff)
    entry, receipt = hand.entry, hand.receipt
    target, control, binding, guard = entry.target, entry.control, entry.binding, entry.guard
    record, state = _private(target, control, binding, guard)
    run = target.repo.fetch_run(target.owner, entry.evidence.run_id)
    require(
        run["runtime"] == "v4"
        and run["status"] == "running"
        and run["retry_epoch"] == entry.evidence.epoch
        and run["cancel_requested_at"] is None
        and run["owner"] == run["owner_user_id"] == target.owner
        and run["subject"] == run["subject_id"] == state["runs"][-1]["subject"]
    )
    account, usage, batches = _central(guard, run["id"])
    require(account["stop_kind"] is None and account["stopped_at"] is None and account["resume_at"] is None)
    require(fingerprint(account["clear_authorization"]) == receipt.authorization_sha256)
    require(account["ledger_identity"] == hand.account["ledger_identity"])
    require(account["location_id"] == hand.account["location_id"])
    with guard.store.connect() as connection:
        _quiescent(connection, guard.store)
    steps, budget = _journal(target, run), _budget(target, state, binding, run)
    terminal, hashes = _attempts(target, binding, run, steps, usage, batches)
    require(terminal["attempt_id"] == entry.evidence.terminal_id)
    stop = {
        key: hand.account[key]
        for key in ("stop_kind", "stopped_at", "resume_at", "clear_authorization", "ledger_identity", "location_id")
    }
    value = dict(
        record=record,
        state_sha256=fingerprint(state),
        journal=steps,
        requests=hashes,
        stop=stop,
        usage=usage,
        batches=batches,
        budget=budget,
        policy=asdict(guard.policy),
    )
    require(fingerprint(value) == entry.evidence.sha256)
    binding.verify(guard)
    entry.session.approval.check(guard.clock.now())
    require(entry.session._receipt is None)
    return entry, run, state


def revalidate(handoff):
    first = _read(handoff)
    second = _read(handoff)
    require(fingerprint(first[1:]) == fingerprint(second[1:]))
    return second
