"""Explicit same-run quota continuation through native leases, Journal and cumulative budgets."""

from __future__ import annotations

from dataclasses import asdict

from psycopg import sql

from mingjing_core.application.agent_model_attempts import core_observation
from mingjing_core.application.agent_model_resume import resume_execution
from mingjing_core.models.errors import ModelUnavailable
from mingjing_core.models.quota_runtime import call_scope
from mingjing_core.repositories.postgres import fingerprint
from tools.eval.lifecycle_identity import LifecycleError
from tools.eval.quota import ProviderStopped
from tools.eval.quota_resume_clear import _bind_claim, _resume_after_clear
from tools.eval.quota_resume_evidence import _central, require

from .base import TurnResult
from .v4_completed_turn import native_answer
from .v4_execution_budget_store import BudgetStore
from .v4_resume_pending_checks import revalidate


def claim_pending(handoff):
    """Called only after confirmed clear COMMIT, before taking the fresh owner transaction."""
    entry, original, state = revalidate(handoff)
    repo, owner = entry.repo, entry.target.owner
    require(getattr(repo._local, "connection", None) is None)
    try:
        with repo.transaction(owner) as connection:
            _, before, _ = revalidate(handoff)
            expired = connection.execute(
                sql.SQL("SELECT lease_until<=now() AS expired FROM {} WHERE owner=%s AND id=%s FOR UPDATE").format(
                    repo.table("core_runs")
                ),
                (owner, original["id"]),
            ).fetchone()
            require(expired is not None and expired["expired"] is True)
            require(fingerprint(before) == fingerprint(original))
            claimed = repo.claim_run(owner, original["id"])
            _, after, _ = revalidate(handoff)
            require(
                claimed == after
                and claimed["lease_token"] != original["lease_token"]
                and claimed["request"] == original["request"]
                and claimed["retry_epoch"] == original["retry_epoch"]
                and claimed["deadline_at"] == original["deadline_at"]
                and claimed["state_version"] == original["state_version"]
                and claimed["usage"] == original["usage"]
            )
    except Exception:
        raise LifecycleError("QUOTA_RESUME_CLAIM_FAILED_OR_UNKNOWN") from None
    _bind_claim(handoff, claimed)
    return entry, claimed, state


def _counts(entry):
    _, rows, _ = _central(entry.guard, entry.evidence.run_id)
    require(len({row["attempt_id"] for row in rows}) == len(rows))
    require(all(row["finished_at"] is not None and row["status"] not in {"reserved", "unknown"} for row in rows))
    return len(rows)


def _result(entry, before):
    target = entry.target
    native = native_answer(target.repo, target.owner, entry.evidence.run_id)
    actual = target.repo.fetch_run(target.owner, entry.evidence.run_id)
    require(actual["retry_epoch"] == entry.evidence.epoch)
    count = _counts(entry)
    budget = BudgetStore(target.repo, target.owner, entry.binding, target.lifecycle_session).read_closed(actual["id"])
    require(budget is not None)
    return TurnResult(
        **{key: native[key] for key in ("text", "receipts", "tools_called", "events")},
        model_calls=count,
        elapsed_seconds=budget["consumed_ns"] / 10**9,
        usage=actual.get("usage", {}).get("reported_tokens", {}),
        metadata=dict(
            runtime="v4",
            run_id=actual["id"],
            run_status="succeeded",
            offline=False,
            physical_model_requests=count,
            segment_model_requests=count - before,
            external_provider_requests=target.port.external_calls,
            resumed_same_run=True,
            retry_epoch=actual["retry_epoch"],
        ),
    )


def _quota_checkpoint(entry, error):
    if error.reason != "quota_5h" or entry.target._budget_unknown:
        return
    entry.session.close()
    _counts(entry)
    entry.target.checkpoint(entry.control, entry.binding, entry.guard, turn=entry.evidence.turn)


def _execute(handoff):
    entry, run, _ = claim_pending(handoff)
    target, guard, binding = entry.target, entry.guard, entry.binding
    before = _counts(entry)
    try:
        with (
            call_scope(entry.session.scope(binding.scenario_id)),
            core_observation(target.repo, target.owner, guard, asdict(binding), lambda: binding.verify(guard)),
            resume_execution(handoff, target.repo, run),
            target._execution_scope(binding, guard, run),
        ):
            target.runtime.execute(target.service, target.owner, run["id"], run["lease_token"])
    except ModelUnavailable as error:
        stopped = ProviderStopped(
            error.kind,
            "target",
            provider_http_status=error.provider_http_status,
            resume_at=error.safe_diagnostic().get("resume_at"),
        )
        _quota_checkpoint(entry, stopped)
        raise stopped from None
    except ProviderStopped as error:
        _quota_checkpoint(entry, error)
        raise
    entry.session.close()
    result = _result(entry, before)
    target.checkpoint(entry.control, binding, guard, turn=entry.evidence.turn, completed=result)
    return result


def resume_pending(target, witness, *, control, binding, guard):
    require(target.repo is not None and target._attached and target._budget_scope is None)
    require(getattr(target.repo._local, "connection", None) is None)
    return _resume_after_clear(
        witness, target=target, control=control, binding=binding, guard=guard, continuation=_execute
    )
