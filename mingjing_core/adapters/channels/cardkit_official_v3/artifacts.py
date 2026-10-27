"""Validate the actual outbound request against the exact current approved run/artifact."""

from typing import Any

from mingjing_core.adapters.channels.stream_outbox_v2 import FreshnessEvidence
from mingjing_core.adapters.channels.stream_outbox_v2.freshness import validate_freshness
from mingjing_core.streaming.json_values import json_object, thaw_json

from .contracts import ArtifactEvidence, OfficialError, OfficialRequest, OfficialState
from .wire import build_wire_request, wire_payload


def validate_artifact(
    state: OfficialState,
    request: OfficialRequest,
    artifact: ArtifactEvidence,
    evidence: FreshnessEvidence,
    purpose: str,
    now: Any,
) -> None:
    if not isinstance(evidence, FreshnessEvidence):
        raise OfficialError("trusted_freshness_evidence_required")
    if not isinstance(artifact, ArtifactEvidence) or artifact.scope != state.scope:
        raise OfficialError("artifact_scope_mismatch")
    if artifact.fingerprint != state.artifact_fingerprint:
        raise OfficialError("artifact_revision_or_content_changed")
    if not isinstance(request, OfficialRequest) or state.operation is None:
        raise OfficialError("request_required")
    if (request.operation_id, request.fingerprint, request.kind, request.sequence) != (
        state.operation.operation_id,
        state.operation.payload_fingerprint,
        state.operation.kind,
        state.operation.sequence,
    ):
        raise OfficialError("actual_request_changed")
    if evidence.run_payload_fingerprint != artifact.run_payload_fingerprint:
        raise OfficialError("artifact_run_payload_mismatch")
    validate_freshness(state.lease_state, evidence, purpose, now)
    rebuilt = build_wire_request(
        state,
        request.kind,
        wire_payload(request),
        operation_id=request.operation_id,
        sequence=request.sequence,
        artifact=artifact,
        element_id=_element(request),
    )
    if rebuilt != request:
        raise OfficialError("request_protocol_mismatch")
    raw = json_object(evidence.validated_payload)
    approved_text = raw.get("text") if raw.get("schema") == "core4.0" else raw.get("answer")
    if type(approved_text) is not str or not approved_text:
        raise OfficialError("approved_run_text_required")
    if request.kind == "update" and not approved_text.startswith(request.body["content"]):
        raise OfficialError("wire_text_not_validated_run_prefix")
    if request.kind == "finalize":
        _answer_binding(thaw_json(artifact.final_card), approved_text)


def _element(request: OfficialRequest) -> str:
    return request.path.split("/")[-2] if request.kind == "update" else "answer"


def _answer_binding(card: dict, approved_text: str) -> None:
    rows = _components(card.get("body", {}).get("elements", []))
    answers = [row.get("content") for row in rows if row.get("element_id") in {"answer", "answer_full"}]
    if not answers:
        raise OfficialError("final_answer_component_required")
    for answer in answers:
        if type(answer) is not str:
            raise OfficialError("final_answer_text_invalid")
        if answer == approved_text:
            continue
        notice = "\n（内容已缩略，完整内容见明镜台）"
        prefix = answer[: -len(notice)] if answer.endswith(notice) else ""
        if not prefix or not approved_text.startswith(prefix):
            raise OfficialError("final_card_text_not_validated_run")


def _components(rows: list[dict]) -> list[dict]:
    result = []
    for row in rows:
        result.append(row)
        if isinstance(row.get("elements"), list):
            result.extend(_components(row["elements"]))
    return result
