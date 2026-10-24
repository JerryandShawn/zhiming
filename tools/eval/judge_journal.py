"""Private score state; completed physical evidence is reused, ambiguous attempts never resend."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from psycopg import sql

from mingjing_core.domain.contracts import CoreError, ScopeError
from mingjing_core.models.quota_delegated_session import require_active
from mingjing_core.models.quota_runtime import call_scope
from mingjing_core.repositories.postgres import fingerprint
from tools.eval.judges import JUDGE_SCHEMA
from tools.eval.lifecycle_identity import LifecycleError
from tools.eval.targets.v4_core30 import load_core30
from tools.eval.targets.v4_lifecycle_state import read_private
from tools.eval.targets.v4_live_judge import V4LiveJudge

RUBRIC = Path(__file__).parent / "rubric_v1.md"
STAGE = "eval_judge"


class JudgeJournal:
    def __init__(self, target: Any, control: Any, binding: Any, guard: Any) -> None:
        self.target, self.control, self.binding, self.guard = target, control, binding, guard
        if target.lifecycle_session is None or target.repo is None:
            raise LifecycleError("评分日志需要已保存并附着的原场景")
        self.repo, self.owner = target.repo, target.owner
        self.ident = "eval-judge:" + target.lifecycle_session

    def _expected(self) -> dict[str, Any]:
        result = self.target.completed_result(self.control, self.binding, self.guard)
        record = self.control.load(self.target.lifecycle_session, self.binding, self.guard)
        state = read_private(self.repo, self.owner, record, self.binding)
        case = next(case for case in load_core30() if case.id == self.binding.scenario_id)
        index = state["turn"]
        if type(index) is not int or not 1 <= index <= len(case.turns):
            raise LifecycleError("评分轮次不属于固定场景")
        turn = case.turns[index - 1]
        payload = {
            "scenario_id": case.id,
            "user": turn.user,
            "clock": turn.at or case.clock,
            "seed": case.seed.model_dump(mode="json"),
            "receipts": result.receipts,
            "tools_called": result.tools_called,
            "criterion": turn.expect.judge,
            "answer": result.text,
        }
        rubric = RUBRIC.read_text(encoding="utf-8")
        identity = {
            **asdict(self.binding),
            "turn": index,
            "run_id": state["runs"][-1]["id"],
            "epoch": state["runs"][-1]["epoch"],
            "rubric_sha256": fingerprint(rubric),
            "schema_sha256": fingerprint(JUDGE_SCHEMA),
            "request_sha256": fingerprint(payload),
        }
        return {"identity": identity, "payload": payload, "rubric": rubric}

    def _load(self, expected: dict) -> dict | None:
        try:
            row = self.repo.get(self.owner, "runtime_step", self.ident, include_deleted=True)
        except ScopeError:
            return None
        value = row.get("value")
        if (
            row["status"] != "active"
            or row.get("stage") != STAGE
            or not isinstance(value, dict)
            or row.get("value_sha256") != fingerprint(value)
            or any(value.get(key) != expected[key] for key in ("identity", "payload", "rubric"))
        ):
            raise LifecycleError("评分日志身份、正文或校验摘要已经失效")
        return row

    def _write(self, value: dict, previous: dict | None) -> dict:
        expected = self._expected()
        if any(value.get(key) != expected[key] for key in ("identity", "payload", "rubric")):
            raise LifecycleError("评分请求不能替换原候选或已提交正文")
        run = self.repo.fetch_run(self.owner, value["identity"]["run_id"])
        return self.repo.put(
            self.owner,
            "runtime_step",
            self.ident,
            {
                "stage": STAGE,
                "run_id": run["id"],
                "epoch": run["retry_epoch"],
                "source_ids": run["request"].get("source_message_ids", [run["request"]["source_message_id"]]),
                "value": value,
                "value_sha256": fingerprint(value),
            },
            subject=run["subject"],
            expected_revision=previous["revision"] if previous else 0,
            operation_id="eval-score:" + fingerprint([self.ident, value]),
        )

    def prepare(self) -> dict:
        with self.repo.transaction(self.owner):
            expected = self._expected()
            old = self._load(expected)
            if old is not None:
                return old
            return self._write({**expected, "attempt_state": "prepared", "attempt_ids": []}, None)

    def _physical(self, identity: dict) -> list[dict]:
        with self.guard.store.connect() as connection:
            self.guard.store.verify(connection)
            return connection.execute(
                sql.SQL(
                    "SELECT * FROM {} WHERE account_id=%s AND lane='eval' AND role='critic' "
                    "AND run_id=%s AND scenario_id=%s ORDER BY id"
                ).format(self.guard.store.table("core_model_usage")),
                (self.guard.store.account_id, identity["run_id"], identity["scenario_id"]),
            ).fetchall()

    def _completed(self, row: dict) -> dict:
        value = row["value"]
        rows = [item for item in self._physical(value["identity"]) if item["attempt_id"] in value["attempt_ids"]]
        if not 1 <= len(rows) <= 2 or fingerprint(rows) != value.get("physical_sha256"):
            raise LifecycleError("已完成评分的中央物理证据改变")
        return deepcopy(value["result"])

    def _begin(self, judge: V4LiveJudge) -> dict:
        if type(judge) is not V4LiveJudge:
            raise LifecycleError("只允许原生锁定的v4评分器")
        active = require_active()
        handles = judge.provider.tracker.port.registry.resolve("critic")
        if (
            active.guard is not self.guard
            or active.phase != "core"
            or active.approval.candidate != self.binding.candidate_commit
            or not handles
            or any(handle.model != self.binding.model for handle in handles)
        ):
            raise LifecycleError("评分必须使用同候选、同中央守卫与已锁定模型")
        with self.repo.transaction(self.owner):
            row = self.prepare()
            value = deepcopy(row["value"])
            if value["attempt_state"] != "prepared" or judge.rubric != value["rubric"]:
                raise LifecycleError("已在途、未知或变更评分禁止重POST")
            value.update(
                attempt_state="inflight",
                prior_attempt_ids=[item["attempt_id"] for item in self._physical(value["identity"])],
            )
            return self._write(value, row)

    def _finish(self, row: dict, reviewed: dict | None) -> dict:
        value = deepcopy(row["value"])
        actual = [
            item for item in self._physical(value["identity"]) if item["attempt_id"] not in value["prior_attempt_ids"]
        ]
        complete = (
            reviewed is not None
            and (reviewed.get("error") is None or reviewed.get("judge_unavailable") is True)
            and 1 <= len(actual) <= 2
            and all(
                item["finished_at"] is not None
                and item["status"] == "ok"
                and item["model"] == self.binding.model
                and item["provider"] == "kimi_code"
                for item in actual
            )
        )
        value.update(
            attempt_state="completed" if complete else "unknown",
            attempt_ids=[item["attempt_id"] for item in actual],
            result=reviewed if complete else None,
            physical_sha256=fingerprint(actual),
        )
        with self.repo.transaction(self.owner):
            current = self._load(self._expected())
            if current is None or current["revision"] != row["revision"]:
                raise LifecycleError("评分在途状态已经改变，不能覆盖")
            self._write(value, current)
        if not complete:
            raise LifecycleError("评分响应或物理结果未完整确认，禁止自动重POST")
        return deepcopy(reviewed)

    def evaluate(self, judge: V4LiveJudge) -> dict:
        row = self.prepare()
        if row["value"]["attempt_state"] == "completed":
            return self._completed(row)
        if row["value"]["attempt_state"] != "prepared":
            raise LifecycleError("在途或未知评分禁止自动重POST")
        row = self._begin(judge)
        active = require_active()
        scope = replace(active.scope(self.binding.scenario_id), run_id=row["value"]["identity"]["run_id"])
        try:
            with call_scope(scope), judge.provider.tracker.authorize_before_send(lambda: self._authorize_send(row)):
                reviewed = judge.evaluate(deepcopy(row["value"]["payload"]))
        except BaseException:
            self._unknown(row)
            raise
        return self._finish(row, reviewed)

    def _authorize_send(self, row: dict) -> None:
        # The permit may have waited after _begin. Re-read native sources and
        # the private request at the transport's last pre-send callback.
        with self.repo.transaction(self.owner):
            current = self._load(self._expected())
            if (
                current is None
                or current["revision"] != row["revision"]
                or current["value"].get("attempt_state") != "inflight"
                or fingerprint(current["value"]) != fingerprint(row["value"])
            ):
                raise LifecycleError("评分发送前来源、控制记录或在途授权已经失效")

    def _unknown(self, row: dict) -> bool:
        try:
            self._finish(row, None)
        except (LifecycleError, CoreError):
            return False
        return True
