"""Freeze private initial context per run/epoch without caching bodies in checkpoints.

The codec reflects the current dataclasses, including normalized reasoning fields.
Missing/unknown fields or unsupported future types reject old snapshots; callers
must explicitly start a new epoch rather than silently drop private protocol data.
The builder must only assemble local context and must never call a provider.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, fields, is_dataclass
from types import UnionType
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

from mingjing_core.agent.context_types import ContextBuild
from mingjing_core.application.agent_commit_versions import reconcile_versions
from mingjing_core.application.agent_thread_scope import assert_thread
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict, RevisionConflict, ScopeError
from mingjing_core.domain.json_values import ensure_finite_json
from mingjing_core.repositories.dependencies import lineage_key
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint
from mingjing_core.timekit.clock import Clock, get_clock

STAGE = "agent_initial_context"
SCHEMA = "agent-initial-context-v1"


def _reject() -> None:
    raise EvidenceError("初始上下文快照格式已变更或损坏，需要明确的新批次")


def _decode(expected: Any, value: Any) -> Any:
    origin, args = get_origin(expected), get_args(expected)
    if expected is Any:
        ensure_finite_json(value)
        return copy.deepcopy(value)
    if is_dataclass(expected):
        if not isinstance(value, dict) or set(value) != {item.name for item in fields(expected)}:
            _reject()
        hints = get_type_hints(expected)
        return expected(**{name: _decode(hints[name], child) for name, child in value.items()})
    if origin in (Union, UnionType):
        for candidate in args:
            try:
                return _decode(candidate, value)
            except (EvidenceError, ValueError, TypeError):
                continue
        _reject()
    if origin is Literal:
        if not any(type(value) is type(item) and value == item for item in args):
            _reject()
        return value
    if origin in (tuple, list):
        if not isinstance(value, list):
            _reject()
        types = [args[0]] * len(value) if origin is list or args[-1:] == (Ellipsis,) else args
        if len(types) != len(value):
            _reject()
        result = [_decode(kind, child) for kind, child in zip(types, value, strict=True)]
        return tuple(result) if origin is tuple else result
    if origin is dict:
        if not isinstance(value, dict):
            _reject()
        return {_decode(args[0], key): _decode(args[1], child) for key, child in value.items()}
    if expected is type(None) and value is None or expected in (str, int, bool, float) and type(value) is expected:
        return value
    _reject()


def _encode(build: ContextBuild) -> dict[str, Any]:
    if type(build) is not ContextBuild:
        _reject()
    try:
        encoded = json.dumps(asdict(build), ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 2_000_000:
            _reject()
        value = json.loads(encoded)
        _decode(ContextBuild, value)
        return value
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise EvidenceError("初始上下文快照不能安全序列化") from None


class AgentSnapshotStore:
    def __init__(self, repo: PostgresRepository, *, clock: Clock | None = None) -> None:
        self.repo, self.memory, self.clock = repo, MemoryService(repo), clock or get_clock()

    def _authority(self, connection: Any, run: Mapping[str, Any]) -> dict[str, Any]:
        owner, ident, token, epoch = (run.get(key) for key in ("owner", "id", "lease_token", "retry_epoch"))
        if any(not isinstance(value, str) or not value for value in (owner, ident, token)):
            raise ScopeError("初始上下文需要完整运行身份")
        if run.get("owner_user_id", owner) != owner or type(epoch) is not int or epoch < 0:
            raise ScopeError("初始上下文运行身份不符")
        row = self.repo._leased(connection, owner, ident, token)
        if row["retry_epoch"] != epoch or row["cancel_requested_at"] is not None:
            raise LeaseConflict("初始上下文运行批次已失效")
        if row["deadline_at"] is not None and row["deadline_at"] <= self.clock.now():
            raise LeaseConflict("初始上下文运行已过期")
        if row["runtime"] != "v4" or row["subject"] != run.get("subject"):
            raise ScopeError("初始上下文人物或运行版本不符")
        self.repo.assert_scope(owner, row["subject"])
        thread = assert_thread(self.repo, row)
        selected = row["request"].get("case_ids", [])
        if not isinstance(selected, list) or any(not isinstance(ident, str) for ident in selected) or len(selected) > 8:
            raise ScopeError("初始上下文事项范围无效")
        for selected_id in selected:
            if self.repo.get(owner, "case", selected_id)["subject_id"] != row["subject"]:
                raise ScopeError("初始上下文事项不属于当前人物")
        source = self.memory.get_source(owner, row["request"].get("source_message_id"))
        policy = source.get("policy", {})
        if (
            source["subject_id"] != row["subject"]
            or source["status"] != "active"
            or source.get("role") != "user"
            or source.get("thread_id") != thread
            or source.get("content") != row["request"].get("message")
            or policy.get("origin") != "current_user"
            or policy.get("run_context") is not True
            or self.repo.is_revoked(owner, "message", source["id"])
        ):
            raise EvidenceError("初始上下文的受信来源已变更或撤销")
        return row

    def _revocations(self, owner: str) -> list[dict[str, Any]]:
        return sorted(self.repo.revocations(owner), key=lambda row: (row["kind"], row["entity_id"]))

    def _privacy(self, owner: str, versions: dict[str, int]) -> str:
        relevant = []
        lineage = {lineage_key(key) for key in versions}
        for row in self._revocations(owner):
            if row["kind"] + ":" + row["entity_id"] in lineage or (
                row["kind"] == "source_span" and "message:" + str(row["metadata"].get("message_id")) in versions
            ):
                relevant.append({key: row[key] for key in ("kind", "entity_id", "operation", "metadata", "revision")})
        return fingerprint(relevant)

    def _dependencies(
        self, row: dict[str, Any], build: ContextBuild, *, versions: dict[str, int] | None = None
    ) -> None:
        owner, subject = row["owner"], row["subject"]
        versions = build.injected_versions if versions is None else versions
        if (
            not isinstance(versions, dict)
            or not versions
            or "message:" + row["request"]["source_message_id"] not in versions
        ):
            raise EvidenceError("初始上下文缺少精确原话依赖")
        for key, revision in versions.items():
            kind, separator, ident = lineage_key(key).partition(":")
            if not separator or type(revision) is not int or revision < 1 or kind in {"owner", "global", "subject"}:
                raise EvidenceError("初始上下文依赖必须是精确实体版本")
            entity = self.repo.get(owner, kind, ident, include_deleted=True)
            if entity["subject_id"] != subject or entity["status"] in {"deleted", "stopped", "superseded"}:
                raise EvidenceError("初始上下文依赖已经撤销")
            if entity.get("case_id") is not None and entity["case_id"] not in row["request"].get("case_ids", []):
                raise ScopeError("初始上下文依赖不在已选择事项")
            if entity["revision"] != revision:
                raise RevisionConflict("初始上下文实体版本已经改变")
            if self.repo.is_revoked(owner, kind, ident):
                raise EvidenceError("初始上下文依赖已经撤销")
        if not self.repo.verify_versions(owner, versions):
            raise RevisionConflict("初始上下文精确依赖已改变，不能替换旧快照")

    def _load(self, row: dict[str, Any]) -> ContextBuild | None:
        ident = f"{row['id']}:e{row['retry_epoch']}:{STAGE}"
        try:
            saved = self.repo.get(row["owner"], "runtime_step", ident, include_deleted=True)
        except ScopeError:
            return None
        if saved["status"] != "active" or saved["subject_id"] != row["subject"]:
            raise EvidenceError("初始上下文快照已经撤销，不能重建")
        if (saved.get("schema"), saved.get("run_id"), saved.get("epoch"), saved.get("stage")) != (
            SCHEMA,
            row["id"],
            row["retry_epoch"],
            STAGE,
        ):
            _reject()
        if saved.get("request_sha256") != fingerprint(row["request"]):
            raise RevisionConflict("运行请求已经改变，不能重放旧初始上下文")
        output = saved.get("output")
        if fingerprint(output) != saved.get("output_sha256"):
            _reject()
        build = _decode(ContextBuild, output)
        initial = reconcile_versions(self.repo, row, build.injected_versions)
        registered = reconcile_versions(self.repo, row, row["state_version"])
        self._dependencies(row, build, versions=initial)
        if any(registered.get(key) != revision for key, revision in initial.items()) or saved.get(
            "privacy_sha256"
        ) != self._privacy(row["owner"], build.injected_versions):
            raise RevisionConflict("初始上下文依赖或撤销范围已改变")
        if registered != row["state_version"]:
            # Reconciliation only admits exact current-epoch effects. Preserve the
            # original frozen bytes and let ToolRegistry replay the actual receipt.
            self.repo.set_run_dependencies(row["owner"], row["id"], registered, row["lease_token"])
            row["state_version"] = registered
        return copy.deepcopy(build)

    def load_or_build(self, run: Mapping[str, Any], builder: Callable[[], ContextBuild]) -> ContextBuild:
        owner = run.get("owner")
        if not isinstance(owner, str) or not owner:
            raise ScopeError("初始上下文需要明确身份")
        with self.repo.transaction(owner) as connection:
            current = self._authority(connection, run)
            cached = self._load(current)
            if cached is not None:
                return cached
            ledger_before = fingerprint(self._revocations(owner))
        # ContextEngine owns its bounded read transaction. No provider work or
        # long-lived owner transaction is introduced by this storage boundary.
        output = _encode(builder())
        build = _decode(ContextBuild, output)
        with self.repo.transaction(owner) as connection:
            current = self._authority(connection, run)
            cached = self._load(current)
            if cached is not None:
                return cached
            if ledger_before != fingerprint(self._revocations(owner)):
                raise RevisionConflict("上下文装配期间撤销范围发生改变")
            self._dependencies(current, build)
            if current["state_version"] and current["state_version"] != build.injected_versions:
                raise RevisionConflict("已有运行依赖不能由新上下文覆盖")
            self.repo.set_run_dependencies(owner, current["id"], build.injected_versions, run["lease_token"])
            ident = f"{current['id']}:e{current['retry_epoch']}:{STAGE}"
            data = {
                "schema": SCHEMA,
                "run_id": current["id"],
                "epoch": current["retry_epoch"],
                "stage": STAGE,
                "output": output,
                "output_sha256": fingerprint(output),
                "request_sha256": fingerprint(current["request"]),
                "privacy_sha256": self._privacy(owner, build.injected_versions),
                "source_ids": [key[8:] for key in build.injected_versions if key.startswith("message:")],
                "fact_ids": [key[5:] for key in build.injected_versions if key.startswith("fact:")],
            }
            self.repo.put(
                owner,
                "runtime_step",
                ident,
                data,
                subject=current["subject"],
                expected_revision=0,
                operation_id="agent-snapshot:" + ident,
            )
            self.repo.checkpoint_run(
                owner, current["id"], {"phase": STAGE, "ids": [ident], "schema_version": SCHEMA}, run["lease_token"]
            )
            return copy.deepcopy(build)
