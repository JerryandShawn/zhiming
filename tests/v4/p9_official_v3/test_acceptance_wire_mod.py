"""Independent 26 §8 wire/limit/error expectations, frozen before these tests."""

import hashlib
import json
import random
from pathlib import Path

import pytest

from mingjing_core.adapters.channels.card_limits_official_v3 import (
    validate_card_id,
    validate_element_id,
    validate_sequence,
    wire_uuid,
)
from mingjing_core.adapters.channels.cardkit_official_v3 import (
    classify_response,
    new_state,
    prepare_operation,
    request_data,
)

from .support_mod import TEXT, acknowledge, dispatch, environment, open_stream, prepare, run_step

MATRIX_PATH = Path(__file__).with_name("fixtures") / "expected_contract_mod.json"
MATRIX = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
CASES = MATRIX["cases"]


def selected(prefix: str) -> list[dict]:
    return [case for case in CASES if case["id"].startswith(prefix)]


def test_normative_fixture_is_still_exactly_frozen() -> None:
    manifest = json.loads(MATRIX_PATH.with_name("expected_contract_mod.manifest.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(MATRIX_PATH.read_bytes()).hexdigest() == manifest["fixture_sha256"]
    assert len(CASES) == manifest["case_count"] == 184
    assert all(MATRIX["checklist_8_coverage"][str(i)] for i in range(1, 12))
    assert len(manifest["section_7_exact_ten_stage_ids"]) == 10


@pytest.mark.parametrize("case", selected("ELEMENT_ID_"), ids=lambda case: case["id"])
def test_element_id_official_regex(case: dict) -> None:
    value = case["given"]["element_id"]
    if case["expected"]["valid"]:
        assert validate_element_id(value) == value
    else:
        with pytest.raises(ValueError):
            validate_element_id(value)


@pytest.mark.parametrize("case", selected("CARD_ID_LENGTH_"), ids=lambda case: case["id"])
def test_card_id_official_length(case: dict) -> None:
    value = case["given"]["card_id"]
    if case["expected"]["valid"]:
        assert validate_card_id(value) == value
    else:
        with pytest.raises(ValueError):
            validate_card_id(value)


@pytest.mark.parametrize("case", selected("SEQUENCE_TYPE_") + selected("SEQUENCE_FLOAT_"), ids=lambda case: case["id"])
def test_sequence_real_int32(case: dict) -> None:
    value = float(case["given"]["value"]) if case["id"] == "SEQUENCE_FLOAT_ONE" else case["given"]["value"]
    if case["expected"]["valid"]:
        assert validate_sequence(value) == value
    else:
        with pytest.raises(ValueError):
            validate_sequence(value)


@pytest.mark.parametrize("case", selected("ERROR_CODE_"), ids=lambda case: case["id"])
def test_documented_errors_have_exact_semantics(case: dict) -> None:
    outcome = classify_response(400, case["given"]["code"])
    expected = case["expected"]["outcome"]
    assert outcome.status == ("uncertain" if expected == "unknown" else expected)


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_5xx_remains_unknown(status: int) -> None:
    assert classify_response(status, 10002).status == "uncertain"


def test_network_unknown_and_rate_delay_seconds() -> None:
    assert classify_response(None, None, network_error=True).status == "uncertain"
    assert classify_response(400, 987654321).status == "uncertain"
    for status, code in [(429, 0), (400, 99991400)]:
        result = classify_response(status, code, {"x-ogw-ratelimit-reset": "3"})
        assert result.status == "retryable" and result.after_ms == 3000


@pytest.mark.parametrize("code", [200850, 300309])
def test_timeout_and_closed_stream_require_explicit_host_decision(code: int) -> None:
    outcome = classify_response(400, code)
    assert outcome.status == "retryable"
    assert outcome.action_required == "reopen_or_finalize"


def test_wire_uuid_is_full_operation_sha256_prefix() -> None:
    for operation_id in ["synthetic-one", "cardkit:" + "0" * 64 + ":finalize", "合成操作号"]:
        expected = hashlib.sha256(operation_id.encode("utf-8")).hexdigest()[:40]
        assert wire_uuid(operation_id) == expected
        assert len(expected) == 40


def test_1000_synthetic_operation_identifiers_and_real_int32_values() -> None:
    rng = random.Random(261008)
    for _ in range(1000):
        value = rng.randrange(1, 2147483648)
        operation_id = f"synthetic-independent-{rng.getrandbits(256):064x}"
        assert validate_sequence(value) == value
        assert wire_uuid(operation_id) == hashlib.sha256(operation_id.encode("utf-8")).hexdigest()[:40]


def test_create_and_send_have_distinct_official_wire_shapes_and_no_sequence() -> None:
    env = environment()
    created = prepare(new_state(env.scope), env, "create")
    first = request_data(created.request)
    assert first["method"] == "POST" and first["path"] == "/open-apis/cardkit/v1/cards"
    assert set(first["body"]) == {"type", "data"} and first["body"]["type"] == "card_json"
    card = json.loads(first["body"]["data"])
    assert card["schema"] == "2.0" and card["config"]["update_multi"] is True
    assert card["config"]["streaming_mode"] is True
    assert card["body"]["elements"][0]["content"]
    state = acknowledge(dispatch(created, env), env)
    sent = prepare(state, env, "send")
    second = request_data(sent.request)
    assert second["method"] == "POST" and second["path"] == "/open-apis/im/v1/messages"
    assert second["query"] == {"receive_id_type": "open_id"}
    assert second["body"]["receive_id"] == env.scope.target
    assert second["body"]["msg_type"] == "interactive"
    assert json.loads(second["body"]["content"]) == {"type": "card", "data": {"card_id": "12345"}}
    assert "sequence" not in second["body"] and sent.request.sequence is None
    assert len(second["body"]["uuid"]) == 40


def test_send_content_and_two_close_requests_follow_official_wire() -> None:
    env = environment()
    state = open_stream(env)
    update = prepare(state, env, "update", TEXT)
    request = request_data(update.request)
    assert request["method"] == "PUT"
    assert request["path"] == "/open-apis/cardkit/v1/cards/12345/elements/answer/content"
    assert request["body"]["content"] == TEXT and request["body"]["sequence"] == 1
    state = run_step(state, env, "update", TEXT)
    finalize = prepare(state, env, "finalize", env.artifact.final_card)
    first = request_data(finalize.request)
    assert first["method"] == "PUT" and first["path"] == "/open-apis/cardkit/v1/cards/12345"
    assert json.loads(first["body"]["card"]["data"])["schema"] == "2.0"
    assert first["body"]["card"]["type"] == "card_json"
    state = run_step(state, env, "finalize", env.artifact.final_card)
    close = prepare(state, env, "close_streaming")
    second = request_data(close.request)
    assert second["method"] == "PATCH" and second["path"].endswith("/settings")
    assert json.loads(second["body"]["settings"]) == {
        "config": {"streaming_mode": False, "summary": {"content": "合成最终摘要"}}
    }
    assert second["body"]["sequence"] == first["body"]["sequence"] + 1
    assert second["body"]["uuid"] != first["body"]["uuid"]


def test_empty_update_or_reset_is_noop_and_consumes_no_sequence() -> None:
    env = environment()
    state = open_stream(env)
    for operation_id in ["synthetic-empty-offer", "synthetic-empty-reset"]:
        result = prepare_operation(
            state, "update", "", operation_id=operation_id, artifact=env.artifact, clock=env.clock
        )
        assert result.status == "noop_empty" and result.request is None
        assert result.state == state and result.state.last_reserved_sequence == 0
