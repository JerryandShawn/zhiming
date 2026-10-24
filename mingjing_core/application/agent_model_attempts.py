"""Opt-in core-evaluation step anchors; private PG owns dispatch evidence."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from psycopg import sql

from mingjing_core.agent.journal import Journal, JournalStep
from mingjing_core.application.agent_thread_scope import assert_thread
from mingjing_core.domain.contracts import ScopeError
from mingjing_core.models.errors import ModelCancelled, ModelUnavailable
from mingjing_core.models.quota_attempt_observer import (
    ModelAttemptUnconfirmed,
    observe_attempts,
)
from mingjing_core.models.quota_delegated_session import require_active
from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.models.quota_r16 import approved_core_model
from mingjing_core.models.quota_runtime import current_scope
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint

SCHEMA = "agent-model-attempts-v1"


@contextmanager
def confirmed(*, only_core: bool = False) -> Iterator[None]:
    if only_core and not observing_core():
        yield
        return
    try:
        yield
    except ModelAttemptUnconfirmed:
        raise
    except ModelUnavailable as error:
        if error.global_stop or isinstance(error, ModelCancelled):
            raise
        raise ModelAttemptUnconfirmed() from None
    except Exception:
        raise ModelAttemptUnconfirmed() from None


@dataclass(frozen=True)
class CoreObservation:
    repo: PostgresRepository
    owner: str
    guard: QuotaGuard
    binding: dict[str, Any]
    verify: Callable[[], Mapping[str, Any]]

    def check(self) -> None:
        session, scope = require_active(), current_scope()
        wanted = approved_core_model(session.approval, session.guard.clock.now())
        if (
            session.phase != "core"
            or session.guard is not self.guard
            or scope.lane != "eval"
            or scope.scenario_id != self.binding["scenario_id"]
            or scope.scenario_id not in session.scenarios
            or session.approval.candidate != self.binding["candidate_commit"]
            or self.binding["model"] != wanted
            or dict(self.verify()) != self.binding
        ):
            raise ModelAttemptUnconfirmed()


_CORE: ContextVar[CoreObservation | None] = ContextVar(
    "core_eval_model_observation", default=None
)


def observing_core() -> bool:
    return _CORE.get() is not None


@contextmanager
def core_observation(
    repo: PostgresRepository,
    owner: str,
    guard: QuotaGuard,
    binding: dict[str, Any],
    verify: Callable[[], Mapping[str, Any]],
) -> Iterator[None]:
    with confirmed():
        selected = CoreObservation(repo, owner, guard, dict(binding), verify)
        selected.check()
    token = _CORE.set(selected)
    try:
        yield
    finally:
        _CORE.reset(token)


def _ident(step: JournalStep) -> str:
    return f"{step.run_id}:e{step.epoch}:agent_model_attempts:{step.seq}"


class StepAttempts:
    def __init__(
        self, context: CoreObservation, step: JournalStep, snapshot: dict[str, Any]
    ) -> None:
        self.context, self.repo, self.step = context, context.repo, step
        self.snapshot, self.revision, self.active_id = snapshot, 0, None
        self.admitted_revision: int | None = None
        call = snapshot["output"]
        self.anchor = {
            "binding": context.binding,
            "owner": step.owner,
            "subject": step.subject,
            "run_id": step.run_id,
            "epoch": step.epoch,
            "seq": step.seq,
            "input_fp": step.input_fp,
            "operation_id": step.operation_id,
            "request_sha256": snapshot["output_sha256"],
            "role": call["role"],
            "name": step.name,
        }

    def authority(self) -> None:
        self.context.check()
        with self.repo.transaction(self.step.owner) as connection:
            run = Journal(self.repo, self.step.owner)._leased(
                connection,
                vars(self.step)
                | {"id": self.step.run_id, "retry_epoch": self.step.epoch},
            )
            assert_thread(self.repo, run)
            source_id = run["request"]["source_message_id"]
            source = self.repo.get(self.step.owner, "message", source_id)
            versions = self.snapshot["output"]["versions"]
            if (
                source["status"] != "active"
                or source.get("role") != "user"
                or source.get("content") != run["request"].get("message")
                or self.repo.is_revoked(self.step.owner, "message", source_id)
                or not self.repo.verify_versions(self.step.owner, versions)
            ):
                raise ModelAttemptUnconfirmed()

    def load(self) -> dict[str, Any]:
        row = self.repo.get(
            self.step.owner, "runtime_step", _ident(self.step), include_deleted=True
        )
        value = row.get("value")
        if (
            row["status"] != "active"
            or row.get("schema") != SCHEMA
            or row.get("value_sha256") != fingerprint(value)
            or not isinstance(value, dict)
            or any(value.get(key) != item for key, item in self.anchor.items())
            or not isinstance(value.get("attempts"), list)
        ):
            raise ModelAttemptUnconfirmed()
        self.revision = row["revision"]
        return value

    def save(self, value: dict[str, Any], operation: str) -> None:
        self.authority()
        versions = self.snapshot["output"]["versions"]
        self.repo.put(
            self.step.owner,
            "runtime_step",
            _ident(self.step),
            {
                "schema": SCHEMA,
                "stage": "agent_model_attempts",
                "run_id": self.step.run_id,
                "epoch": self.step.epoch,
                "value": value,
                "value_sha256": fingerprint(value),
                "source_ids": [
                    key[8:] for key in versions if key.startswith("message:")
                ],
                "fact_ids": [key[5:] for key in versions if key.startswith("fact:")],
            },
            subject=self.step.subject,
            expected_revision=self.revision,
            operation_id=self.step.operation_id + ":attempts:" + operation,
        )
        self.revision += 1

    def begin(self) -> None:
        self.authority()
        from mingjing_core.application.agent_model_resume import begin_pending

        if begin_pending(self):
            return
        try:
            self.repo.get(
                self.step.owner, "runtime_step", _ident(self.step), include_deleted=True
            )
        except ScopeError:
            self.save(dict(self.anchor, attempts=[]), "logical_intent")
            return
        # Existing unfinished dispatch is never evidence that no POST happened.
        raise ModelAttemptUnconfirmed()

    def _scope(
        self, guard: QuotaGuard, scope: Any, role: str, provider: str, model: str
    ) -> dict[str, Any]:
        self.authority()
        if (
            guard is not self.context.guard
            or (scope.run_id, scope.lane, scope.scenario_id)
            != (self.step.run_id, "eval", self.context.binding["scenario_id"])
            or (role, provider, model)
            != (self.anchor["role"], "kimi_code", self.context.binding["model"])
            or not scope.batch_id
            or not scope.authorization_id
        ):
            raise ModelAttemptUnconfirmed()
        return {
            "run_id": scope.run_id,
            "lane": scope.lane,
            "scenario_id": scope.scenario_id,
            "batch_id": scope.batch_id,
            "authorization_sha256": fingerprint(scope.authorization_id),
            "role": role,
            "provider": provider,
            "model": model,
        }

    def prepare(
        self,
        guard: QuotaGuard,
        scope: Any,
        attempt_id: str,
        role: str,
        provider: str,
        model: str,
    ) -> None:
        with confirmed():
            admitted = self._scope(guard, scope, role, provider, model)
            from mingjing_core.application.agent_model_resume import prepare_pending

            prepare_pending(self)
            value = self.load()
            if any(
                item["attempt_id"] == attempt_id or item["state"] != "finished"
                for item in value["attempts"]
            ):
                raise ModelAttemptUnconfirmed()
            value["attempts"].append(
                dict(admitted, attempt_id=attempt_id, state="intent")
            )
            self.save(value, attempt_id + ":intent")
            self.active_id = attempt_id

    def central(
        self, guard: QuotaGuard, scope: Any, attempt_id: str, *, read=None
    ) -> dict[str, Any]:
        value = self.load()
        entry = next(
            item for item in value["attempts"] if item["attempt_id"] == attempt_id
        )
        if scope is not None:
            admitted = self._scope(
                guard, scope, entry["role"], entry["provider"], entry["model"]
            )
            if any(entry[key] != item for key, item in admitted.items()):
                raise ModelAttemptUnconfirmed()
        elif read is not None:
            from mingjing_core.application.agent_model_resume import completed_authority

            completed_authority(read, self)
        else:
            self.authority()
        with guard.store.connect() as connection:
            account = guard.store.verify(connection)
            row = connection.execute(
                sql.SQL(
                    "SELECT * FROM {} WHERE account_id=%s AND attempt_id=%s"
                ).format(guard.store.table("core_model_usage")),
                (guard.store.account_id, attempt_id),
            ).fetchone()
            batch = connection.execute(
                sql.SQL(
                    "SELECT authorization_id FROM {} WHERE account_id=%s AND batch_id=%s"
                ).format(guard.store.table("core_model_batches")),
                (guard.store.account_id, entry["batch_id"]),
            ).fetchone()
        if (
            row is None
            or batch is None
            or account["location_id"] != self.context.binding["central_location"]
            or guard.store.identity != self.context.binding["central_identity"]
            or guard.store.account_id != self.context.binding["central_account"]
            or fingerprint(batch["authorization_id"]) != entry["authorization_sha256"]
            or any(
                row[key] != entry[key]
                for key in (
                    "run_id",
                    "lane",
                    "scenario_id",
                    "batch_id",
                    "role",
                    "provider",
                    "model",
                )
            )
        ):
            raise ModelAttemptUnconfirmed()
        if read is not None:
            from mingjing_core.application.agent_model_resume import completed_terminal

            completed_terminal(read, self, row)
        return row

    def admitted(self, guard: QuotaGuard, scope: Any, attempt_id: str) -> None:
        with confirmed():
            row = self.central(guard, scope, attempt_id)
            if (
                row["status"] != "reserved"
                or row["finished_at"] is not None
                or self.active_id != attempt_id
            ):
                raise ModelAttemptUnconfirmed()
            value = self.load()
            value["attempts"][-1]["state"] = "admitted"
            self.save(value, attempt_id + ":admitted")
            self.admitted_revision = self.revision

    def before_send(self) -> None:
        with confirmed():
            self.authority()
            value = self.load()
            if (
                not value["attempts"]
                or value["attempts"][-1]["attempt_id"] != self.active_id
                or value["attempts"][-1]["state"] != "admitted"
                or self.revision != self.admitted_revision
            ):
                raise ModelAttemptUnconfirmed()
            row = self.central(self.context.guard, None, self.active_id)
            if row["status"] != "reserved" or row["finished_at"] is not None:
                raise ModelAttemptUnconfirmed()

    def finished(self, guard: QuotaGuard, scope: Any, attempt_id: str) -> None:
        with confirmed():
            row = self.central(guard, scope, attempt_id)
            if row["finished_at"] is None or row["status"] in {"reserved", "unknown"}:
                raise ModelAttemptUnconfirmed()
            value = self.load()
            entry = next(
                item for item in value["attempts"] if item["attempt_id"] == attempt_id
            )
            if entry["state"] != "admitted":
                raise ModelAttemptUnconfirmed()
            entry.update(
                state="finished",
                terminal_sha256=fingerprint(row),
                result_kind=row["status"],
            )
            self.save(value, attempt_id + ":finished")

    def verify_completed(self) -> None:
        from mingjing_core.application.agent_model_resume import (
            completed_authority,
            completed_read,
        )

        with (
            completed_read(self) as read,
            self.repo.transaction(self.step.owner) as connection,
        ):
            if read is None:
                self.authority()
            else:
                completed_authority(read, self)
            journal = Journal(self.repo, self.step.owner)
            run = journal._leased(
                connection,
                vars(self.step)
                | {"id": self.step.run_id, "retry_epoch": self.step.epoch},
            )
            native = journal._read(
                connection, self.step.run_id, self.step.epoch, self.step.seq
            )
            if native is None:
                raise ModelAttemptUnconfirmed()
            journal._check(native, self.step.kind, self.step.name, self.step.input_fp)
            actual = journal._step(native, run)
            keys = (
                "owner",
                "run_id",
                "epoch",
                "seq",
                "kind",
                "name",
                "operation_id",
                "input_fp",
                "status",
                "output",
                "usage",
            )
            if fingerprint({key: getattr(actual, key) for key in keys}) != fingerprint(
                {key: getattr(self.step, key) for key in keys}
            ):
                raise ModelAttemptUnconfirmed()
            value = self.load()
            if (
                not self.step.completed
                or not value["attempts"]
                or value["attempts"][-1].get("result_kind") != "ok"
            ):
                raise ModelAttemptUnconfirmed()
            for entry in value["attempts"]:
                row = self.central(
                    self.context.guard, None, entry["attempt_id"], read=read
                )
                if entry["state"] != "finished" or fingerprint(row) != entry.get(
                    "terminal_sha256"
                ):
                    raise ModelAttemptUnconfirmed()


def _selected(
    repo: PostgresRepository, step: JournalStep, offline: bool
) -> StepAttempts | None:
    context = _CORE.get()
    if context is None:
        return None
    if offline or context.repo is not repo or step.owner != context.owner:
        raise ModelAttemptUnconfirmed()
    snapshot = repo.get(
        step.owner,
        "runtime_step",
        f"{step.run_id}:e{step.epoch}:agent_model_request:{step.seq}",
    )
    if (
        snapshot.get("schema") != "agent-model-request-v1"
        or (
            snapshot.get("run_id"),
            snapshot.get("epoch"),
            snapshot.get("seq"),
            snapshot.get("input_fp"),
        )
        != (step.run_id, step.epoch, step.seq, step.input_fp)
        or snapshot.get("output_sha256") != fingerprint(snapshot.get("output"))
        or snapshot.get("output", {}).get("name") != step.name
        or snapshot.get("output", {}).get("role")
        != ("critic" if step.name == "critic" else "primary")
    ):
        raise ModelAttemptUnconfirmed()
    return StepAttempts(context, step, snapshot)


@contextmanager
def physical_step(
    repo: PostgresRepository, step: JournalStep, *, offline: bool
) -> Iterator[None]:
    with confirmed():
        selected = _selected(repo, step, offline)
        if selected is not None:
            selected.begin()
    if selected is None:
        yield
    else:
        with observe_attempts(selected):
            yield


def verify_completed(
    repo: PostgresRepository, step: JournalStep, *, offline: bool
) -> None:
    with confirmed():
        selected = _selected(repo, step, offline)
        if selected is not None:
            selected.verify_completed()
