"""The complete approved run must authorize the exact outbound card, at both send boundaries."""

from dataclasses import replace
from datetime import timedelta

import pytest

from mingjing_core.adapters.channels.cardkit_contracts import fingerprint
from mingjing_core.adapters.channels.cardkit_official_v3 import (
    ArtifactEvidence,
    OfficialError,
    begin_dispatch,
    claim,
)
from mingjing_core.adapters.channels.cardkit_official_v3.artifacts import validate_artifact
from mingjing_core.streaming.json_values import thaw_json

from .isolated_coverage_mod import isolated_p9 as isolated_p9
from .support_mod import TEXT, TOKEN, Environment, environment, freshness, open_stream, prepare


def boundary_inputs(boundary: str, *, final: bool = False, env: Environment | None = None) -> tuple:
    env = environment() if env is None else env
    prepared = prepare(
        open_stream(env), env, "finalize" if final else "update", env.artifact.final_card if final else TEXT[:5]
    )
    state = prepared.state
    if boundary == "dispatch":
        state = claim(
            state,
            prepared.request,
            artifact=env.artifact,
            evidence=freshness(state, env, "claim"),
            token=TOKEN,
            worker_id="synthetic-worker",
            clock=env.clock,
            ttl=timedelta(seconds=30),
            expected_revision=state.revision,
        )
    return env, state, prepared.request


def invoke(
    boundary: str, env: Environment, state: object, request: object, *, artifact: object = None, evidence: object = None
) -> object:
    arguments = {
        "artifact": env.artifact if artifact is None else artifact,
        "evidence": freshness(state, env, boundary) if evidence is None else evidence,
        "token": TOKEN,
        "clock": env.clock,
        "expected_revision": state.revision,
    }
    if boundary == "claim":
        return claim(state, request, worker_id="synthetic-worker", ttl=timedelta(seconds=30), **arguments)
    return begin_dispatch(state, request, fence=state.lease_state.fence, **arguments)


@pytest.mark.parametrize("boundary", ["claim", "dispatch"])
@pytest.mark.parametrize("field", tuple(environment().scope.__dataclass_fields__))
def test_artifact_cannot_reuse_another_one_of_seven_scope_bindings(boundary: str, field: str) -> None:
    env, state, request = boundary_inputs(boundary)
    artifact = replace(env.artifact, scope=replace(env.scope, **{field: "synthetic-foreign-scope"}))
    with pytest.raises(OfficialError) as caught:
        invoke(boundary, env, state, request, artifact=artifact)
    assert caught.value.reason_code == "artifact_scope_mismatch"


@pytest.mark.parametrize("boundary", ["claim", "dispatch"])
def test_artifact_revision_changes_after_prepare_are_rejected_even_with_the_same_text(boundary: str) -> None:
    env, state, request = boundary_inputs(boundary)
    artifact = replace(env.artifact, revision=env.artifact.revision + 1)
    with pytest.raises(OfficialError) as caught:
        invoke(boundary, env, state, request, artifact=artifact)
    assert caught.value.reason_code == "artifact_revision_or_content_changed"


@pytest.mark.parametrize("boundary", ["claim", "dispatch"])
def test_artifact_and_freshness_must_bind_the_same_complete_run_body(boundary: str) -> None:
    env, state, request = boundary_inputs(boundary)
    artifact = replace(env.artifact, run_payload_fingerprint="e" * 64)
    state = replace(state, artifact_fingerprint=artifact.fingerprint)
    with pytest.raises(OfficialError) as caught:
        invoke(boundary, env, state, request, artifact=artifact)
    assert caught.value.reason_code == "artifact_run_payload_mismatch"


@pytest.mark.parametrize("boundary", ["claim", "dispatch"])
@pytest.mark.parametrize("field", ["method", "path", "query"])
def test_self_consistent_request_fingerprints_do_not_authorize_a_different_wire_protocol(
    boundary: str, field: str
) -> None:
    env, state, request = boundary_inputs(boundary)
    changed = {
        "method": "PATCH",
        "path": "/open-apis/cardkit/v1/cards/67890/elements/answer/content",
        "query": {"unapproved_target_override": "synthetic"},
    }[field]
    request = replace(request, **{field: changed})
    operation = replace(state.operation, payload_fingerprint=request.fingerprint)
    inner = replace(
        state.lease_state, intent=replace(state.lease_state.intent, payload_fingerprint=request.fingerprint)
    )
    state = replace(state, operation=operation, lease_state=inner)
    with pytest.raises(OfficialError) as caught:
        invoke(boundary, env, state, request)
    assert caught.value.reason_code == "request_protocol_mismatch"


