"""Bounded cycle policy and short PG lease/cancellation checks; no model work in transactions."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal

from psycopg import sql

from mingjing_core.application.agent_commit_versions import reconcile_versions
from mingjing_core.domain.contracts import CoreError, EvidenceError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import Clock, get_clock


class LoopStopped(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__("本轮循环已停止")


@dataclass(frozen=True)
class LoopPolicy:
    depth: Literal["standard", "deep"] = "standard"
    max_iterations: int | None = None
    max_seconds: int | None = None
    max_tools: int | None = None
    repeat_limit: int = 3
    renew_seconds: int = 20
    lease_seconds: int = 150
    only_tool: str | None = None
    text_only: bool = False

    def __post_init__(self) -> None:
        if self.depth not in {"standard", "deep"}:
            raise EvidenceError("循环深度无效")
        for value, maximum in (
            (self.iterations, 60 if self.deep else 40),
            (self.seconds, 1200 if self.deep else 480),
            (self.tools_per_step, 10 if self.deep else 6),
            (self.repeat_limit, 3),
            (self.renew_seconds, 20),
            (self.lease_seconds, 150),
        ):
            if type(value) is not int or not 1 <= value <= maximum:
                raise EvidenceError("循环策略不能扩大已批准上限")
        if self.only_tool is not None and (not isinstance(self.only_tool, str) or not self.only_tool or self.text_only):
            raise EvidenceError("循环工具选择无效")

    @property
    def deep(self) -> bool:
        return self.depth == "deep"

    @property
    def iterations(self) -> int:
        return self.max_iterations if self.max_iterations is not None else 60 if self.deep else 40

    @property
    def seconds(self) -> int:
        return self.max_seconds if self.max_seconds is not None else 1200 if self.deep else 480

    @property
    def tools_per_step(self) -> int:
        return self.max_tools if self.max_tools is not None else 10 if self.deep else 6


class RunControl:
    """Injected ports must cooperate with cancel_event during blocked transport reads."""

    def __init__(
        self,
        repo: PostgresRepository,
        run: Mapping[str, Any],
        policy: LoopPolicy,
        *,
        clock: Clock | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        cancel_event: threading.Event | None = None,
    ) -> None:
        self.repo, self.run, self.policy = repo, dict(run), policy
        self.clock, self.monotonic = clock or get_clock(), monotonic
        self.cancel_event = cancel_event or threading.Event()
        self.started, self.renewed = monotonic(), monotonic()
        self.lock, self.failure = threading.RLock(), None

    def poll(self) -> None:
        with self.lock:
            if self.failure is not None:
                raise self.failure
            if self.cancel_event.is_set():
                raise LoopStopped("cancelled")
            if self.monotonic() - self.started >= self.policy.seconds:
                raise LoopStopped("wall_time_limit")
            try:
                self._poll_database()
            except CoreError:
                raise LoopStopped("lease_or_source_invalid") from None

    def _poll_database(self) -> None:
        run, owner = self.run, self.run["owner"]
        with self.repo.transaction(owner) as connection:
            row = self.repo._leased(connection, owner, run["id"], run["lease_token"])
            if row["runtime"] != "v4" or row["retry_epoch"] != run["retry_epoch"] or row["subject"] != run["subject"]:
                raise LoopStopped("runtime_identity_changed")
            self.repo.assert_scope(owner, row["subject"])
            if row["cancel_requested_at"] is not None:
                raise LoopStopped("cancelled")
            if row["deadline_at"] is None:
                deadline = self.clock.now() + timedelta(seconds=self.policy.seconds)
                connection.execute(
                    sql.SQL("UPDATE {} SET deadline_at=%s WHERE owner=%s AND id=%s").format(
                        self.repo.table("core_runs")
                    ),
                    (deadline, owner, run["id"]),
                )
            elif row["deadline_at"] <= self.clock.now():
                raise LoopStopped("wall_time_limit")
            source_id = row["request"].get("source_message_id")
            source = self.repo.get(owner, "message", source_id)
            if source["status"] != "active" or source["subject_id"] != row["subject"] or source.get("role") != "user":
                raise LoopStopped("source_revoked")
            if source.get("content") != row["request"].get("message"):
                raise LoopStopped("source_changed")
            if any(
                item["kind"] == "message"
                and item["entity_id"] == source_id
                or item["kind"] == "source_span"
                and item["metadata"].get("message_id") == source_id
                for item in self.repo.revocations(owner)
            ):
                raise LoopStopped("source_revoked")
            versions = reconcile_versions(self.repo, row, row["state_version"])
            if not self.repo.verify_versions(owner, versions):
                raise LoopStopped("dependencies_changed")
            if versions != row["state_version"]:
                self.repo.set_run_dependencies(owner, run["id"], versions, run["lease_token"])
            if self.monotonic() - self.renewed >= self.policy.renew_seconds:
                self.repo.renew_run(owner, run["id"], run["lease_token"], self.policy.lease_seconds)
                self.renewed = self.monotonic()

    @contextmanager
    def monitor(self) -> Iterator[None]:
        stop = threading.Event()

        def observe() -> None:
            while not stop.wait(0.25):
                try:
                    self.poll()
                except Exception as error:
                    with self.lock:
                        self.failure = error if isinstance(error, LoopStopped) else LoopStopped("control_failure")
                        self.cancel_event.set()
                    return

        self.poll()
        thread = threading.Thread(target=observe, name="agent-loop-control", daemon=True)
        thread.start()
        try:
            yield
            self.poll()
        finally:
            stop.set()
            thread.join(timeout=1)
