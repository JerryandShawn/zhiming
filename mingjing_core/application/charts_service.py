"""One calculation boundary shared by legacy consultation, HTTP and Agent tools."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Protocol

from mingjing_core.adapters.charts import ChartAdapter
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.domain.json_values import ensure_finite_json
from mingjing_core.knowledge import KnowledgeRegistry
from mingjing_core.knowledge.registry import resolve_pointer


class ChartEngine(Protocol):
    def calculate(
        self, archive: dict[str, Any], date: str, requested_systems: list[str], revision: int, subject: str
    ) -> dict[str, Any]: ...


def authorized_archive(owner: str, subject: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    if snapshot.get("owner_user_id", owner) != owner or snapshot.get("subject_id", subject) != subject:
        raise ScopeError("计算快照不属于当前人物")
    user: dict[str, Any] = {}
    for path, value in snapshot.get("profile", {}).items():
        keys = path.removeprefix("user.").split(".")
        node = user
        for key in keys[:-1]:
            node = node.setdefault(key, {})
        node[keys[-1]] = value
    return {"owner_user_id": owner, "subject_id": subject, "user": user}


class ChartsService:
    def __init__(
        self, factory: Callable[[str], ChartEngine] = ChartAdapter, registry: KnowledgeRegistry | None = None
    ) -> None:
        self.factory, self.registry = factory, registry

    def calculate(
        self,
        owner: str,
        subject: str,
        snapshot: dict[str, Any],
        target: str,
        systems: list[str],
        *,
        topic: str | None = None,
    ) -> dict[str, Any]:
        archive = authorized_archive(owner, subject, snapshot)
        if topic is not None:
            archive["calculation_topic"] = topic
        result = self.factory(owner).calculate(archive, target, systems, snapshot["revision"], subject)
        ensure_finite_json(result)
        return result

    def evaluate(
        self,
        owner: str,
        subject: str,
        snapshot: dict[str, Any],
        target: str,
        systems: list[str],
        *,
        topic: str,
        scale: str,
    ) -> dict[str, Any]:
        result = self.calculate(owner, subject, snapshot, target, systems, topic=topic)
        registry = self.registry or KnowledgeRegistry.load_builtin()
        claims = registry.claims_for(
            result,
            owner=owner,
            subject=subject,
            revision=snapshot["revision"],
            topic=topic,
            time_scale=scale,
            target_date=target,
        )
        return {"calculation": result, "claims": claims["claims"], "gaps": claims["gaps"]}


def verify_calculation_scope(
    result: dict[str, Any],
    owner: str,
    subject: str,
    revision: int,
    *,
    target: str | None = None,
    system: str | None = None,
) -> None:
    """Apply the strict persisted-tool boundary without rewriting native data."""
    ensure_finite_json(result)
    if set(result) != {"profiles", "artifacts", "features", "branches", "errors"}:
        raise EvidenceError("计算引擎结果结构无效")
    for group in ("profiles", "artifacts", "features"):
        if not isinstance(result[group], dict):
            raise EvidenceError("计算产物索引无效")
        for ident, row in result[group].items():
            if not isinstance(row, dict) or row.get("id") != ident:
                raise EvidenceError("计算产物身份无效")
            _scope(row, owner, subject, revision)
    if not isinstance(result["branches"], list) or not isinstance(result["errors"], list):
        raise EvidenceError("计算分支或错误结构无效")
    for row in result["branches"]:
        _scope(row, owner, subject, revision)
        if not isinstance(row.get("id"), str) or not row["id"]:
            raise EvidenceError("计算时间分支身份无效")
    verify_links(result, target, system)


def verify_links(result: dict[str, Any], target: str | None, system: str | None) -> None:
    branches = {row["id"] for row in result["branches"]}
    for artifact in result["artifacts"].values():
        profile = result["profiles"].get(artifact.get("profile_id"))
        if (
            profile is None
            or artifact.get("branch_id") not in branches
            or any(artifact.get(key) != profile.get(key) for key in ("branch_id", "system"))
        ):
            raise EvidenceError("计算产物来源或分支绑定无效")
        if target is not None and artifact.get("target_date") != target:
            raise EvidenceError("计算产物目标日期不符")
        if system is not None and artifact.get("system") != system:
            raise EvidenceError("计算产物体系不符")
    for feature in result["features"].values():
        artifact = result["artifacts"].get(feature.get("artifact_id"))
        if artifact is None or feature.get("branch_id") != artifact.get("branch_id"):
            raise EvidenceError("计算依据没有对应产物")
        try:
            actual = resolve_pointer(artifact, feature.get("path"))
            expected = json.dumps(feature.get("value"), sort_keys=True, allow_nan=False)
            if json.dumps(actual, sort_keys=True, allow_nan=False) != expected:
                raise ValueError("value mismatch")
        except (ValueError, TypeError, KeyError):
            raise EvidenceError("计算依据引用与真实值不符") from None


def _scope(row: dict[str, Any], owner: str, subject: str, revision: int) -> None:
    if not isinstance(row, dict) or row.get("owner_user_id") != owner or row.get("subject_id") != subject:
        raise ScopeError("计算产物归属不匹配")
    if type(row.get("revision")) is not int or row["revision"] != revision:
        raise EvidenceError("计算产物版本不匹配")
