"""Persistent rolling membership limits; no sleeping, network or credential reads."""

from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from mingjing_core.timekit.clock import Clock, SystemClock
from tools.eval.member_budget_store import ledger_transaction
from tools.eval.quota import ProviderStopped

WINDOW = timedelta(hours=5)
BATCH_GAP = timedelta(minutes=20)
MAX_CALLS = 80
ROLES = frozenset({"target", "judge", "probe"})


def _at(value: str) -> datetime:
    try:
        stamp = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValueError("会员调用账本时间无效；停止发送") from None
    if stamp.tzinfo is None:
        raise ValueError("会员调用账本缺少时区；停止发送")
    return stamp.astimezone(UTC)


class MemberBudget:
    def __init__(self, path: Path, run_id: str, clock: Clock | None = None) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}", run_id):
            raise ValueError("会员评测运行标识无效")
        self.path, self.run_id = Path(path), run_id
        # Scenario evaluation freezes the global clock; membership uses physical time.
        self.clock = clock or SystemClock()

    def _now(self) -> datetime:
        stamp = self.clock.now()
        if stamp.tzinfo is None:
            raise ValueError("会员预算时钟必须带时区")
        return stamp.astimezone(UTC)

    def _run(self, state: dict[str, Any]) -> dict[str, Any]:
        return state["runs"].setdefault(
            self.run_id,
            {
                "status": "ready",
                "quota_5h_stops": 0,
                "auto_resumes": 0,
                "batches_completed": 0,
            },
        )

    def _signal(self, reason: str, role: str, run: dict[str, Any]) -> None:
        raise ProviderStopped(
            reason,
            role,
            provider_http_status=run.get("http_status"),
            resume_at=run.get("resume_at"),
        )

    def _check(self, state: dict[str, Any], run: dict[str, Any], now: datetime, role: str) -> None:
        if state.get("weekly_stop"):
            self._signal("quota_weekly", role, state["weekly_stop"])
        if state.get("provider_stop"):
            self._signal("quota_5h", role, state["provider_stop"])
        if run.get("status") != "stopped":
            return
        if run.get("reason") == "member_window_limit" and now >= _at(run["resume_at"]):
            run.update(status="ready", reason=None, resume_at=None)
            return
        self._signal(run.get("reason", "provider_http_error"), role, run)

    def check_open(self, role: str) -> None:
        with ledger_transaction(self.path) as state:
            self._check(state, self._run(state), self._now(), role)

    def before_batch(self, scenario_ids: list[str]) -> None:
        if (
            not 1 <= len(scenario_ids) <= 10
            or len(set(scenario_ids)) != len(scenario_ids)
            or any(not re.fullmatch(r"[A-Z]{1,3}[0-9]{2,3}", value) for value in scenario_ids)
        ):
            raise ValueError("会员评测每批必须为 1–10 个不同的场景标识")
        now = self._now()
        with ledger_transaction(self.path) as state:
            run = self._run(state)
            self._check(state, run, now, "target")
            if state.get("active_batch", {}).get("run_id", self.run_id) != self.run_id:
                raise ValueError("同一会员账号的另一批评测尚未结束")
            active = run.get("active_batch")
            if active:
                if active != scenario_ids:
                    raise ValueError("上一批尚未结束；须从原批续跑")
                return
            if state.get("last_batch_finished_at"):
                resume = _at(state["last_batch_finished_at"]) + BATCH_GAP
                if now < resume:
                    self._signal("batch_cooldown", "target", {"resume_at": resume.isoformat()})
            run.update(
                active_batch=list(scenario_ids),
                status="running",
                batch_started_at=now.isoformat(),
            )
            state["active_batch"] = {
                "run_id": self.run_id,
                "scenario_ids": list(scenario_ids),
            }

    def finish_batch(self) -> None:
        with ledger_transaction(self.path) as state:
            run = self._run(state)
            if not run.get("active_batch"):
                return
            if run.get("status") == "stopped":
                raise ValueError("已停止的批次不能标记完成")
            stamp = self._now().isoformat()
            run.update(active_batch=None, last_batch_finished_at=stamp, status="ready")
            run["batches_completed"] += 1
            state["last_batch_finished_at"] = stamp
            state.pop("active_batch", None)

    def before_provider_request(self, role: str) -> None:
        if role not in ROLES:
            raise ValueError("会员调用角色无效")
        now = self._now()
        with ledger_transaction(self.path) as state:
            run = self._run(state)
            self._check(state, run, now, role)
            if role != "probe" and not run.get("active_batch"):
                raise ValueError("会员目标与评审调用必须属于已登记的批次")
            calls = state["calls"]
            if calls and now < max(_at(call["at"]) for call in calls):
                raise ValueError("会员时钟早于已登记调用；停止发送")
            window = [call for call in calls if _at(call["at"]) > now - WINDOW]
            if len(window) >= MAX_CALLS:
                resume = min(_at(call["at"]) for call in window) + WINDOW
                run.update(
                    status="stopped",
                    reason="member_window_limit",
                    resume_at=resume.isoformat(),
                )
                self._signal("member_window_limit", role, run)
            calls.append({"at": now.isoformat(), "role": role, "run_id": self.run_id})

    def record_stop(self, reason: str, http_status: int | None = None) -> None:
        now = self._now()
        with ledger_transaction(self.path) as state:
            run = self._run(state)
            if run.get("status") == "stopped" and run.get("reason") == reason:
                return
            run.update(
                status="stopped",
                reason=reason,
                stopped_at=now.isoformat(),
                resume_at=None,
            )
            if type(http_status) is int and 100 <= http_status <= 599:
                run["http_status"] = http_status
            if reason == "quota_5h":
                run["quota_5h_stops"] += 1
                if run["quota_5h_stops"] == 1 and run["auto_resumes"] == 0:
                    run["resume_at"] = (now + WINDOW).isoformat()
                state["provider_stop"] = {
                    "run_id": self.run_id,
                    "stopped_at": now.isoformat(),
                    "resume_at": run["resume_at"],
                    "http_status": http_status,
                }
            elif reason == "quota_weekly":
                state["weekly_stop"] = {
                    "stopped_at": now.isoformat(),
                    "http_status": http_status,
                }
                run["warning"] = "线上可能受影响"

    def resume_once(self) -> None:
        now = self._now()
        with ledger_transaction(self.path) as state:
            run = self._run(state)
            if state.get("weekly_stop"):
                self._signal("quota_weekly", "target", state["weekly_stop"])
            eligible = (
                run.get("reason") == "quota_5h"
                and run["quota_5h_stops"] == 1
                and run["auto_resumes"] == 0
                and run.get("resume_at") is not None
                and now >= _at(run["resume_at"])
                and state.get("provider_stop", {}).get("run_id") == self.run_id
            )
            if not eligible:
                self._signal(run.get("reason", "provider_http_error"), "target", run)
            run.update(status="ready", reason=None, resume_at=None, auto_resumes=1)
            state.pop("provider_stop", None)

    def snapshot(self) -> dict[str, Any]:
        now = self._now()
        with ledger_transaction(self.path) as state:
            run = dict(self._run(state))
            calls = state["calls"]
            window = [call for call in calls if _at(call["at"]) > now - WINDOW]
            current = [call for call in calls if call["run_id"] == self.run_id]
            for prefix, selected in (
                ("real", calls),
                ("window", window),
                ("run", current),
            ):
                run[prefix + "_calls_total"] = len(selected)
                counts = Counter(call["role"] for call in selected)
                run[prefix + "_calls_by_role"] = {role: counts[role] for role in sorted(ROLES)}
            run.update(run_id=self.run_id, version=1, max_calls=MAX_CALLS, window_hours=5)
            if state.get("weekly_stop"):
                run.update(
                    status="stopped",
                    reason="quota_weekly",
                    resume_at=None,
                    warning="线上可能受影响",
                )
            return run
