"""Independent frozen v1 wire and strict validation acceptance, with no transport calls."""

import copy
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from mingjing_core.streaming.codec import decode_sse, encode_sse
from mingjing_core.streaming.event_errors import EventValidationError
from mingjing_core.streaming.event_models import (
    EventDraft,
    RunEvent,
    event_data,
    make_event,
)

FIXTURES = Path(__file__).parent / "fixtures"
ORIGINAL = json.loads((FIXTURES / "event_samples_expected_mod.json").read_bytes())
TRUTH = json.loads((FIXTURES / "event_samples_main_v1_mod.json").read_bytes())
SAMPLES = TRUTH["samples"]
AT = datetime(2026, 10, 20, 23, tzinfo=UTC)
SCHEMA_PATH = Path(__file__).parents[3] / "docs/v4/evidence/MOD_2026-10-21/events_v1.origin.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_bytes())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
REQUIRED = {
    "started": ("thread_id", "message_id", "incognito"),
    "status": ("text", "phase"),
    "tool_call": ("call_id", "name", "summary"),
    "tool_result": ("call_id", "name", "ok", "summary"),
    "text_delta": ("text",),
    "text_reset": ("text", "reason"),
    "memory_receipt": ("write_status", "summary", "sensitive"),
    "ask_user": ("ask_id", "question", "options", "allow_free_text", "multi", "why"),
    "present_options": ("options_id", "options"),
    "review": ("state", "reasons"),
    "final": ("message_id", "envelope"),
    "error": ("code", "message", "retryable"),
}


def sample(kind):
    return copy.deepcopy(next(item["payload"] for item in SAMPLES if item["type"] == kind))


def event(kind, payload=None, *, seq=1, **kwargs):
    return make_event(
        run_id="synthetic-run",
        seq=seq,
        ts=AT,
        type=kind,
        payload=sample(kind) if payload is None else payload,
        **kwargs,
    )


def frame(data, *, header_id="1", kind="text_delta"):
    return f"id: {header_id}\nevent: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def test_exact_mainline_schema_and_original_fixture_remain_frozen():
    assert hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest() == TRUTH["mainline_schema_sha256"]
    assert hashlib.sha256((FIXTURES / "event_samples_expected_mod.json").read_bytes()).hexdigest() == (
        "eb510c22da025048ccf8011ac4f47c544cb10683fbf47187e2c92844f0af3326"
    )
    Draft202012Validator.check_schema(SCHEMA)
    mismatches = []
    for index, item in enumerate(ORIGINAL["samples"]):
        wire = {
            "type": item["type"],
            "data": dict(
                v=1,
                run_id="synthetic-run",
                seq=index + 1,
                ts=ORIGINAL["timestamp"],
                **item["payload"],
            ),
        }
        if list(VALIDATOR.iter_errors(wire)):
            mismatches.append(index)
    assert mismatches == [
        3,
        13,
    ]  # Mainline refined receipt shape and uppercase error identifiers.


@pytest.mark.parametrize("index,item", list(enumerate(SAMPLES)))
def test_all_event_samples_match_mainline_schema_and_sse_roundtrip(index, item):
    original = copy.deepcopy(item["payload"])
    emitted = event(item["type"], original, seq=index + 1)
    data = event_data(emitted)
    assert data == dict(v=1, run_id="synthetic-run", seq=index + 1, ts=TRUTH["timestamp"], **original)
    VALIDATOR.validate({"type": emitted.type, "data": data})
    encoded = encode_sse(emitted)
    assert f"id: {index + 1}\n" in encoded and f"event: {item['type']}\n" in encoded
    assert decode_sse(encoded) == emitted
    assert decode_sse(encoded.encode("utf-8")) == emitted
    assert "synthetic-owner" not in encoded


@pytest.mark.parametrize("kind,key", [(kind, key) for kind, keys in REQUIRED.items() for key in keys])
def test_required_fields_are_not_silently_defaulted(kind, key):
    payload = sample(kind)
    del payload[key]
    with pytest.raises(EventValidationError):
        EventDraft(kind, payload)


@pytest.mark.parametrize("kind", list(REQUIRED))
def test_unknown_top_level_payload_fields_are_rejected(kind):
    payload = {**sample(kind), "private_trace": "synthetic-private-marker"}
    with pytest.raises(EventValidationError) as caught:
        EventDraft(kind, payload)
    assert "synthetic-private-marker" not in str(caught.value)


@pytest.mark.parametrize(
    "kind,field,value",
    [
        ("started", "incognito", "false"),
        ("status", "phase", "completed"),
        ("status", "text", 42),
        ("tool_result", "ok", 1),
        ("text_delta", "text", None),
        ("text_reset", "reason", "append"),
        ("memory_receipt", "write_status", "updated"),
        ("memory_receipt", "sensitive", "false"),
        ("ask_user", "multi", 0),
        ("ask_user", "allow_free_text", "true"),
        ("present_options", "options", []),
        ("review", "state", "failed"),
        ("error", "retryable", "true"),
        ("error", "code", "lowercase_error"),
    ],
)
def test_invalid_scalar_types_and_enums_are_rejected(kind, field, value):
    payload = sample(kind)
    payload[field] = value
    with pytest.raises(EventValidationError):
        EventDraft(kind, payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"summary": "合成", "write_status": "saved", "sensitive": False},
        {
            "summary": "合成",
            "write_status": "saved",
            "sensitive": False,
            "fact_id": "f",
            "proposal_id": "p",
        },
    ],
)
def test_receipt_identifies_exactly_one_fact_or_proposal(payload):
    with pytest.raises(EventValidationError):
        EventDraft("memory_receipt", payload)


