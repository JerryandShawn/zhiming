"""Offline output chunks and every-frame comparison cannot invent observations."""

from __future__ import annotations

import copy
from datetime import datetime

import pytest

from mingjing_core.agent.envelope import build_envelope
from mingjing_core.agent.events import make_event
from mingjing_core.timekit.clock import FrozenClock
from mingjing_core.validation.structural import check_structure
from tools.eval.providers.scripted import ScriptedProvider
from tools.eval.targets.v4_scripted import ScriptedModelPort
from tools.eval.targets.v4_sse_proof import check_complete
from tools.eval.targets.v4_sse_reconnect import partition_script


def native_events(extra_text: bool = False) -> list[dict]:
    clock = FrozenClock(datetime.fromisoformat("2026-10-17T10:30:00+08:00"))
    result = build_envelope(
        {"id": "run-synthetic", "operation_id": "synthetic-operation", "subject": "self", "request": {}},
        check_structure("合成完整回答", {}),
        message_id="synthetic-message",
    )
    values = [
        ("status", {"text": "正在整理", "phase": "thinking"}),
        ("text_delta", {"text": "合成"}),
        ("text_delta", {"text": "完整回答"}),
    ]
    if extra_text:
        values.append(("text_delta", {"text": "额外片段"}))
    values.append(("final", {"message_id": "synthetic-message", "envelope": result}))
    return [make_event(kind, "run-synthetic", index, body, clock=clock) for index, (kind, body) in enumerate(values, 1)]


def test_offline_chunks_preserve_original_model_boundary_and_reject_nonoutput_data():
    text = "先整理条件，再做比较。"
    port = ScriptedModelPort()
    script = [{"turn": 1, "model": partition_script([{"text": text}])}]
    port.start(ScriptedProvider(script), 1, {})
    chunks = [event.data for event in port.stream([], tools=[]) if event.type == "text"]
    assert len(chunks) == 2 and "".join(chunks) == text and port.calls == 1
    legacy = [{"turn": 1, "model": [{"text": text}]}]
    port.start(ScriptedProvider(legacy), 1, {})
    assert [event.data for event in port.stream([], tools=[]) if event.type == "text"] == [text]
    tool = {"tool_call": {"name": "time_context", "arguments": {}}}
    port.start(ScriptedProvider([{"turn": 1, "model": [tool]}]), 1, {})
    assert [event.type for event in port.stream([], tools=[])] == ["tool_call", "usage", "done"]
    for bad in (
        {"text": text, "text_chunks": ["wrong", text]},
        {"text": text, "text_chunks": [text, ""]},
        {"text": text, "text_chunks": [text], "db": {}},
        {"text": text, "text_chunks": [text], "event": "run.completed"},
        {"text": text, "text_chunks": [text], "proof": {}},
        {"text": text, "text_chunks": [text], **tool},
    ):
        with pytest.raises(ValueError):
            port.start(ScriptedProvider([{"turn": 1, "model": [bad]}]), 1, {})


@pytest.mark.parametrize("fault", ["duplicate", "missing"])
def test_all_native_frames_reject_duplicate_or_missing_http_delivery(fault):
    pg = native_events()
    replay = copy.deepcopy(pg[2:])
    if fault == "duplicate":
        replay.insert(0, copy.deepcopy(pg[1]))
    else:
        replay.pop(0)
    with pytest.raises(ValueError, match="entire persisted"):
        check_complete(pg, pg[:2], replay, 2)


def test_extra_related_native_frames_are_all_mapped_instead_of_hidden():
    pg = native_events(extra_text=True)
    proof = check_complete(pg, pg[:2], pg[2:], 2)
    assert proof["events"] == ["text.delta", "text.delta", "text.delta", "run.completed"]
    assert len(proof["received_event_ids"]) == 4 and len(proof["replayed_event_ids"]) == 3
    assert proof["related_native_ids"] == [2, 3, 4, 5]
    assert [row["seq"] for row in proof["native_pg_frames"]] == [1, 2, 3, 4, 5]
    assert all(set(row) == {"seq", "kind", "sha256"} for row in proof["native_pg_frames"])
