"""Candidate codec roundtrips on MockTransport; no configured live capabilities."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Iterator
from typing import Any

import httpx

from mingjing_core.models.anthropic_messages import AnthropicMessages
from mingjing_core.models.errors import ModelProtocolError
from mingjing_core.models.openai_compat import OpenAICompat
from mingjing_core.models.port import ChatMessage, StreamEvent

from .v4_scripted import ScriptedModelPort


def recording(chunks: list[dict[str, Any]]) -> bytes:
    return "".join("data: " + json.dumps(chunk, ensure_ascii=False) + "\n\n" for chunk in chunks).encode()


def wire_output(action: dict[str, Any], protocol: str, call_id: str) -> bytes:
    call = action.get("tool_call")
    if protocol == "openai_compat":
        delta = (
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": call_id,
                        "function": {
                            "name": call["name"],
                            "arguments": json.dumps(call["arguments"], ensure_ascii=False),
                        },
                    }
                ]
            }
            if call
            else {"content": action["text"]}
        )
        return recording([{"choices": [{"delta": delta, "finish_reason": "tool_calls" if call else "stop"}]}])
    block = (
        {"type": "tool_use", "id": call_id, "name": call["name"], "input": {}} if call else {"type": "text", "text": ""}
    )
    delta = (
        {"type": "input_json_delta", "partial_json": json.dumps(call["arguments"], ensure_ascii=False)}
        if call
        else {"type": "text_delta", "text": action["text"]}
    )
    return recording(
        [
            {"type": "message_start", "message": {"usage": {}}},
            {"type": "content_block_start", "index": 0, "content_block": block},
            {"type": "content_block_delta", "index": 0, "delta": delta},
            {"type": "content_block_stop", "index": 0},
            {"type": "message_delta", "delta": {"stop_reason": "tool_use" if call else "end_turn"}},
            {"type": "message_stop"},
        ]
    )


class ScriptedWirePort(ScriptedModelPort):
    def __init__(self, protocol: str, candidate: str) -> None:
        super().__init__()
        adapter = {"openai_compat": OpenAICompat, "anthropic_messages": AnthropicMessages}[protocol]
        self.protocol, self.candidate = protocol, candidate
        self.current_messages: list[ChatMessage] = []
        self.request_digests: list[str] = []
        self.echoes = 0
        self.adapter = adapter(
            base_url="https://synthetic.invalid/v1",
            api_key="synthetic-codec-key",
            model=candidate,
            provider="scripted",
            caps={"tools": True, "tool_choice": ["auto", "none"], "reasoning_replay": False},
            transport=httpx.MockTransport(self._respond),
            max_retries=0,
            settings={"thinking": {"type": "enabled", "budget_tokens": 1024}},
        )

    def _respond(self, request: httpx.Request) -> httpx.Response:
        if request.url.host != "synthetic.invalid" or not self.actions:
            raise ModelProtocolError()
        body = json.loads(request.content)
        self.request_digests.append(hashlib.sha256(request.content).hexdigest())
        if any(message.role == "tool" for message in self.current_messages):
            if self.protocol == "openai_compat":
                echoes = [row for row in body["messages"] if row["role"] == "tool" and row.get("tool_call_id")]
            else:
                echoes = [
                    block
                    for row in body["messages"]
                    for block in row["content"]
                    if block["type"] == "tool_result" and block.get("tool_use_id")
                ]
            if not echoes:
                raise ModelProtocolError()
            self.echoes += len(echoes)
        action = self._value(copy.deepcopy(self.actions.pop(0)), self.current_messages)
        return httpx.Response(200, content=wire_output(action, self.protocol, f"wire-{self.calls}"))

    def stream(self, messages: list[ChatMessage], **kwargs: Any) -> Iterator[StreamEvent]:
        self.calls += 1
        self.current_messages = messages
        self.requests.append(
            {"messages": copy.deepcopy(messages), "tool_names": [tool.name for tool in kwargs["tools"]]}
        )
        yield from self.adapter.stream(messages, **kwargs)

    def proof(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate,
            "protocol": self.protocol,
            "mock_requests": self.adapter.request_count,
            "tool_result_echoes": self.echoes,
            "request_sha256": list(self.request_digests),
            "scope": "offline candidate caps + real codec + PG; no live model capability claim",
        }


def run_matrix(seed: dict[str, Any], turn: dict[str, Any], dsn: str) -> dict[str, Any]:
    from .v4_target import V4Target

    results, errors, calls = [], [], 0
    for candidate in seed["controls"]["model_matrix"]:
        protocol = "anthropic_messages" if candidate.startswith("kimi") else "openai_compat"
        target = V4Target(dsn=dsn, protocol=protocol, candidate=candidate)
        try:
            target.reset(copy.deepcopy(seed))
            observed = target.send(copy.deepcopy(turn))
            calls += observed.model_calls
            current = target.repo.fetch_run(target.owner, target.run_ids[-1])
            proof = target.port.proof()
            proof.update(run_id=current["id"], run_status=current["status"])
            if observed.error or current["status"] != "succeeded" or proof["tool_result_echoes"] < 1:
                errors.append(candidate)
            results.append(proof)
        finally:
            target.close()
    return {
        "protocol_models": [item["candidate"] for item in results],
        "protocol_errors": errors,
        "model_calls": calls,
        "proofs": results,
    }
