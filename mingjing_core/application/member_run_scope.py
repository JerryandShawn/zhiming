"""Bind member accounting at model I/O to the currently leased PG run."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import replace
from typing import Any

from mingjing_core.agent.journal import Journal
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.models.quota_runtime import CallScope, call_scope, current_scope
from mingjing_core.models.quota_types import GuardRejected
from mingjing_core.repositories.postgres import PostgresRepository


@contextmanager
def member_run_scope(repo: PostgresRepository, run: Mapping[str, Any], *, role: str) -> Iterator[None]:
    if role not in {"primary", "critic"}:
        raise EvidenceError("Agent模型角色只能由受信主模型或评审入口指定")
    inherited = current_scope()
    with repo.transaction(run["owner"]) as connection:
        current = Journal(repo, run["owner"])._leased(connection, run)
        lane = current.get("lane")
        if lane not in {"interactive", "background"}:
            raise EvidenceError("模型调用缺少持久通道身份")
    if inherited.lane in {"eval", "probe"}:
        # The physical PG guard still checks the existing batch, scenario and
        # short-lived manual authorization. Missing authority never becomes chat.
        selected = replace(inherited, run_id=current["id"])
    else:
        if any(getattr(inherited, name) is not None for name in ("batch_id", "authorization_id", "scenario_id")):
            raise GuardRejected("manual_start_required")
        if inherited.lane == "background" and lane == "interactive":
            raise EvidenceError("嵌套模型调用不能扩大后台预留权限")
        selected = CallScope(lane=lane, run_id=current["id"])
    with call_scope(selected):
        yield
