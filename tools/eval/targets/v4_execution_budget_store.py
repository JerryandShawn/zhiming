"""Private PG execution segments; a closed duration is never inferred from clocks."""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, replace
from typing import Any

from psycopg import sql

from mingjing_core.agent.loop_policy import LoopPolicy
from mingjing_core.application.agent_regeneration import lease_hash
from mingjing_core.application.runtime_limits import deadline, validate_pin
from mingjing_core.domain.contracts import ScopeError
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint
from tools.eval.lifecycle_identity import LifecycleBinding, LifecycleError

from .v4_lifecycle_state import run_identity

STAGE = "eval_execution_budget"
FORMAT = "eval-execution-budget-v1"
SOURCE_KEYS = ("id", "epoch", "subject", "thread", "request_sha256", "sources")
KEYS = {"format", "binding", "session", "location", "source", "pin", "deadline", "limit_ns", "segments"}


def _segments(value: Any) -> int:
    if not isinstance(value, list) or not value:
        raise LifecycleError("执行预算缺少已知段")
    total, seen = 0, set()
    for segment in value:
        if (
            not isinstance(segment, dict)
            or set(segment) != {"id", "phase", "elapsed_ns", "lease", "has_text"}
            or re.fullmatch(r"[0-9a-f]{32}", segment.get("id", "")) is None
            or segment["id"] in seen
            or re.fullmatch(r"[0-9a-f]{64}", segment.get("lease", "")) is None
            or type(segment["has_text"]) is not bool
            or segment["phase"] != "closed"
            or type(segment["elapsed_ns"]) is not int
            or not 0 <= segment["elapsed_ns"] <= 2**63 - 1
        ):
            raise LifecycleError("执行预算含未闭合或未知段")
        seen.add(segment["id"])
        total += segment["elapsed_ns"]
    return total


