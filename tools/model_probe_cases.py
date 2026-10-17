"""Small synthetic capability cases; never production or user conversations."""

from dataclasses import dataclass, field
from typing import Any

from mingjing_core.models.port import ChatMessage, Part, ToolSpec


@dataclass
class Probe:
    name: str
    messages: list[ChatMessage]
    tools: list[ToolSpec] = field(default_factory=list)
    choice: str = "auto"
    max_output: int = 800
    protocol: str = "anthropic_messages"


def cases() -> list[Probe]:
    text = [ChatMessage("user", "请只回复：合成探针正常。")]
    schema: dict[str, Any] = {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]}
    tool = ToolSpec("probe_echo", "把输入值原样提交。", schema)
    call = [ChatMessage("user", "请调用 probe_echo，value 为合成探针。")]
    result = [Probe("text_stream", text), Probe("single_tool", call, [tool])]
    for choice in ("auto", "none", "required", "probe_echo"):
        result.append(Probe("tool_choice_" + ("named" if choice == "probe_echo" else choice), call, [tool], choice))
    result.append(
        Probe("parallel_tools", [ChatMessage("user", "请在同一回答中调用 probe_echo 两次，值为一和二。")], [tool])
    )
    # A CRC-verified synthetic PNG contains no private image data.
    pixel = (
        "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAIAAAD8GO2jAAAANElEQVR4nO3NMQEAMAyEwG/8i30JlUCWbJwA"
        "eG1zaU7rcbDgADlADpAD5AA5QA6QA+Qg5AOmjQMQ4sS++gAAAABJRU5ErkJggg=="
    )
    result.append(
        Probe(
            "vision", [ChatMessage("user", [Part(text="描述这张合成图片的颜色即可。"), Part(type="image", data=pixel)])]
        )
    )
    for key, value in (
        ("default", "示例"),
        ("examples", ["示例"]),
        ("format", "date"),
        ("anyOf", [{"type": "string"}, {"type": "null"}]),
    ):
        property_schema = {key: value} if key == "anyOf" else {"type": "string", key: value}
        keyword_schema = {"type": "object", "properties": {"value": property_schema}, "required": ["value"]}
        result.append(Probe("schema_" + key, call, [ToolSpec("probe_echo", "提交合成值", keyword_schema)]))
    result.extend(
        [
            Probe("include_usage", text, protocol="openai_compat"),
            Probe(
                "chinese_long_output",
                [
                    ChatMessage(
                        "user",
                        "请写一篇至少2200个汉字的中文科普，介绍四季与日常作息。"
                        "这是合成输出完整性探针，不需要工具；结尾写【合成完毕】。",
                    )
                ],
                max_output=6000,
            ),
        ]
    )
    return result
