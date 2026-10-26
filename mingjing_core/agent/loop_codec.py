"""Private normalized message codec and verified tool lineage for a recoverable cycle."""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable, Iterator
from dataclasses import asdict
from typing import Any

from mingjing_core.application.agent_snapshots import _decode
from mingjing_core.application.agent_tools_contracts import ToolResult
from mingjing_core.application.member_run_scope import member_run_scope
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.models.errors import ModelProtocolError
from mingjing_core.models.port import AssistantMessage, ChatMessage, ModelPort, StreamEvent
from mingjing_core.repositories.dependencies import entity_dependency

from .loop_policy import RunControl


def assistant_output(value: AssistantMessage) -> dict[str, Any]:
    try:
        output = json.loads(json.dumps(asdict(value), ensure_ascii=False, allow_nan=False))
        decoded = _decode(AssistantMessage, output)
        calls = decoded.tool_calls
        if len({call.id for call in calls}) != len(calls) or any(
            not call.id or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,79}", call.name) is None for call in calls
        ):
            raise ValueError("invalid normalized call identity")
        return {"assistant": output}
    except (ValueError, TypeError, EvidenceError):
        raise ModelProtocolError() from None


def assistant_from(output: dict[str, Any]) -> AssistantMessage:
    try:
        return _decode(AssistantMessage, output["assistant"])
    except (KeyError, TypeError, EvidenceError):
        raise ModelProtocolError() from None


def tool_message(
    call_id: str, result: ToolResult, cycle: str, *, aliases: dict[str, dict[str, Any]] | None = None
) -> ChatMessage:
    output = result.model_dump()
    if output["data"].get("adapter_mode") == "p8_v1_1":
        from mingjing_core.application.agent_p8_charts import tool_projection

        output["data"] = tool_projection(output["data"])
    output["data"].pop("registered_aliases", None)
    output["data"].pop("alias_registration", None)
    if aliases is not None:
        # Only the caller's already attested registry is projected, never tool-supplied aliases.
        registered = {
            key: {name: row[name] for name in ("kind", "id", "revision", "native_id", "basis") if name in row}
            for key, row in aliases.items()
            if re.fullmatch(r"[cr][1-9][0-9]*", key) or row.get("kind") == "case" and row.get("basis") == "case_index"
        }
        if registered:
            output["data"]["registered_aliases"] = registered
            output["data"]["alias_registration"] = "verified_current_run"
    return ChatMessage(
        "tool",
        json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False),
        tool_call_id=call_id,
        tool_cycle=cycle,
    )


class ObservedPort(ModelPort):
    """Use the port's current complete codec while observing every streamed fragment."""

    def __init__(self, port: ModelPort, control: RunControl, text: Callable[[str], None]) -> None:
        self.port, self.control, self.text = port, control, text

    def stream(self, messages: list[ChatMessage], **kwargs: Any) -> Iterator[StreamEvent]:
        self.control.poll()
        role = kwargs.setdefault("role", "primary")
        with member_run_scope(self.control.repo, self.control.run, role=role):
            stream = self.port.stream(messages, **kwargs)
            try:
                for event in stream:
                    self.control.poll()
                    if event.type == "text":
                        self.text(event.data)
                    yield event
            finally:
                close = getattr(stream, "close", None)
                if close is not None:
                    close()


def candidates(name: str, result: ToolResult) -> list[tuple[str, str]]:
    rows = []
    if name == "memory_search":
        rows.extend((item["entity_kind"], item["id"]) for item in result.data.get("items", []))
    if name == "profile_get":
        rows.extend(("fact", item["id"]) for item in result.data.get("facts", []))
    if name == "calendar_lookup":
        rows.extend(("fact", item["id"]) for day in result.data.get("days", []) for item in day.get("events", []))
    receipt = result.receipt or {}
    if receipt.get("kind") in {
        "fact",
        "note",
        "proposal",
        "case",
        "feedback",
        "followup",
        "reminder",
        "thread",
    } and isinstance(receipt.get("id"), str):
        rows.append((receipt["kind"], receipt["id"]))
    return list(dict.fromkeys(rows))


def _verified_row(
    service: Any, run: dict[str, Any], kind: str, ident: str, *, index_case: bool = False
) -> dict[str, Any]:
    allowed = {
        "fact",
        "message",
        "note",
        "episode",
        "proposal",
        "case",
        "feedback",
        "followup",
        "reminder",
        "thread",
        "artifact",
        "interpretive_claim",
    }
    if not isinstance(kind, str) or kind not in allowed or not isinstance(ident, str) or not 1 <= len(ident) <= 200:
        raise ScopeError("工具依赖身份无效")
    row = service.repo.get(run["owner"], kind, ident, include_deleted=True)
    selected = set(run["request"].get("case_ids", []))
    if row["subject_id"] != run["subject"] or row["status"] in {"deleted", "stopped", "superseded"}:
        raise ScopeError("工具依赖不属于有效人物资料")
    if (
        row.get("case_id") is not None
        and row["case_id"] not in selected
        or kind == "case"
        and ident not in selected
        and not index_case
    ):
        raise ScopeError("工具依赖不在已选择事项")
    if service.repo.is_revoked(run["owner"], kind, ident):
        raise EvidenceError("工具依赖已经撤销")
    if kind in {"artifact", "interpretive_claim"} and (
        row.get("run_id") != run["id"] or type(row.get("epoch")) is not int or row["epoch"] != run["retry_epoch"]
    ):
        raise ScopeError("专业依据不属于当前运行批次")
    if kind == "message" and (
        row.get("thread_id") != "life:" + run["subject"] or row.get("role") not in {"user", "assistant"}
    ):
        raise ScopeError("工具来源不在主线程")
    if kind == "fact" and (
        row.get("consent") != "granted"
        or row.get("assertion_status") == "legacy_unverified"
        or not row.get("source_refs")
    ):
        raise ScopeError("工具事实没有有效授权来源")
    return row