class BudgetStore:
    def __init__(self, repo: PostgresRepository, owner: str, binding: LifecycleBinding, session: str) -> None:
        if re.fullmatch(r"eval_v4_[0-9a-f]{32}", repo.schema) is None:
            raise LifecycleError("执行预算只允许原本机场景")
        if re.fullmatch(r"eval-[0-9a-f]{32}", session or "") is None:
            raise LifecycleError("执行预算缺少原生命周期身份")
        self.repo, self.owner, self.binding, self.session = repo, owner, binding, session
        self.entry: dict[str, Any] | None = None

    @staticmethod
    def ident(run_id: str, epoch: int) -> str:
        return f"eval-budget:{run_id}:e{epoch}"

    def _actual(self, connection: Any, run_id: str, *, queued_read_only: bool = False) -> dict[str, Any]:
        row = connection.execute(
            sql.SQL("SELECT * FROM {} WHERE owner=%s AND id=%s FOR UPDATE").format(self.repo.table("core_runs")),
            (self.owner, run_id),
        ).fetchone()
        if row is None:
            raise LifecycleError("执行预算缺少原生运行")
        current = self.repo._run(row)
        allowed = {"queued", "running", "succeeded"} if queued_read_only else {"running", "succeeded"}
        if current["status"] not in allowed or current["cancel_requested_at"] is not None:
            raise LifecycleError("执行预算运行已终止")
        return current

    def _authority(self, connection: Any, current: dict[str, Any]) -> dict[str, Any]:
        pin = current.get("usage", {}).get("agent_runtime", {}).get("limit_epochs", {}).get(str(current["retry_epoch"]))
        config = validate_pin(pin, current, current["retry_epoch"])
        if pin["origin"] != "new_epoch" or current["deadline_at"] != deadline(pin):
            raise LifecycleError("执行预算不能采用遗留或改变的原限制")
        native = run_identity(self.repo, self.owner, current["id"], current=current["status"] == "running")
        location = connection.execute(
            "SELECT current_database() AS db,inet_server_addr()::text AS host,inet_server_port() AS port"
        ).fetchone()
        return {
            "format": FORMAT,
            "binding": asdict(self.binding),
            "session": self.session,
            "location": fingerprint(dict(location, schema=self.repo.schema)),
            "source": {key: native[key] for key in SOURCE_KEYS},
            "pin": pin["pin_sha256"],
            "deadline": pin["deadline_at"],
            "limit_ns": config.policy(current["lane"], current["request"].get("depth", "standard")).seconds * 10**9,
        }

    def _record(self, current: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        try:
            row = self.repo.get(
                self.owner, "runtime_step", self.ident(current["id"], current["retry_epoch"]), include_deleted=True
            )
        except ScopeError:
            return None, None
        budget = row.get("budget")
        if (
            row["status"] != "active"
            or row.get("stage") != STAGE
            or row.get("run_id") != current["id"]
            or row.get("epoch") != current["retry_epoch"]
            or not isinstance(budget, dict)
            or set(budget) != KEYS
            or not isinstance(budget["segments"], list)
            or not budget["segments"]
            or row.get("budget_sha256") != fingerprint(budget)
        ):
            raise LifecycleError("执行预算记录改变或已经擦除")
        return row, budget

    def _write(self, current: dict[str, Any], row: dict | None, budget: dict) -> dict[str, Any]:
        return self.repo.put(
            self.owner,
            "runtime_step",
            self.ident(current["id"], current["retry_epoch"]),
            {
                "stage": STAGE,
                "run_id": current["id"],
                "epoch": current["retry_epoch"],
                "source_ids": [source["id"] for source in budget["source"]["sources"]],
                "budget": budget,
                "budget_sha256": fingerprint(budget),
            },
            subject=current["subject"],
            expected_revision=row["revision"] if row else 0,
            operation_id="eval-budget:" + fingerprint(budget),
        )

    def open(self, run: dict[str, Any], policy: LoopPolicy) -> tuple[int, bool]:
        if self.entry is not None:
            raise LifecycleError("执行段不能重复打开")
        with self.repo.transaction(self.owner) as connection:
            current = self.repo._run(self.repo._leased(connection, self.owner, run["id"], run["lease_token"]))
            if current["retry_epoch"] != run["retry_epoch"] or current["subject"] != run["subject"]:
                raise LifecycleError("执行预算不属于原批次")
            authority = self._authority(connection, current)
            pin = current["usage"]["agent_runtime"]["limit_epochs"][str(current["retry_epoch"])]
            expected = validate_pin(pin, current, current["retry_epoch"]).policy(
                current["lane"], current["request"].get("depth", "standard")
            )
            if replace(policy, text_only=False) != expected:
                raise LifecycleError("执行控制器与原安全限额不符")
            executor = lease_hash(run["lease_token"])
            if current["usage"].get("agent_runtime", {}).get("executor_lease_sha256") != executor:
                raise LifecycleError("执行预算缺少原执行者凭据")
            row, old = self._record(current)
            if old is None:
                exists = connection.execute(
                    sql.SQL("SELECT 1 FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s LIMIT 1").format(
                        self.repo.table("core_run_steps")
                    ),
                    (self.owner, run["id"], run["retry_epoch"]),
                ).fetchone()
                if exists:
                    raise LifecycleError("已有Journal却缺少执行预算，不能猜零")
                segments, consumed = [], 0
            else:
                if {key: value for key, value in old.items() if key != "segments"} != authority:
                    raise LifecycleError("执行预算原身份或限制改变")
                segments, consumed = list(old["segments"]), _segments(old["segments"])
            if consumed >= authority["limit_ns"]:
                raise LifecycleError("累计执行预算已耗尽")
            nonce = uuid.uuid4().hex
            has_text = any(segment["has_text"] for segment in segments)
            segments.append(dict(id=nonce, phase="open", elapsed_ns=None, lease=executor, has_text=has_text))
            saved = self._write(current, row, dict(authority, segments=segments))
            self.entry = dict(run=run, authority=authority, nonce=nonce, revision=saved["revision"], executor=executor)
        return consumed, has_text

    def close(self, elapsed_ns: int, has_text: bool) -> dict[str, Any]:
        entry = self.entry
        if entry is None or type(elapsed_ns) is not int or not 0 <= elapsed_ns <= 2**63 - 1:
            raise LifecycleError("执行段没有可信结束测量")
        with self.repo.transaction(self.owner) as connection:
            current = self._actual(connection, entry["run"]["id"])
            authority = self._authority(connection, current)
            if authority != entry["authority"]:
                raise LifecycleError("关闭执行段时原身份已经改变")
            if current["usage"].get("agent_runtime", {}).get("executor_lease_sha256") != entry["executor"]:
                raise LifecycleError("关闭执行段时执行者改变")
            if current["status"] == "running":
                self.repo._leased(connection, self.owner, current["id"], entry["run"]["lease_token"])
            elif current["lease_token"] is not None:
                raise LifecycleError("成功运行没有正常释放租约")
            row, budget = self._record(current)
            if row is None or row["revision"] != entry["revision"]:
                raise LifecycleError("执行段被并行改变")
            if {key: value for key, value in budget.items() if key != "segments"} != entry["authority"]:
                raise LifecycleError("执行段原始锚点被改变")
            segments = list(budget["segments"])
            last = segments[-1]
            if (
                not isinstance(last, dict)
                or set(last) != {"id", "phase", "elapsed_ns", "lease", "has_text"}
                or last.get("id") != entry["nonce"]
                or last.get("phase") != "open"
                or last.get("lease") != entry["executor"]
                or last.get("elapsed_ns") is not None
                or type(last.get("has_text")) is not bool
            ):
                raise LifecycleError("不是本次打开的执行段")
            if segments[:-1]:
                _segments(segments[:-1])
            segments[-1] = dict(
                last, phase="closed", elapsed_ns=elapsed_ns, has_text=bool(has_text or last["has_text"])
            )
            updated = dict(budget, segments=segments)
            _segments(segments)
            saved = self._write(current, row, updated)
            self.entry = None
            return self._summary(saved, updated)

    @staticmethod
    def _summary(row: dict, budget: dict) -> dict[str, Any]:
        return {
            "run_id": budget["source"]["id"],
            "epoch": budget["source"]["epoch"],
            "record_id": row["id"],
            "revision": row["revision"],
            "sha256": row["budget_sha256"],
            "consumed_ns": _segments(budget["segments"]),
            "segments": len(budget["segments"]),
            "pin": budget["pin"],
            "deadline": budget["deadline"],
        }

    def read_closed(self, run_id: str) -> dict[str, Any] | None:
        with self.repo.transaction(self.owner) as connection:
            current = self._actual(connection, run_id, queued_read_only=True)
            row, budget = self._record(current)
            if row is None:
                return None
            if current["status"] == "queued":
                raise LifecycleError("queued旧观察不能携带执行预算")
            if {key: value for key, value in budget.items() if key != "segments"} != self._authority(
                connection, current
            ):
                raise LifecycleError("闭合执行预算不属于原来源或原限制")
            return self._summary(row, budget)


def closed_budgets(target: Any, binding: LifecycleBinding, *, required: bool) -> dict[str, Any] | None:
    store = BudgetStore(target.repo, target.owner, binding, target.lifecycle_session)
    values = [store.read_closed(run_id) for run_id in target.run_ids]
    if not values or any(value is None for value in values):
        if required or any(value is not None for value in values):
            raise LifecycleError("私密生命周期缺少完整闭合预算")
        return None
    return {"format": FORMAT, "runs": values}


def verify_saved_budgets(repo: Any, owner: str, state: dict, record: dict, binding: LifecycleBinding) -> None:
    store = BudgetStore(repo, owner, binding, record["session_id"])
    values = [store.read_closed(run["id"]) for run in state["runs"]]
    expected = state.get("execution_budget")
    if expected is None:
        if any(value is not None for value in values):
            raise LifecycleError("不能降级已启用的执行预算")
        return
    if any(value is None for value in values) or expected != {"format": FORMAT, "runs": values}:
        raise LifecycleError("私密生命周期闭合预算已经改变")
