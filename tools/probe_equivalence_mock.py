"""Deterministic Anthropic wire fixture; no socket, credential or provider call."""

import json

import httpx

from tools.probe_equivalence_cases import EquivalenceCase, expected_arguments


def mock_transport(case: EquivalenceCase, seen: list[dict]) -> httpx.MockTransport:
    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        assert not any(key in body for key in ("thinking", "reasoning_effort", "effort"))
        resumed = any(row["role"] == "assistant" for row in body["messages"])
        if resumed:
            assistant = next(row for row in body["messages"] if row["role"] == "assistant")
            assert any(
                block.get("type") == "thinking" and block.get("signature") == "synthetic-signature"
                for block in assistant["content"]
            )
        tools = case.tools if not resumed else ()
        events = [{"type": "message_start", "message": {"model": body["model"], "usage": {"input_tokens": 20}}}]
        blocks = [{"type": "thinking", "thinking": "纯合成私有推理", "signature": "synthetic-signature"}]
        if tools:
            blocks.extend(
                {
                    "type": "tool_use",
                    "id": "call-" + str(index),
                    "name": tool.name,
                    "input": expected_arguments(tool.name),
                }
                for index, tool in enumerate(tools)
            )
        else:
            text = "2026-10-17，周六" if case.ident == "EQ02" else '{"ok":true}' if case.ident == "EQ08" else "合成"
            blocks.append({"type": "text", "text": text})
        for index, block in enumerate(blocks):
            events.extend(
                [
                    {"type": "content_block_start", "index": index, "content_block": block},
                    {"type": "content_block_stop", "index": index},
                ]
            )
        events.extend(
            [
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "tool_use" if tools else "end_turn"},
                    "usage": {"output_tokens": 8},
                },
                {"type": "message_stop"},
            ]
        )
        wire = "".join("data: " + json.dumps(event, ensure_ascii=False) + "\n\n" for event in events)
        return httpx.Response(200, content=wire.encode("utf-8"))

    return httpx.MockTransport(respond)
