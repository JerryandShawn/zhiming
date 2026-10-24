"""Body-free per-epoch witness prevents deletion from downgrading new proof runs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.agent_case_capability import case_effect_capability
from mingjing_core.domain.case_effects import MARKER, MAX_WRITES, PROTOCOL, SCHEMA
from mingjing_core.domain.case_effects import STAGE as STAGE
from mingjing_core.domain.contracts import EvidenceError


def marker_cases(run: Mapping[str, Any]) -> dict[str, list[int]] | None:
    case_effect_capability(run)
    protocols = run["usage"].get(PROTOCOL, {})
    if not isinstance(protocols, dict) or any(
        not isinstance(epoch, str) or not epoch.isdecimal() or schema != SCHEMA for epoch, schema in protocols.items()
    ):
        raise EvidenceError("事项版本证据协议声明损坏")
    epoch = str(run["retry_epoch"])
    markers = run["usage"].get(MARKER)
    if markers is None:
        if epoch in protocols:
            raise EvidenceError("新事项版本证据标记缺失，不能降级旧协议")
        return None
    if not isinstance(markers, dict):
        raise EvidenceError("事项版本证据模式损坏")
    value = markers.get(epoch)
    if value is None:
        if epoch in protocols:
            raise EvidenceError("当前周期的事项版本证据标记缺失")
        return None
    if protocols.get(epoch) != SCHEMA:
        raise EvidenceError("事项版本证据缺少独立协议声明")
    if not isinstance(value, dict) or set(value) != {"schema", "cases"} or value["schema"] != SCHEMA:
        raise EvidenceError("事项版本证据格式不受支持")
    cases = value["cases"]
    if not isinstance(cases, dict) or set(cases) - set(run["request"].get("case_ids", [])):
        raise EvidenceError("事项版本证据扩大了已选范围")
    for ident, sequences in cases.items():
        if (
            not isinstance(ident, str)
            or not isinstance(sequences, list)
            or not sequences
            or len(sequences) > MAX_WRITES
            or any(type(seq) is not int or seq < 1 for seq in sequences)
            or sequences != sorted(set(sequences))
        ):
            raise EvidenceError("事项版本证据步骤无效")
    return cases


def mark_effect(repo: Any, connection: Any, run: dict[str, Any], ident: str, sequence: int) -> None:
    previous = marker_cases(run) or {}
    cases = {key: list(values) for key, values in previous.items()}
    recorded = cases.setdefault(ident, [])
    if sequence in recorded or recorded and sequence <= recorded[-1] or len(recorded) >= MAX_WRITES:
        raise EvidenceError("事项版本证据不能重复或倒序补写")
    recorded.append(sequence)
    markers = dict(run["usage"].get(MARKER, {}))
    markers[str(run["retry_epoch"])] = {"schema": SCHEMA, "cases": cases}
    protocols = dict(run["usage"].get(PROTOCOL, {}), **{str(run["retry_epoch"]): SCHEMA})
    usage = dict(run["usage"], **{MARKER: markers, PROTOCOL: protocols})
    connection.execute(
        sql.SQL("UPDATE {} SET usage=%s WHERE owner=%s AND id=%s").format(repo.table("core_runs")),
        (Jsonb(usage), run["owner"], run["id"]),
    )
