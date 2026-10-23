"""Synthetic codec and strict-contract checks against the frozen mainline schema."""

import json
import random
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from mingjing_core.streaming.codec import decode_sse, encode_sse, event_from_data
from mingjing_core.streaming.envelope_reader import read_envelope
from mingjing_core.streaming.event_errors import EventValidationError
from mingjing_core.streaming.event_models import EventDraft, RunEvent, RunScope, event_data, make_event

AT = datetime(2026, 10, 20, 18, tzinfo=UTC)
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "docs/v4/evidence/MOD_2026-10-21/events_v1.origin.schema.json"
SCHEMA = Draft202012Validator(json.loads(SCHEMA_PATH.read_text("utf-8")), format_checker=FormatChecker())


def options():
    base = {
        "title": "先观察",
        "benefit": "补信息",
        "cost": "时间",
        "risk": "仍有未知",
        "reversibility": "easy",
        "first_step": "列问题",
        "unknowns": ["结果待确认"],
    }
    return {"options_id": "options-1", "options": [{**base, "id": "first"}, {**base, "id": "second"}]}


def envelope():
    return {
        "schema": "core4.0",
        "message_id": "message-1",
        "text": "合成回答",
        "receipts": [],
        "used_fact_ids": [],
        "used_claim_ids": [],
        "asked": None,
        "options": None,
        "review": {"state": "skipped", "reasons": []},
        "usage": {},
    }


def payloads():
    return {
        "started": {"thread_id": "life:self", "message_id": "message-1", "incognito": False},
        "status": {"text": "正在思考", "phase": "thinking"},
        "tool_call": {"call_id": "call-1", "name": "memory_search", "summary": "查找已授权的记录"},
        "tool_result": {
            "call_id": "call-1",
            "name": "memory_write",
            "ok": True,
            "summary": "完成",
            "receipt": {"write_status": "saved", "fact_id": "fact-1", "revision": 1},
        },
        "text_delta": {"text": "合成增量\n下一行"},
        "text_reset": {"text": "", "reason": "resumed"},
        "memory_receipt": {"fact_id": "fact-1", "write_status": "saved", "summary": "已记住", "sensitive": False},
        "ask_user": {
            "ask_id": "ask-1",
            "question": "哪一个？",
            "options": [{"id": "first", "label": "先观察"}],
            "allow_free_text": True,
            "multi": False,
            "why": "确认你的选择",
        },
        "present_options": options(),
        "review": {"state": "revised", "reasons": [{"code": "generic_barnum", "severity": 3}], "revision_id": "rev-1"},
        "final": {"message_id": "message-1", "envelope": envelope()},
        "error": {"code": "OFFLINE", "message": "暂时无法继续，请稍后再试", "retryable": True},
    }


@pytest.mark.parametrize("event_type", list(payloads()))
def test_each_event_roundtrips_and_matches_fetched_mainline_schema(event_type):
    event = make_event(run_id="run-1", seq=1, ts=AT, type=event_type, payload=payloads()[event_type])
    SCHEMA.validate({"type": event.type, "data": event_data(event)})
    wire = encode_sse(event)
    assert decode_sse(wire) == event
    assert decode_sse(wire.encode("utf-8")) == event
    assert event_data(event)["ts"] == "2026-10-21T02:00:00+08:00"
    assert "owner_id" not in event_data(event)


@pytest.mark.parametrize("value", [True, False, "1", 1.0, 0, -1])
def test_sequence_is_positive_strict_integer(value):
    with pytest.raises(EventValidationError):
        RunEvent("run-1", value, AT, "text_delta", {"text": "合成"})


@pytest.mark.parametrize("value", [True, "1", 1.0, 0, 2])
def test_version_is_exact_integer_one(value):
    with pytest.raises(EventValidationError):
        RunEvent("run-1", 1, AT, "text_delta", {"text": "合成"}, v=value)


@pytest.mark.parametrize("event_type", list(payloads()))
def test_unknown_top_level_payload_keys_are_forbidden(event_type):
    payload = {**payloads()[event_type], "private_trace": "合成隐私"}
    with pytest.raises(EventValidationError) as caught:
        EventDraft(event_type, payload)
    assert "合成隐私" not in str(caught.value)


def test_nested_structures_are_deeply_frozen_and_wire_is_an_independent_copy():
    raw = options()
    event = make_event(run_id="run-1", seq=1, ts=AT, type="present_options", payload=raw)
    raw["options"][0]["unknowns"].append("后来改变")
    with pytest.raises(TypeError):
        event.payload["options"][0]["title"] = "不能修改"
    projected = event_data(event)
    projected["options"][0]["unknowns"].append("客户端改变")
    assert event.payload["options"][0]["unknowns"] == ("结果待确认",)
    assert "先观察" not in repr(event)


@pytest.mark.parametrize("target", [{}, {"fact_id": "a", "proposal_id": "b"}, {"fact_id": ""}])
def test_memory_receipt_requires_exactly_one_valid_target(target):
    with pytest.raises(EventValidationError):
        EventDraft("memory_receipt", {**target, "write_status": "saved", "summary": "合成", "sensitive": False})


@pytest.mark.parametrize("counter", [True, -1, "1", 1.5])
def test_nested_public_usage_counters_are_strict_nonnegative(counter):
    data = envelope()
    data["usage"] = {"reported_tokens": {"input_tokens": counter}}
    with pytest.raises(EventValidationError):
        EventDraft("final", {"message_id": "message-1", "envelope": data})


