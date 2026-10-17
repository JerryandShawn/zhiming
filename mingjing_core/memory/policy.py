"""Narrow false-positive fixes; sensitive-category authorization stays in v3."""

import re

BENIGN_REMINDERS = re.compile(r"别忘(?:了|记)?(?:记住)?|不要忘了|不用每次提醒")
DECLINE = re.compile(
    r"(?:不要|不用|不许|禁止|不允许|别|不想|不愿|不需要).{0,12}(?:保存|存储|记录|记住|留存|归档|存记忆|加入.{0,3}记忆)"
    r"|(?:不得|不能)(?:保存|存储|记录|留存)"
    r"|(?:不保存|不存储|不记录|不留存)|(?:别|不要)记(?:住|下)?(?!性|忆)"
)
HYPOTHESIS = re.compile(r"假如|假设|如果|要是|举个例子|比如说|也许|可能会|[？?]")
THIRD_PARTY = re.compile(
    r"(?:^|[，,。！？；;\n\s])\s*(?:(?:我的?)?(?:朋友|同事|家人|妈妈|爸爸|母亲|父亲|妈|爸)|他|她)"
    r"(?:的|是|出生|生日|喜欢|职业|已经|已|最近|目前|被|确诊)"
)


def has_optout(text: str) -> bool:
    return DECLINE.search(BENIGN_REMINDERS.sub(" ", text)) is not None


def clause(text: str, start: int, end: int, *, comma=True) -> str:
    separators = "。！？!?；;\n" + ("，," if comma else "")
    left = max(text.rfind(mark, 0, start) for mark in separators) + 1
    ends = [text.find(mark, end) for mark in separators]
    right = min([position + 1 for position in ends if position >= 0] or [len(text)])
    return text[left:right]


def hypothetical(text: str, start: int, end: int) -> bool:
    return HYPOTHESIS.search(clause(text, start, end)) is not None


def third_party(quote: str) -> bool:
    return THIRD_PARTY.search(quote) is not None
