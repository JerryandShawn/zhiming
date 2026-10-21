"""Cross-language schema, Core producers and SSE wire examples share frozen v1."""

from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from mingjing_core.agent.envelope import build_envelope, public_question
from mingjing_core.agent.events import encode_sse, envelope_schema, event_schema, heartbeat, make_event, validate_event
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.timekit.clock import FrozenClock
from mingjing_core.validation.structural import check_structure

CONTRACTS = Path(__file__).resolve().parents[3] / "docs/v4/contracts"
CLOCK = FrozenClock(datetime.fromisoformat("2026-10-17T00:30:00+00:00"))
FORMATS = FormatChecker()


@FORMATS.checks("date-time", raises=ValueError)
def real_instant(value: object) -> bool:
    # The lock deliberately has no optional rfc3339-validator dependency.
    return not isinstance(value, str) or datetime.fromisoformat(value).utcoffset() is not None


QUESTION = {
    "ask_id": "ask-synthetic",
    "question": "更想先讨论哪件事？",
    "options": [{"id": "a", "label": "工作"}, {"id": "b", "label": "生活"}],
    "allow_free_text": True,
    "multi": False,
    "why": "决定接下来要用的资料",
}
OPTIONS = {
    "options_id": "options-synthetic",
    "options": [
        dict(
            id=ident,
            title=title,
            benefit="",
            cost="",
            risk="",
            reversibility="unknown",
            first_step="",
            unknowns=["费用"],
        )
        for ident, title in [("a", "先了解"), ("b", "稍后决定")]
    ],
}


def envelope() -> dict:
    return build_envelope(
        {"id": "run-synthetic", "operation_id": "operation-synthetic", "subject": "self", "request": {}},
        check_structure("这是合成回答", {}),
        message_id="message-synthetic",
    )


def samples() -> dict:
    return {
        "started": dict(thread_id="life:self", message_id="message-synthetic", incognito=False),
        "status": dict(text="正在整理", phase="thinking"),
        "tool_call": dict(call_id="call-synthetic", name="memory_search", summary="正在查找相关记忆"),
        "tool_result": dict(call_id="call-synthetic", name="memory_search", summary="查找结束", ok=True),
        "text_delta": dict(text="合成\n文本"),
        "text_reset": dict(text="替换后的合成回答", reason="revised", revision_id="revision-synthetic"),
        "memory_receipt": dict(fact_id="fact-synthetic", write_status="saved", summary="已保存", sensitive=False),
        "ask_user": QUESTION,
        "present_options": OPTIONS,
        "review": dict(
            state="revised", reasons=[dict(code="generic_barnum", severity=3)], revision_id="revision-synthetic"
        ),
        "final": dict(message_id="message-synthetic", envelope=envelope()),
        "error": dict(code="MODEL_UNAVAILABLE", message="暂时没能完成，请稍后再试。", retryable=True),
    }


@pytest.mark.parametrize("kind", list(samples()))
def test_each_event_is_valid_in_core_schema_and_sse(kind: str) -> None:
    event = make_event(kind, "run-synthetic", 7, samples()[kind], clock=CLOCK)
    schema = event_schema()
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FORMATS).validate(event)
    wire = encode_sse(event)
    fields = wire.rstrip("\n").splitlines()
    assert fields[0:2] == ["id: 7", "event: " + kind] and len(fields) == 3
    assert json.loads(fields[2].removeprefix("data: ")) == event["data"]
    assert event["data"]["ts"] == "2026-10-17T08:30:00+08:00"


@pytest.mark.parametrize("zone", ["+00:00", "+09:00", "-05:00"])
def test_event_clock_converts_explicit_zone_and_never_uses_host_zone(zone: str) -> None:
    at = datetime.fromisoformat("2026-10-17T23:30:00" + zone)
    event = make_event("status", "run-synthetic", 1, samples()["status"], clock=FrozenClock(at))
    parsed = datetime.fromisoformat(event["data"]["ts"])
    assert parsed == at and event["data"]["ts"].endswith("+08:00")


@pytest.mark.parametrize("stamp", ["2026-10-17T08:30:00+09:00", "2026-02-30T08:30:00+08:00", "2026-10-17T08:30:00Z"])
def test_wrong_or_impossible_timestamp_is_rejected(stamp: str) -> None:
    data = dict(v=1, run_id="run-synthetic", seq=1, ts=stamp, **samples()["status"])
    with pytest.raises(EvidenceError):
        validate_event("status", data)
    assert list(
        Draft202012Validator(event_schema(), format_checker=FORMATS).iter_errors(dict(type="status", data=data))
    )


