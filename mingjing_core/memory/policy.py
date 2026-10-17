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


def mask_quoted(text: str) -> str:
    for opening, closing in (("“", "”"), ("「", "」"), ("『", "』"), ('"', '"'), ("'", "'"), ("`", "`")):
        text = re.sub(
            re.escape(opening) + r"[^" + re.escape(closing) + r"\n]*" + re.escape(closing),
            lambda match: " " * len(match.group()),
            text,
        )
    return text


def clause_bounds(text: str, start: int, end: int, *, comma: bool = True) -> tuple[int, int]:
    hard = "。！？!?；;\n"
    separators = hard + ("，," if comma else "")
    left = max(text.rfind(mark, 0, start) for mark in separators) + 1
    closing = " \t\r”’」』\"'）)]】〕》〉"
    tail = text[start:end].rstrip(closing)
    ends = [text.find(mark, end) for mark in separators]
    right = (
        end if tail and tail[-1] in hard else min([position + 1 for position in ends if position >= 0] or [len(text)])
    )
    while right < len(text) and text[right] in closing:
        right += 1
    return left, right


def clause(text: str, start: int, end: int, *, comma: bool = True) -> str:
    left, right = clause_bounds(text, start, end, comma=comma)
    return text[left:right]


def authorization_clause(text: str, start: int, end: int) -> str:
    # Mask complete original quotes before slicing, so an inner sentence cannot
    # lose its opening quote and turn reported speech into user consent.
    left, right = clause_bounds(text, start, end, comma=False)
    return mask_quoted(text)[left:right]


def hypothetical(text: str, start: int, end: int) -> bool:
    return HYPOTHESIS.search(clause(text, start, end, comma=False)) is not None


def third_party(quote: str) -> bool:
    return THIRD_PARTY.search(quote) is not None
