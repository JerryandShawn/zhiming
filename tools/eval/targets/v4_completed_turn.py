"""Observe and freeze an already committed answer without executing its terminal run."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from typing import Any

from psycopg import sql

from mingjing_core.application.read_result import read_result
from mingjing_core.repositories.postgres import fingerprint
from tools.eval.lifecycle_identity import LifecycleError

from .base import TurnResult
from .v4_observations import semantic_observations, structural_observations, tool_steps


def native_answer(repo: Any, owner: str, run_id: str) -> dict[str, Any]:
    run = repo.fetch_run(owner, run_id)
    if run["status"] != "succeeded" or run["runtime"] != "v4" or run["cancel_requested_at"] is not None:
        raise LifecycleError("只读评分需要已经成功提交的原生v4运行")
    result = read_result(run["result"])
    identity = result.get("meta", {}).get("core_run", {})
    if identity.get("run_id") != run_id or identity.get("operation_id") != run["operation_id"]:
        raise LifecycleError("成功信封缺少当前原生运行身份")
    steps = tool_steps(repo, owner, run_id)
    if any(step["status"] != "completed" or step["epoch"] != run["retry_epoch"] for step in steps):
        raise LifecycleError("只读评分不能采用未完成或旧批次工具")
    with repo.transaction(owner) as connection:
        events = connection.execute(
            sql.SQL("SELECT kind,payload FROM {} WHERE owner=%s AND run_id=%s ORDER BY seq").format(
                repo.table("core_run_events")
            ),
            (owner, run_id),
        ).fetchall()
    finals = [event for event in events if event["kind"] == "final"]
    if len(finals) != 1 or finals[0]["payload"].get("envelope") != run["result"]:
        raise LifecycleError("只读评分缺少唯一且一致的真实final事件")
    semantics = semantic_observations(steps) + structural_observations(run)
    names = [event["kind"] for event in events]
    if semantics:
        names = [name for name in names if name != "final"] + [item["name"] for item in semantics]
    return {
        "text": result["text"],
        "receipts": result["receipts"],
        "tools_called": [step["name"] for step in steps],
        "events": names + ["run.completed"],
        "run_id": run_id,
        "epoch": run["retry_epoch"],
        "envelope_sha256": fingerprint(run["result"]),
    }


def freeze_completed(target: Any, turn: int, result: TurnResult) -> dict[str, Any]:
    if type(result) is not TurnResult or not target.run_ids or result.error is not None:
        raise LifecycleError("完成结果需要真实成功TurnResult")
    native = native_answer(target.repo, target.owner, target.run_ids[-1])
    if any(getattr(result, key) != native[key] for key in ("text", "receipts", "tools_called", "events")):
        raise LifecycleError("TurnResult与真实信封、工具或事件不符")
    if result.metadata.get("run_id") != native["run_id"] or result.metadata.get("run_status") != "succeeded":
        raise LifecycleError("TurnResult运行观察身份不符")
    observed = deepcopy(result)
    observed.db = target.inspect_db()
    return {"turn": turn, "native": native, "result": asdict(observed)}


def verify_completed(repo: Any, owner: str, saved: Any) -> TurnResult:
    if not isinstance(saved, dict) or set(saved) != {"turn", "native", "result"}:
        raise LifecycleError("私密完成观察结构无效")
    native = native_answer(repo, owner, saved["native"]["run_id"])
    if native != saved["native"]:
        raise LifecycleError("原生成功结果已经改变")
    try:
        result = TurnResult(**saved["result"])
    except (TypeError, ValueError):
        raise LifecycleError("私密TurnResult格式不符") from None
    if result.error is not None or any(
        getattr(result, key) != native[key] for key in ("text", "receipts", "tools_called", "events")
    ):
        raise LifecycleError("私密TurnResult与原生提交不符")
    return result