def _source_links(service: Any, run: dict[str, Any], kind: str, row: dict[str, Any]) -> list[tuple[str, str]]:
    pending = [("message", value) for value in row.get("source_ids", [])]
    pending.extend(("fact", value) for value in (*row.get("fact_ids", []), *row.get("used_fact_ids", [])))
    if row.get("source_fact_id"):
        pending.append(("fact", row["source_fact_id"]))
    for ref in row.get("source_refs", []):
        source = _verified_row(service, run, "message", ref["message_id"])
        if source["revision"] != ref.get("version", source["revision"]):
            raise RevisionConflict("工具原话版本已经改变")
        if kind == "fact" and source.get("role") != "user":
            raise ScopeError("工具事实必须来自用户原话")
        start, end = ref.get("start", 0), ref.get("end", len(source["content"]))
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(source["content"]):
            raise EvidenceError("工具原话区间无效")
        if "quote" in ref and source["content"][start:end] != ref["quote"]:
            raise EvidenceError("工具原话与来源不一致")
        if kind == "fact" and not {"version", "start", "end", "quote"} <= set(ref):
            raise EvidenceError("工具事实缺少完整原话区间")
        for revoked in service.repo.revocations(run["owner"]):
            span = revoked["metadata"]
            if (
                revoked["kind"] == "source_span"
                and span.get("message_id") == source["id"]
                and max(start, span["start"]) < min(end, span["end"])
            ):
                raise EvidenceError("工具原话区间已经撤销")
        pending.append(("message", source["id"]))
    return pending


def _registries(service: Any, run: dict[str, Any], name: str, result: ToolResult) -> tuple[dict, dict, dict]:
    from mingjing_core.application.agent_case_index_lineage import case_index_lineage
    from mingjing_core.application.agent_chart_lineage import chart_lineage
    from mingjing_core.application.agent_tarot_lineage import tarot_lineage

    rows, captured = [], {}
    if name == "chart_compute":
        rows, captured = chart_lineage(service, run, result)
    elif name in {"daily_transit", "window_search", "almanac"}:
        from mingjing_core.application.agent_p8_tool_lineage import p8_tool_lineage

        rows, captured = p8_tool_lineage(service, run, name, result)
    elif name in {"tarot_start", "tarot_read"}:
        rows, captured = tarot_lineage(service, run, name, result)
    indexes = case_index_lineage(service, run, result) if name == "case_list" else []
    return {(row["kind"], row["id"]): row for row in rows}, {(row["kind"], row["id"]): row for row in indexes}, captured


def verified_versions(
    service: Any, run: dict[str, Any], name: str, result: ToolResult
) -> tuple[dict[str, int], list[dict]]:
    """Resolve identifiers against PG, never trust returned revision/scope claims."""
    pending, versions, records = candidates(name, result), {}, []
    with service.repo.transaction(run["owner"]):
        professional, indexes, captured = _registries(service, run, name, result)
        pending.extend(professional)
        pending.extend(indexes)
        while pending:
            kind, ident = pending.pop(0)
            if kind in {"artifact", "interpretive_claim"} and (kind, ident) not in professional:
                raise EvidenceError("专业依据缺少本轮计算步骤证明")
            index_case = (kind, ident) in indexes
            row = _verified_row(service, run, kind, ident, index_case=index_case)
            receipt = result.receipt or {}
            if (
                receipt.get("write_status") == "saved"
                and receipt.get("kind") == kind
                and receipt.get("id", receipt.get("fact_id")) == ident
                and (type(receipt.get("revision")) is not int or receipt["revision"] != row["revision"])
            ):
                if name != "case_update" or kind != "case" or not result.ok or result.ends_turn:
                    raise RevisionConflict("工具写入后实体已被其他修订改变，不能采用旧回执")
                from mingjing_core.application.agent_case_receipt_replay import assert_case_receipt_replay

                assert_case_receipt_replay(service.repo, run, receipt, row)
            key = entity_dependency(kind, ident)
            if key in versions:
                continue
            if len(versions) >= 1024:
                raise EvidenceError("工具依赖闭包超过当前上限")
            versions[key] = row["revision"]
            records.append(
                dict(
                    kind=kind,
                    id=ident,
                    revision=row["revision"],
                    **{
                        key: value
                        for key, value in {
                            **professional.get((kind, ident), {}),
                            **indexes.get((kind, ident), {}),
                        }.items()
                        if key not in {"kind", "id", "revision"}
                    },
                )
            )
            if not index_case or ident in run["request"].get("case_ids", []):
                pending.extend(_source_links(service, run, kind, row))
        for key, value in captured.items():
            if key in versions and versions[key] != value:
                raise RevisionConflict("计算来源版本与实际资料不一致")
            versions[key] = value
        if not service.repo.verify_versions(run["owner"], versions):
            raise RevisionConflict("工具依赖在读取期间发生改变")
    return versions, records


def extend_aliases(aliases: dict[str, dict[str, Any]], records: list[dict[str, Any]]) -> None:
    for row in records:
        if any(value["kind"] == row["kind"] and value["id"] == row["id"] for value in aliases.values()):
            continue
        prefix = {"fact": "f", "message": "m", "note": "n", "artifact": "c", "interpretive_claim": "r"}.get(
            row["kind"], "e"
        )
        number = max([int(key[1:]) for key in aliases if re.fullmatch(prefix + r"\d+", key)] or [0]) + 1
        aliases[prefix + str(number)] = copy.deepcopy(row)
