"""Nine frozen synthetic checks consume at most twenty physical attempts total."""

from __future__ import annotations

from dataclasses import dataclass

from mingjing_core.models.port import ChatMessage, ToolSpec

SCHEMA = {
    "type": "object",
    "properties": {"value": {"type": "string", "enum": ["合成"]}},
    "required": ["value"],
    "additionalProperties": False,
}
ECHO = ToolSpec("synthetic_echo", "回传合成值，不执行外部操作", SCHEMA)
OTHER = ToolSpec("synthetic_other", "第二个纯合成工具，不执行外部操作", SCHEMA)
NESTED = ToolSpec(
    "synthetic_nested",
    "回传嵌套合成值，无副作用",
    {
        "type": "object",
        "properties": {"payload": SCHEMA},
        "required": ["payload"],
        "additionalProperties": False,
    },
)


@dataclass(frozen=True)
class EquivalenceCase:
    ident: str
    prompt: str
    tools: tuple[ToolSpec, ...] = ()
    roundtrip: bool = False

    def messages(self) -> list[ChatMessage]:
        return [
            ChatMessage("system", "这是一项纯合成协议检查。遵守工具schema，不执行任何现实操作。"),
            ChatMessage("user", self.prompt),
        ]


CASES = (
    EquivalenceCase("EQ01", "请只回复：合成"),
    EquivalenceCase("EQ02", "合成基准为北京时间2026-10-17（周六），请原样回复日期和星期。"),
    EquivalenceCase("EQ03", "请简短回复：合成用量检查。"),
    EquivalenceCase("EQ04", "请调用synthetic_echo，value为合成。", (ECHO,)),
    EquivalenceCase("EQ05", "请同时调用两个提供的工具，各一次，value均为合成。", (ECHO, OTHER)),
    EquivalenceCase("EQ06", "请调用synthetic_nested，payload.value为合成。", (NESTED,)),
    EquivalenceCase("EQ07", "以下为合成资料：" + "合成资料仅用于协议检查。" * 512 + "请只回复：合成"),
    EquivalenceCase("EQ08", '请只回复JSON：{"ok":true}'),
    EquivalenceCase("EQ09", "请先调用synthetic_echo，value为合成；收到结果后只回复：合成。", (ECHO,), True),
)
SCENARIOS = tuple(case.ident for case in CASES)
MAX_ATTEMPTS = 20


def expected_arguments(name: str) -> dict:
    return {"payload": {"value": "合成"}} if name == "synthetic_nested" else {"value": "合成"}
