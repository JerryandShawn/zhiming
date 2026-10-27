"""Transport corruption and historical read boundaries, independent of the encoder's round trip."""

import json
from copy import deepcopy
from typing import Any

import pytest

from mingjing_core.streaming.codec import decode_sse, encode_sse, event_from_data
from mingjing_core.streaming.envelope_reader import read_envelope
from mingjing_core.streaming.event_errors import EventValidationError
from mingjing_core.streaming.event_models import EventDraft, event_data
from mingjing_core.streaming.json_values import json_object
from tests.v4.streaming.coverage_support_acceptance_mod import event, sample


def wire() -> dict[str, Any]:
    return {"v": 1, "run_id": "boundary-run", "seq": 7, "ts": "2026-10-21T08:52:00+08:00", "text": "虚构🌙\n第二行"}


@pytest.mark.parametrize(
    "frame",
    [
        "id: 7\nevent: text_delta\ndata: {}\n",
        ": ping\n\n: ping\n\n",
        "id: 7\nretry: 1000\nevent: text_delta\ndata: {}\n\n",
        "id: 7\nid: 7\nevent: text_delta\ndata: {}\n\n",
        "id: 7\nevent: text_delta\nevent: text_delta\ndata: {}\n\n",
        "id: 7\nevent: text_delta\ndata\n\n",
        "event: text_delta\ndata: {}\n\n",
        "id: 7\ndata: {}\n\n",
        "id: 7\nevent: text_delta\n\n",
        "id: ７\nevent: text_delta\ndata: {}\n\n",
        "id: 07\nevent: text_delta\ndata: {}\n\n",
        b"\xff\n\n",
        None,
    ],
)
def test_incomplete_duplicate_or_malformed_transport_never_emits_a_partial_event(frame: object) -> None:
    with pytest.raises(EventValidationError) as caught:
        decode_sse(frame)
    assert "虚构" not in str(caught.value)


def test_multiline_json_crlf_and_comments_reconstruct_exact_text() -> None:
    lines = json.dumps(wire(), ensure_ascii=False, indent=2).splitlines()
    frame = "\r\n".join([": intermediary", "id:7", "event:text_delta", *[f"data:{line}" for line in lines], "", ""])
    decoded = decode_sse(frame.encode("utf-8"))
    assert decoded is not None and decoded.seq == 7 and decoded.payload["text"] == "虚构🌙\n第二行"
    assert decode_sse(": intermediary\r\n\r\n") is None


@pytest.mark.parametrize(
    "mutation",
    [
        {"ts": 1},
        {"ts": "2026-13-21T08:52:00+08:00"},
        {"ts": "2026-10-21T08:52:00Z"},
        {"ts": "2026-10-21T08:52:00+09:00"},
        {"v": True},
        {"v": 2},
        {"seq": True},
        {"seq": 8},
        {"owner_id": "private-owner"},
    ],
)
def test_wire_identity_timestamp_and_private_extra_fields_are_not_coerced(mutation: dict[str, object]) -> None:
    value = wire() | mutation
    with pytest.raises(EventValidationError):
        event_from_data("text_delta", value, expected_seq=7)


@pytest.mark.parametrize("data", [[], None, "private", 7, {}, {"v": 1, "seq": 7, "ts": "x"}])
def test_sse_data_requires_complete_public_object(data: object) -> None:
    with pytest.raises(EventValidationError):
        event_from_data("text_delta", data)


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity"])
def test_json_nonfinite_numbers_are_rejected_before_model_coercion(number: str) -> None:
    frame = f'id: 7\nevent: text_delta\ndata: {json.dumps(wire())[:-1]},"extra":{number}}}\n\n'
    with pytest.raises(EventValidationError) as caught:
        decode_sse(frame)
    assert caught.value.reason_code == "json_number_invalid"


def test_nested_duplicate_json_keys_cannot_change_a_question_answer() -> None:
    data = {key: value for key, value in wire().items() if key != "text"} | sample("ask_user")
    value = json.dumps(data, ensure_ascii=False)
    first_option = data["options"][0]
    before = json.dumps(first_option, ensure_ascii=False)
    after = before[:-1] + ',"label":"虚构篡改"}'
    frame = f"id: 7\nevent: ask_user\ndata: {value.replace(before, after)}\n\n"
    with pytest.raises(EventValidationError) as caught:
        decode_sse(frame)
    assert caught.value.reason_code == "json_duplicate_key"


@pytest.mark.parametrize("value", [None, {}, "event"])
def test_encoder_and_public_projection_require_an_actual_validated_event(value: object) -> None:
    for convert in (encode_sse, event_data):
        with pytest.raises(EventValidationError) as caught:
            convert(value)
        assert caught.value.reason_code == "event_required"


def legacy() -> dict[str, Any]:
    return {"schema_version": "core3.0", "answer": "虚构历史回答", "validation": {"schema": "core3.0", "valid": True}}


@pytest.mark.parametrize(
    "mutation",
    [
        {"schema": "core3.0", "schema_version": "other"},
        {"answer": " "},
        {"answer": 1},
        {"validation": {"schema": "core3.0", "valid": 1}},
        {"validation": {"schema": "core4.0", "valid": True}},
        {"message_id": 123},
    ],
)
def test_historical_core3_marker_and_validation_are_required_not_just_an_answer(mutation: dict[str, Any]) -> None:
    with pytest.raises(EventValidationError):
        read_envelope(legacy() | mutation)


def test_valid_historical_core3_is_a_deep_frozen_read_without_delivery_authority() -> None:
    value = legacy() | {"message_id": "old-message", "receipt": {"status": "history-only"}}
    result = read_envelope(value)
    value["receipt"]["status"] = "mutated"
    assert result.schema == "core3.0" and result.text == "虚构历史回答" and result.message_id == "old-message"
    assert result.payload["receipt"]["status"] == "history-only"
    with pytest.raises(TypeError):
        result.payload["receipt"]["status"] = "forged"
    with pytest.raises(EventValidationError):
        EventDraft("final", {"message_id": "old-message", "envelope": legacy()})


def test_bad_core4_or_unknown_historical_envelope_never_gets_a_read_receipt() -> None:
    value = deepcopy(sample("final")["envelope"])
    value["text"] = 7
    with pytest.raises(EventValidationError) as caught:
        read_envelope(value)
    assert caught.value.reason_code == "core4_envelope_invalid"
    with pytest.raises(EventValidationError) as caught:
        read_envelope({"schema": "core5.0", "text": "虚构"})
    assert caught.value.reason_code == "envelope_version_unknown"
    assert read_envelope(sample("final")["envelope"]).schema == "core4.0"


def test_cyclic_or_nonobject_json_cannot_be_used_as_a_payload() -> None:
    cycle: dict[str, Any] = {}
    cycle["child"] = cycle
    with pytest.raises(EventValidationError) as caught:
        json_object(cycle)
    assert caught.value.reason_code == "json_nesting_invalid"
    with pytest.raises(EventValidationError) as caught:
        json_object(["not-an-object"])
    assert caught.value.reason_code == "json_object_required"
    assert decode_sse(encode_sse(event("text_delta"))) is not None
