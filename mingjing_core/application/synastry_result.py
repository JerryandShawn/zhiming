"""Attest an ephemeral result from this process's own isolated P8 invocation."""

from copy import deepcopy

from mingjing_core.adapters.charts.tool_evidence import content_hash
from mingjing_core.application.charts_documents import _rule_paths
from mingjing_core.application.agent_tools_contracts import ToolResult
from mingjing_core.agent.tools.p8_parameters import Synastry
from mingjing_core.domain.contracts import CoreError, EvidenceError
from mingjing_core.domain.json_values import ensure_finite_json
from mingjing_core.repositories.postgres import fingerprint


def verify_synastry(payload: dict, owner: str, snapshots: list[dict], operation: str, kind: str) -> None:
    ensure_finite_json(payload)
    expected = {
        "owner_user_id": owner,
        "subject_ids": [row["subject_id"] for row in snapshots],
        "revisions": [row["revision"] for row in snapshots],
        "operation_ids": [operation, operation],
    }
    if payload.get("version") != "p8-synastry-v1" or fingerprint(payload.get("scope")) != fingerprint(expected):
        raise EvidenceError("合盘产物归属、修订或版本不符")
    root = {key: payload[key] for key in ("version", "scope", "data", "rule_hits", "sources")}
    if payload.get("document_id") != "tool-" + content_hash(root):
        raise EvidenceError("合盘产物内容摘要不符")
    if payload["data"].get("kind") != kind or payload["data"].get("consent") != "user_confirmed":
        raise EvidenceError("合盘产物用途或授权不符")
    if not isinstance(payload.get("rule_hits"), list) or not payload.get("sources"):
        raise EvidenceError("合盘产物缺少原生依据")
    effects = payload.get("effects", {})
    if any(type(effects.get(key)) is not int or effects[key] != 0 for key in ("model_calls", "writes")):
        raise EvidenceError("合盘产物不能声明模型请求或长期写入")
    for hit in payload["rule_hits"]:
        _rule_paths(payload, hit)


def project_synastry(data: dict) -> dict:
    """Do not inject the second person's birth instants or private authority record."""
    native = data["calculation"]
    visible = deepcopy({key: native["data"][key] for key in ("kind", "bazi", "astro", "ziwei", "methods")})
    visible["astro"].pop("natal_at_utc", None)
    return {
        "adapter_mode": "p8_synastry_transient",
        "comparison": visible,
        "limits": native["limits"],
        "record_policy": {"memory": False, "profile": False, "reflection": False, "forward": False},
        "alias_registration": "not_registered",
        "reference_policy": "native_step_verified_no_reference_aliases",
    }


def verify_cached_synastry(row, ctx, service, consent):
    """A matching journal/cache is insufficient if its native payload is corrupt."""
    try:
        result = ToolResult.model_validate(row["tool_output"])
        if not result.ok:
            return result
        args = Synastry.model_validate(row["arguments"]).model_dump()
        if (
            not consent
            or (consent["subject_a"], consent["subject_b"], consent["comparison_kind"])
            != (ctx.subject, args["other_subject_id"], args["kind"])
            or consent["state"] != "consumed"
            or type(consent["uses_left"]) is not int
            or consent["uses_left"] != 0
            or consent.get("consumed_by") != ctx.operation_id
            or result.receipt is not None
            or result.ends_turn
            or set(result.data) != {"adapter_mode", "calculation", "record_policy"}
            or result.data["adapter_mode"] != "p8_synastry_transient"
            or fingerprint(result.data["record_policy"])
            != fingerprint({"memory": False, "profile": False, "reflection": False})
        ):
            raise EvidenceError("原合盘缓存的用途、授权或临时保存策略不符")
        snapshots = service._pair(ctx.owner, ctx.subject, args["other_subject_id"], ctx.operation_id)
        if fingerprint(row["snapshots"]) != fingerprint(snapshots):
            raise EvidenceError("原合盘缓存与双方当前授权资料不符")
        verify_synastry(result.data["calculation"], ctx.owner, snapshots, ctx.operation_id, args["kind"])
        return result
    except CoreError:
        raise
    except (ValueError, KeyError, TypeError):
        raise EvidenceError("原合盘缓存结构已失效，不能采用旧结果") from None