@pytest.mark.parametrize("field,value", [("v", True), ("v", 2), ("seq", True), ("seq", 0), ("phase", "private")])
def test_public_identity_and_phase_are_strict(field: str, value: object) -> None:
    data = make_event("status", "run-synthetic", 1, samples()["status"], clock=CLOCK)["data"]
    with pytest.raises(EvidenceError):
        validate_event("status", dict(data, **{field: value}))


@pytest.mark.parametrize("field", ["reasoning", "tool_arguments", "private_protocol", "owner", "trace"])
def test_unknown_and_private_fields_cannot_reach_public_events(field: str) -> None:
    with pytest.raises(EvidenceError):
        make_event(
            "tool_call", "run-synthetic", 1, dict(samples()["tool_call"], **{field: "synthetic private"}), clock=CLOCK
        )


@pytest.mark.parametrize("field", ["usage", "meta", "validation"])
def test_private_fields_inside_compatibility_projections_are_rejected(field: str) -> None:
    result = envelope()
    result[field]["reasoning"] = "synthetic private"
    with pytest.raises(EvidenceError):
        make_event("final", "run-synthetic", 1, dict(message_id="message-synthetic", envelope=result), clock=CLOCK)


@pytest.mark.parametrize("identifiers", [{}, {"fact_id": "f", "proposal_id": "p"}])
def test_memory_receipt_requires_exactly_one_entity_in_core_and_json_schema(identifiers: dict) -> None:
    payload = dict(write_status="rejected", summary="未保存", sensitive=True, **identifiers)
    data = dict(v=1, run_id="run-synthetic", seq=1, ts="2026-10-17T08:30:00+08:00", **payload)
    with pytest.raises(EvidenceError):
        validate_event("memory_receipt", data)
    assert list(Draft202012Validator(event_schema()).iter_errors(dict(type="memory_receipt", data=data)))


@pytest.mark.parametrize("state", ["saved", "pending_confirm", "undone", "rejected"])
def test_all_four_memory_states_have_frozen_names(state: str) -> None:
    event = make_event(
        "memory_receipt", "run-synthetic", 1, dict(samples()["memory_receipt"], write_status=state), clock=CLOCK
    )
    assert event["data"]["write_status"] == state


def test_decision_unknowns_question_ids_final_identity_and_finite_numbers() -> None:
    bad_options = copy.deepcopy(OPTIONS)
    bad_options["options"][1]["id"] = "a"
    with pytest.raises(EvidenceError):
        make_event("present_options", "run-synthetic", 1, bad_options, clock=CLOCK)
    with pytest.raises(EvidenceError):
        make_event("final", "run-synthetic", 1, dict(message_id="other", envelope=envelope()), clock=CLOCK)
    with pytest.raises(EvidenceError):
        make_event(
            "final",
            "run-synthetic",
            1,
            dict(message_id="message-synthetic", envelope=dict(envelope(), usage={"model_steps": float("nan")})),
            clock=CLOCK,
        )
    with pytest.raises(EvidenceError):
        make_event("status", "run-synthetic", 1, dict(samples()["status"], seq=999), clock=CLOCK)


def test_core4_required_nulls_and_legacy_question_projection_are_preserved() -> None:
    result = envelope()
    assert result["asked"] is None and result["options"] is None
    event = make_event("final", "run-synthetic", 1, dict(message_id="message-synthetic", envelope=result), clock=CLOCK)
    assert event["data"]["envelope"]["asked"] is None and event["data"]["envelope"]["options"] is None
    legacy = dict(
        question="合成问题？",
        options=["选一", "选二"],
        allow_free_text=True,
        why="帮助理解",
        slot="工作地点",
        changes_conclusion="会影响方案",
    )
    question = public_question(legacy, "message-synthetic")
    assert question == public_question(legacy, "message-synthetic") and question["multi"] is False
    assert len({option["id"] for option in question["options"]}) == 2
    assert "slot" not in question and "changes_conclusion" not in question


def test_published_schemas_match_core_source_and_heartbeat_consumes_no_seq() -> None:
    assert json.loads((CONTRACTS / "events_v1.schema.json").read_text(encoding="utf-8")) == event_schema()
    published = json.loads((CONTRACTS / "core4_envelope_v1.schema.json").read_text(encoding="utf-8"))
    assert published == envelope_schema()
    Draft202012Validator(published).validate(envelope())
    assert heartbeat() == ": ping\n\n" and "id:" not in heartbeat()


def test_resumed_reset_may_clear_an_uncommitted_draft() -> None:
    event = make_event("text_reset", "run-synthetic", 1, dict(text="", reason="resumed"), clock=CLOCK)
    Draft202012Validator(event_schema()).validate(event)
    assert event["data"]["text"] == ""