@pytest.mark.parametrize("count", [0, 1, 5])
def test_decision_count_requires_two_to_four(count):
    payload = sample("present_options")
    payload["options"] = [{**payload["options"][0], "id": f"o{i}"} for i in range(count)]
    with pytest.raises(EventValidationError):
        EventDraft("present_options", payload)


@pytest.mark.parametrize("value", ["irreversible", None, True])
def test_nested_decision_reversibility_has_only_frozen_values(value):
    payload = sample("present_options")
    payload["options"][0]["reversibility"] = value
    with pytest.raises(EventValidationError):
        EventDraft("present_options", payload)


@pytest.mark.parametrize("severity", [0, 6, True, 2.5, "3"])
def test_review_severity_is_a_strict_integer_one_through_five(severity):
    with pytest.raises(EventValidationError):
        EventDraft(
            "review",
            {
                "state": "revised",
                "reasons": [{"code": "generic_barnum", "severity": severity}],
            },
        )


@pytest.mark.parametrize("code", ["generic_barnum", "sycophancy", "chart_inconsistency"])
def test_added_review_codes_are_valid_and_schema_compatible(code):
    emitted = event("review", {"state": "revised", "reasons": [{"code": code, "severity": 3}]})
    VALIDATOR.validate({"type": emitted.type, "data": event_data(emitted)})


@pytest.mark.parametrize(
    "field,value",
    [
        ("seq", 0),
        ("seq", -1),
        ("seq", True),
        ("seq", 1.5),
        ("v", True),
        ("v", 2),
        ("run_id", ""),
        ("run_id", "has space"),
        ("run_id", "../run"),
        ("run_id", "中文id"),
        ("run_id", "a" * 201),
        ("ts", datetime(2026, 10, 21)),
    ],
)
def test_event_common_metadata_is_strict(field, value):
    values = dict(
        run_id="synthetic-run",
        seq=1,
        ts=AT,
        type="text_delta",
        payload={"text": "合成"},
    )
    values[field] = value
    with pytest.raises(EventValidationError):
        RunEvent(**values)


def test_nested_event_payload_is_deeply_frozen_and_data_returns_a_copy():
    payload = sample("ask_user")
    emitted = event("ask_user", payload)
    payload["options"][0]["label"] = "外部后来改动"
    payload["options"].clear()
    assert event_data(emitted)["options"][0]["label"] == "先整理"
    with pytest.raises(TypeError):
        emitted.payload["options"][0]["label"] = "不能直接写入"
    returned = event_data(emitted)
    returned["options"][0]["label"] = "副本改动"
    assert event_data(emitted)["options"][0]["label"] == "先整理"


@pytest.mark.parametrize(
    "text",
    [
        "你好\n第二行",
        "🌙中文\r\n末尾",
        "id: 999\nevent: error\ndata: {}",
        '反斜线\\与引号"',
    ],
)
def test_unicode_and_line_breaks_cannot_inject_sse_headers(text):
    emitted = event("text_delta", {"text": text})
    encoded = encode_sse(emitted)
    assert len([line for line in encoded.splitlines() if line.startswith("id:")]) == 1
    assert decode_sse(encoded).payload["text"] == text


@pytest.mark.parametrize("duplicate", ["v", "run_id", "seq", "ts", "text"])
def test_duplicate_json_keys_are_rejected_even_if_values_agree(duplicate):
    data = event_data(event("text_delta"))
    raw = json.dumps(data, ensure_ascii=False)
    raw = "{" + json.dumps(duplicate) + ":" + json.dumps(data[duplicate]) + "," + raw[1:]
    with pytest.raises(EventValidationError):
        decode_sse("id: 1\nevent: text_delta\ndata: " + raw + "\n\n")


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_json_is_rejected_on_construction_and_decode(value):
    payload = sample("final")
    payload["envelope"]["usage"]["reported_tokens"] = {"input_tokens": value}
    with pytest.raises(EventValidationError):
        EventDraft("final", payload)
    data = dict(v=1, run_id="synthetic-run", seq=1, ts=TRUTH["timestamp"], **payload)
    with pytest.raises(EventValidationError):
        decode_sse(frame(data, kind="final"))


@pytest.mark.parametrize("change", ["header-id", "header-type", "data-version", "data-time", "extra"])
def test_sse_header_and_public_json_must_agree(change):
    data = event_data(event("text_delta"))
    header_id, kind = "1", "text_delta"
    if change == "header-id":
        header_id = "2"
    elif change == "header-type":
        kind = "status"
    elif change == "data-version":
        data["v"] = 2
    elif change == "data-time":
        data["ts"] = "2026-10-20T23:00:00+00:00"
    else:
        data["owner"] = "synthetic-owner"
    with pytest.raises(EventValidationError):
        decode_sse(frame(data, header_id=header_id, kind=kind))


def test_heartbeat_comment_is_not_an_event_and_unknown_type_is_rejected():
    assert decode_sse(": ping\n\n") is None
    with pytest.raises(EventValidationError):
        EventDraft("heartbeat", {})