def test_public_usage_allowlist_and_legacy_fields_match_mainline_schema():
    data = envelope()
    data.update(
        schema_version="core4.0",
        answer=data["text"],
        validation={"status": "validated", "valid": True, "schema": "core4.0"},
        meta={
            "core_run": {"run_id": "run-1", "operation_id": "operation-1"},
            "subject_id": "self",
            "case_ids": [],
            "structural_warnings": [{"code": "CODE", "count": 1}],
        },
    )
    data["usage"] = {
        "reported_tokens": {"input_tokens": 20, "output_tokens": 3},
        "usage_known": True,
        "model_steps": 1,
        "model_streams_this_execution": 1,
        "replayed_model_steps": 0,
        "offline": True,
    }
    data["receipts"] = [{"write_status": "updated", "affected_ids": ["fact-1"], "revision": 2}]
    event = make_event(
        run_id="run-1", seq=1, ts=AT, type="final", payload={"message_id": "message-1", "envelope": data}
    )
    SCHEMA.validate({"type": "final", "data": event_data(event)})
    assert read_envelope(data).schema == "core4.0"
    data["usage"]["private_trace"] = "禁止公开"
    with pytest.raises(EventValidationError):
        EventDraft("final", {"message_id": "message-1", "envelope": data})


@pytest.mark.parametrize("patch", [{"message_id": "other"}, {"schema": "core3.0"}])
def test_final_rejects_mismatched_or_old_envelope(patch):
    data = {**envelope(), **patch}
    with pytest.raises(EventValidationError):
        EventDraft("final", {"message_id": "message-1", "envelope": data})


@pytest.mark.parametrize("kind", ["private_kind", "text_delta\nevent: error"])
def test_unknown_event_type_cannot_inject_sse(kind):
    with pytest.raises(EventValidationError):
        EventDraft(kind, {"text": "合成"})


@pytest.mark.parametrize(
    "timestamp",
    ["2026-10-21 02:00:00+08:00", "2026-10-21T02:00:00+0800", "2026-10-21T02:00:00Z", "2026-10-21T03:00:00+09:00"],
)
def test_wire_timestamp_requires_exact_shanghai_format(timestamp):
    data = {"v": 1, "run_id": "run-1", "seq": 1, "ts": timestamp, "text": "合成"}
    with pytest.raises(EventValidationError):
        event_from_data("text_delta", data)


def test_naive_time_and_invalid_identifiers_are_rejected():
    with pytest.raises(EventValidationError):
        RunEvent("run-1", 1, AT.replace(tzinfo=None), "text_delta", {"text": "合成"})
    with pytest.raises(EventValidationError):
        RunScope("owner-1", "运行1")
    event = RunEvent("run-1", 1, AT.astimezone(timezone(timedelta(hours=9))), "text_delta", {"text": "合成"})
    assert event.ts == AT


@pytest.mark.parametrize("raw", ['{"v":1,"v":1}', '{"n":NaN}', '{"n":Infinity}', '{"n":-Infinity}'])
def test_duplicate_keys_and_nonfinite_json_are_rejected(raw):
    with pytest.raises(EventValidationError):
        decode_sse(f"id: 1\nevent: text_delta\ndata: {raw}\n\n")


def test_id_type_and_common_counter_must_match():
    event = make_event(run_id="run-1", seq=1, ts=AT, type="text_delta", payload={"text": "合成"})
    with pytest.raises(EventValidationError):
        decode_sse(encode_sse(event).replace("id: 1", "id: 2"))
    with pytest.raises(EventValidationError):
        decode_sse(encode_sse(event).replace("event: text_delta", "event: status"))
    with pytest.raises(EventValidationError):
        decode_sse(encode_sse(event).replace("id: 1", "id: 01"))
    assert decode_sse(": ping\n\n") is None
    assert decode_sse(encode_sse(event).replace("\n", "\r\n")) == event


@pytest.mark.parametrize("value", [float("nan"), float("inf"), {1: "bad"}, "\ud800"])
def test_non_json_payload_values_fail_safely(value):
    with pytest.raises(EventValidationError):
        EventDraft("text_delta", {"text": value})


def test_core3_historical_read_is_explicit_and_cannot_write_final():
    legacy = {
        "schema_version": "core3.0",
        "answer": "合成旧正文",
        "validation": {"valid": True, "schema": "core3.0"},
        "meta": {"core_run": {"run_id": "legacy-run", "dependencies": {"synthetic": 1}}},
    }
    assert read_envelope(legacy).text == "合成旧正文"
    with pytest.raises(EventValidationError):
        EventDraft("final", {"message_id": "message-1", "envelope": legacy})
    legacy["validation"]["valid"] = 1
    with pytest.raises(EventValidationError):
        read_envelope(legacy)


def test_seeded_unicode_and_timezone_roundtrip_property():
    rng = random.Random(20261021)
    alphabet = '合成问题abc123\\"\r\n\t\x00\u2028\u2029🙂'
    for _ in range(1000):
        text = "".join(rng.choices(alphabet, k=rng.randrange(1, 150)))
        offset = timezone(timedelta(minutes=rng.choice([-720, -300, 0, 330, 480, 540, 840])))
        instant = (AT + timedelta(seconds=rng.randrange(-100000, 100000))).astimezone(offset)
        event = make_event(
            run_id="synthetic-run", seq=rng.randrange(1, 100000), ts=instant, type="text_delta", payload={"text": text}
        )
        frame = encode_sse(event)
        assert frame.count("\n") == 4
        assert decode_sse(frame.encode("utf-8")) == event
        assert event_data(event)["ts"].endswith("+08:00")
