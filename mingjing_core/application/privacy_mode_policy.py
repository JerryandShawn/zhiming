"""Only direct, unquoted current-user commands can change conversation privacy."""

from __future__ import annotations

import re
from typing import Literal

from mingjing_core.domain.contracts import EvidenceError

PrivacyAction = Literal["enter", "exit"]
PREFIX = r"(?:(?:请(?:你)?|麻烦(?:你)?|帮我|现在|先|我想|我要)[，,\s]*)*"
ENTER = re.compile(
    PREFIX + r"(?:(?:开(?:启|个)?|进入|切换到?|开始)(?:一个)?无痕(?:模式|线程|对话)?|"
    r"(?:这(?:段|个|些)|本(?:轮|次)|接下来(?:这段)?)?(?:话|内容|对话|消息)?"
    r"(?:请)?(?:别|不要)(?:记(?:住|录|下)?|保存|存储|留存)(?:进?记忆)?)"
    r"(?:吧|了)?[。.!！\s]*$"
)
EXIT = re.compile(PREFIX + r"(?:结束|退出|关闭|停止)(?:本次|当前)?无痕(?:模式|对话|线程)?(?:吧|了)?[。.!！\s]*$")
NON_DIRECT = re.compile(
    r"假如|假设|如果|要是|举个例子|比如说|例如|也许|可能会|转述|引用|复述|说|告诉|表示|写着|原话|提到"
    r"|(?:朋友|同事|别人|他|她|某人).{0,8}(?:说|让我|要求)"
    r"|我(?:刚才|之前|曾经|昨天).{0,4}说"
)
DECLINE = re.compile(r"(?:别|不要)(?:记|保存|存储|留存)")


def _unquoted(text: str) -> str:
    result = list(text)
    for match in re.finditer(r"```[\s\S]*?(?:```|$)|(?m:^[ \t]*>[^\n]*)", text):
        result[match.start() : match.end()] = " " * len(match.group())
    text = "".join(result)
    for opening, closing in (("“", "”"), ("‘", "’"), ("「", "」"), ("『", "』"), ('"', '"'), ("'", "'"), ("`", "`")):
        text = re.sub(
            re.escape(opening) + "[\\s\\S]*?(?:" + re.escape(closing) + "|$)", lambda m: " " * len(m.group()), text
        )
    return text


def privacy_action(text: str) -> PrivacyAction | None:
    """This consumes authenticated raw input, never model text or an extracted quote."""
    if not isinstance(text, str):
        raise EvidenceError("隐私指令需要当前用户原话")
    masked, found = _unquoted(text), set()
    if re.search(r"假如|假设|如果|要是|举个例子|比如说|例如", masked):
        return None
    for hard in re.split(r"[。.!！；;\n]", masked):
        prefix = ""
        for clause in re.split(r"[，,]", hard):
            prefix += clause
            if NON_DIRECT.search(prefix):
                continue
            clause = clause.strip()
            if ENTER.fullmatch(clause):
                found.add("enter")
            if EXIT.fullmatch(clause):
                found.add("exit")
    if len(found) > 1:
        raise EvidenceError("同一条消息的无痕进入和退出指令冲突，请明确选择")
    return next(iter(found), None)


def blocks_current_run(text: str) -> bool:
    return privacy_action(text) == "enter" and DECLINE.search(_unquoted(text)) is not None
