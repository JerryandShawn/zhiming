"""Model port for real idle reflection: one structured call, strictly parsed, never trusted as authority."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Protocol

from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.models.port import ChatMessage, ModelPort, ToolSpec
from mingjing_core.models.quota_runtime import CallScope, call_scope

PROMPT_PATH = Path(__file__).resolve().parents[1] / "agent" / "prompts" / "memory_reflection.md"
PROMPT_VERSION = "1.0.0"
PROMPT_SHA256 = "30624c41bba7d11df7739cbfe67dabd0dc4b221d3b7c829b9052669b278de697"
MODEL_KINDS = ("preference", "constraint", "background", "goal", "event", "concern")
MAX_ITEMS = 20
TOOL = ToolSpec(
    name="submit_memories",
    description="提交本次整理出的长期记忆条目；没有就提交空列表。",
    parameters={
        "type": "object",
        "additionalProperties": False,
        "required": ["items"],
        "properties": {
            "items": {
                "type": "array",
                "maxItems": MAX_ITEMS,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["message_id", "quote", "kind", "explicit", "summary"],
                    "properties": {
                        "message_id": {"type": "string"},
                        "quote": {"type": "string", "minLength": 1, "maxLength": 300},
                        "kind": {"type": "string", "enum": list(MODEL_KINDS)},
                        "explicit": {"type": "boolean"},
                        "summary": {"type": "string", "minLength": 1, "maxLength": 60},
                    },
                },
            }
        },
    },
)


class ReflectionModel(Protocol):
    def extract(self, payload: dict[str, Any]) -> list[dict[str, Any]]: ...


def load_prompt() -> str:
    content = PROMPT_PATH.read_bytes()
    header = "<!-- prompt: memory_reflection v" + PROMPT_VERSION + " -->"
    text = content.decode("utf-8")
    if hashlib.sha256(content).hexdigest() != PROMPT_SHA256 or not text.startswith(header):
        raise EvidenceError("反思提示词内容或版本不符")
    return text[len(header) :].strip()


def parse_items(raw: Any, allowed_ids: set[str]) -> list[dict[str, Any]]:
    """Model output is untrusted shape; authority checks happen later against current PG originals."""
    if not isinstance(raw, dict) or set(raw) != {"items"} or not isinstance(raw["items"], list):
        raise EvidenceError("反思模型输出结构无效")
    if len(raw["items"]) > MAX_ITEMS:
        raise EvidenceError("反思模型输出条目过多")
    items = []
    for row in raw["items"]:
        if not isinstance(row, dict) or set(row) != {"message_id", "quote", "kind", "explicit", "summary"}:
            raise EvidenceError("反思条目结构无效")
        quote, summary = row["quote"], row["summary"]
        if (
            row["message_id"] not in allowed_ids
            or row["kind"] not in MODEL_KINDS
            or type(row["explicit"]) is not bool
            or not isinstance(quote, str)
            or not 1 <= len(quote) <= 300
            or not isinstance(summary, str)
            or not 1 <= len(summary) <= 60
        ):
            raise EvidenceError("反思条目字段无效或来源不在本次输入")
        items.append(dict(row))
    return items


class ModelReflection:
    """Real provider call on the background lane; the caller enforces the per-owner daily budget."""

    def __init__(self, port: ModelPort, *, max_output: int = 2000) -> None:
        self.port, self.max_output = port, max_output
        self.prompt = load_prompt()

    def extract(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        messages = [
            ChatMessage(role="system", content=self.prompt),
            ChatMessage(role="user", content=json.dumps(payload, ensure_ascii=False, sort_keys=True)),
        ]
        with call_scope(CallScope(lane="background")):
            result = self.port.complete(
                messages, tools=[TOOL], tool_choice="required", max_output=self.max_output, temperature=0
            )
        calls = [call for call in result.tool_calls if call.name == TOOL.name]
        if len(calls) != 1 or len(result.tool_calls) != 1:
            raise EvidenceError("反思模型需要且只能提交一次")
        allowed = {row["id"] for row in payload["messages"] if "content" in row}
        return parse_items(calls[0].arguments, allowed)


class ScriptedFactModel:
    """Test and rehearsal double: replays fixed items, records what it was shown, never calls a provider."""

    def __init__(self, items: list[dict[str, Any]] | None = None) -> None:
        self.items = list(items or [])
        self.calls: list[dict[str, Any]] = []

    def extract(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        self.calls.append(json.loads(json.dumps(payload, ensure_ascii=False)))
        allowed = {row["id"] for row in payload["messages"] if "content" in row}
        return parse_items({"items": self.items}, allowed)
