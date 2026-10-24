"""Four physical checks of R16; all prompts and tools are synthetic and fixed."""

from __future__ import annotations

from mingjing_core.models.port import ChatMessage
from tools.probe_equivalence_cases import ECHO, EquivalenceCase
from tools.probe_equivalence_control import digest

MODEL = "k3.1-pro"
CASES = (
    EquivalenceCase("K31-TOOLS", "先调用synthetic_echo，value为合成。收到结果后只回复：合成。", (ECHO,), True),
    EquivalenceCase("K31-INPUT", "以下仅为合成计量资料：" + "合成资料用于输入计量。" * 512 + "请只回复：合成"),
    EquivalenceCase(
        "K31-LONG",
        "请用中文写一篇1500至1800汉字的原创虚构小故事，主题为小镇图书馆。"
        "不要调用工具，保持完整结尾，正文之后单独一行写[K31-END]。",
    ),
)
SCENARIOS = tuple(case.ident for case in CASES)
EXPECTED = frozenset((case.ident, step) for case in CASES for step in range(1, 3 if case.roundtrip else 2))
FIELDS = frozenset(
    {
        "model",
        "scenario",
        "step",
        "passed",
        "response_model",
        "effort",
        "reasoning_present",
        "text_chars",
        "tool_count",
        "input_actual",
        "input_estimated",
        "input_ratio",
        "factor",
    }
)


def contract_digest() -> str:
    return digest(
        {
            "schema": "k31-connection-contract-r16",
            "model": MODEL,
            "effort": "high",
            "max_physical": 20,
            "steps": sorted(EXPECTED),
            "cases": [
                {
                    "id": case.ident,
                    "prompt": case.prompt,
                    "roundtrip": case.roundtrip,
                    "tools": [{"name": tool.name, "parameters": tool.parameters} for tool in case.tools],
                }
                for case in CASES
            ],
            "long_min_chinese": 1000,
            "long_end": "[K31-END]",
            "max_output": 8192,
        }
    )


def followup(response) -> list[ChatMessage]:
    return [
        response.as_chat(tool_cycle="k31-integration-cycle"),
        *[
            ChatMessage("tool", '{"value":"合成"}', tool_call_id=call.id, tool_cycle="k31-integration-cycle")
            for call in response.tool_calls
        ],
    ]