@pytest.mark.parametrize("boundary", ["claim", "dispatch"])
def test_update_payload_must_be_a_prefix_of_the_approved_run_and_not_just_any_valid_card_text(boundary: str) -> None:
    env = environment()
    prepared = prepare(open_stream(env), env, "update", "SYNTHETIC_UNAPPROVED_CARD_BODY")
    with pytest.raises(OfficialError) as caught:
        validate_artifact(
            prepared.state,
            prepared.request,
            env.artifact,
            freshness(prepared.state, env, boundary),
            boundary,
            env.clock.now(),
        )
    assert caught.value.reason_code == "wire_text_not_validated_run_prefix"
    assert "SYNTHETIC_UNAPPROVED" not in str(caught.value)


@pytest.mark.parametrize("variant", ["absent", "wrong", "prefix_without_notice", "empty_prefix_notice", "nontext"])
def test_full_final_card_must_contain_the_exact_answer_or_an_explicit_bound_truncation(variant: str) -> None:
    env = environment()
    card = thaw_json(env.artifact.final_card)
    row = card["body"]["elements"][0]
    if variant == "absent":
        row["element_id"] = "unrelated_note"
    elif variant == "wrong":
        row["content"] = "SYNTHETIC_UNAPPROVED_FINAL_BODY"
    elif variant == "prefix_without_notice":
        row["content"] = TEXT[:5]
    elif variant == "empty_prefix_notice":
        row["content"] = "\n（内容已缩略，完整内容见明镜台）"
    else:
        card["body"]["elements"] = [
            {
                "tag": "collapsible_panel",
                "element_id": "answer",
                "expanded": False,
                "header": {"title": {"tag": "plain_text", "content": "合成详情"}},
                "elements": [{"tag": "markdown", "element_id": "unrelated_note", "content": TEXT}],
            }
        ]
    env = replace(env, artifact=ArtifactEvidence(env.scope, fingerprint(env.payload), 2, card))
    env, state, request = boundary_inputs("claim", final=True, env=env)
    with pytest.raises(OfficialError) as caught:
        invoke("claim", env, state, request)
    assert caught.value.reason_code in {
        "final_answer_component_required",
        "final_answer_text_invalid",
        "final_card_text_not_validated_run",
    }


@pytest.mark.parametrize("nested", [False, True])
def test_authorized_explicit_truncation_and_nested_answer_are_accepted_without_changing_the_run(nested: bool) -> None:
    env = environment()
    card = thaw_json(env.artifact.final_card)
    row = card["body"]["elements"][0]
    row["content"] = TEXT[:5] + "\n（内容已缩略，完整内容见明镜台）"
    if nested:
        card["body"]["elements"] = [
            {
                "tag": "collapsible_panel",
                "element_id": "details",
                "expanded": False,
                "header": {"title": {"tag": "plain_text", "content": "合成详情"}},
                "elements": [row],
            }
        ]
    env = replace(env, artifact=ArtifactEvidence(env.scope, fingerprint(env.payload), 2, card))
    env, state, request = boundary_inputs("claim", final=True, env=env)
    result = invoke("claim", env, state, request)
    assert result.phase == "leased" and result.card_id == state.card_id
    assert env.payload["text"] == TEXT


@pytest.mark.parametrize("malformed", [None, {}, True])
def test_boolean_or_raw_mapping_is_not_current_freshness_evidence(malformed: object) -> None:
    env, state, request = boundary_inputs("claim")
    with pytest.raises(OfficialError) as caught:
        validate_artifact(state, request, env.artifact, malformed, "claim", env.clock.now())
    assert caught.value.reason_code == "trusted_freshness_evidence_required"


def test_missing_request_and_wrong_artifact_type_are_rejected_without_revealing_body() -> None:
    env, state, request = boundary_inputs("claim")
    evidence = freshness(state, env, "claim")
    for request_value, artifact_value in ((None, env.artifact), (request, {"revision": 1})):
        with pytest.raises(OfficialError) as caught:
            validate_artifact(state, request_value, artifact_value, evidence, "claim", env.clock.now())
        assert TEXT not in str(caught.value)
