"""Pin body-free loop limits to an authoritative leased run and retry epoch."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.agent.loop_policy import LoopPolicy
from mingjing_core.agent.runtime_config import (
    RuntimeConfig,
    config_hash,
    validate_runtime_config,
)
from mingjing_core.application.agent_thread_scope import assert_thread, thread_id
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import Clock, get_clock

SCHEMA = "agent-runtime-limits-v1"
PIN_KEYS = {
    "schema",
    "owner",
    "run_id",
    "subject",
    "thread_id",
    "lane",
    "epoch",
    "depth",
    "config",
    "config_sha256",
    "deadline_at",
    "origin",
    "pin_sha256",
}


def identity(run: dict[str, Any], epoch: int) -> dict[str, Any]:
    return {
        "owner": run["owner"],
        "run_id": run["id"],
        "subject": run["subject"],
        "thread_id": thread_id(run),
        "lane": run["lane"],
        "epoch": epoch,
        "depth": run["request"].get("depth", "standard"),
    }


def validate_pin(value: Any, run: dict[str, Any], epoch: int) -> RuntimeConfig:
    if not isinstance(value, dict) or set(value) != PIN_KEYS:
        raise EvidenceError("运行限制凭据结构无效")
    if (
        value["schema"] != SCHEMA
        or type(value["epoch"]) is not int
        or any(value[key] != expected for key, expected in identity(run, epoch).items())
        or value["origin"] not in {"new_epoch", "legacy_unpinned_journal"}
        or value["pin_sha256"] != config_hash({key: item for key, item in value.items() if key != "pin_sha256"})
    ):
        raise EvidenceError("运行限制凭据与当前身份不符")
    config = validate_runtime_config(value["config"])
    if config.sha256 != value["config_sha256"]:
        raise EvidenceError("运行限制配置摘要不符")
    deadline(value)
    return config


def deadline(pin: dict[str, Any]) -> datetime:
    try:
        value = datetime.fromisoformat(pin["deadline_at"])
        if value.tzinfo is None:
            raise ValueError
        return value
    except (ValueError, TypeError):
        raise EvidenceError("运行限制截止时间无效") from None


class RuntimeLimits:
    def __init__(self, repo: PostgresRepository, *, clock: Clock | None = None) -> None:
        self.repo, self.clock = repo, clock or get_clock()

    def _history(self, values: Any, current: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(values, dict):
            raise EvidenceError("运行限制周期记录无效")
        for key, pin in values.items():
            if not isinstance(key, str) or not key.isdecimal() or str(int(key)) != key:
                raise EvidenceError("运行限制周期标识无效")
            epoch = int(key)
            if epoch > current["retry_epoch"]:
                raise EvidenceError("运行限制周期不能来自未来")
            validate_pin(pin, current, epoch)
        return dict(values)

    def _new(
        self, connection: Any, current: dict[str, Any], config: RuntimeConfig, previous: dict[str, Any]
    ) -> dict[str, Any]:
        epoch = current["retry_epoch"]
        if previous:
            old = previous.get(str(epoch - 1))
            if old is None:
                raise EvidenceError("运行限制周期缺少前一份凭据")
            config = validate_pin(old, current, epoch - 1)
        policy = config.policy(current["lane"], current["request"].get("depth", "standard"))
        exists = connection.execute(
            sql.SQL("SELECT 1 FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s LIMIT 1").format(
                self.repo.table("core_run_steps")
            ),
            (current["owner"], current["id"], epoch),
        ).fetchone()
        ends = self.clock.now() + timedelta(seconds=policy.seconds)
        if current["deadline_at"] is not None:
            ends = min(ends, current["deadline_at"])
        value = {
            "schema": SCHEMA,
            **identity(current, epoch),
            "config": config.model_dump(),
            "config_sha256": config.sha256,
            "deadline_at": ends.isoformat(),
            "origin": "legacy_unpinned_journal" if exists else "new_epoch",
        }
        return dict(value, pin_sha256=config_hash(value))

    def policy(self, run: dict[str, Any], configured: RuntimeConfig) -> LoopPolicy:
        if type(run.get("retry_epoch")) is not int or run["retry_epoch"] < 0:
            raise EvidenceError("运行限制需要明确的当前周期")
        with self.repo.transaction(run["owner"]) as connection:
            current = self.repo._run(self.repo._leased(connection, run["owner"], run["id"], run["lease_token"]))
            if (
                current["runtime"] != "v4"
                or type(current["retry_epoch"]) is not int
                or current["retry_epoch"] != run["retry_epoch"]
                or identity(current, current["retry_epoch"]) != identity(run, run["retry_epoch"])
                or current["cancel_requested_at"] is not None
            ):
                raise EvidenceError("运行限制缺少当前批次授权")
            self.repo.assert_scope(current["owner"], current["subject"])
            assert_thread(self.repo, current)
            usage = dict(current["usage"])
            meta = usage.get("agent_runtime", {})
            if not isinstance(meta, dict):
                raise EvidenceError("运行限制元数据无效")
            pins = self._history(meta.get("limit_epochs", {}), current)
            key = str(current["retry_epoch"])
            if key not in pins:
                pins[key] = self._new(connection, current, validate_runtime_config(configured), pins)
            config = validate_pin(pins[key], current, current["retry_epoch"])
            policy = config.policy(current["lane"], current["request"].get("depth", "standard"))
            usage["agent_runtime"] = dict(meta, limit_epochs=pins)
            self._store(connection, current, usage, pins[key], policy)
            return policy

    def _store(self, connection: Any, run: dict[str, Any], usage: dict, pin: dict, policy: LoopPolicy) -> None:
        # A process restart must not reset its wall-clock allowance or enlarge a lease.
        connection.execute(
            sql.SQL(
                "UPDATE {} SET usage=%s,deadline_at=LEAST(coalesce(deadline_at,%s),%s),"
                "lease_until=LEAST(lease_until,now()+%s*interval '1 second') WHERE owner=%s AND id=%s"
            ).format(self.repo.table("core_runs")),
            (Jsonb(usage), deadline(pin), deadline(pin), policy.lease_seconds, run["owner"], run["id"]),
        )
