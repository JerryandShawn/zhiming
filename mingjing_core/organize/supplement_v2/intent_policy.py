"""Conservative goal intent gate; conditions and explicit refusals cannot authorize an upgrade."""

import re

_CONDITIONAL = re.compile(
    r"\b(?:if|suppose|supposing|hypothetical|hypothetically|assuming|maybe|perhaps)\b"
    r"|\bfor\s+(?:example|instance)\b|\blet['’]s\s+say\b|\bimagine\s+(?:an?|the|i|my|that)\b"
    r"|\b(?:might|may)\s+(?:not\s+)?(?:want|be|attend|have|go|achieve)\b",
    re.I,
)
_NEGATIVE = re.compile(
    r"(?:不|没)(?:再|太)?(?:想|要|打算|准备|希望|需要)|并非.{0,12}(?:目标|希望)|不是.{0,12}目标|没有.{0,8}目标"
    r"|放弃.{0,12}(?:目标|拿到|完成)|\b(?:no|not)\s+(?:my\s+|a\s+|the\s+)?goal\b"
    r"|\b(?:do|does|did)\s+not\b|\b(?:don['’]t|doesn['’]t|didn['’]t|won['’]t|wouldn['’]t|cannot)\b"
    r"|\b(?:not|never)\s+(?:want|intend|plan|aim|wish|hope|seek|pursue|achieve)\b",
    re.I,
)
_HARD_BOUNDARY = re.compile(r"[\n;；。！？!?]")


def asserted_goal(source_text: str, start: int, end: int) -> bool:
    previous = list(_HARD_BOUNDARY.finditer(source_text[:start]))
    following = _HARD_BOUNDARY.search(source_text[end:])
    lower = previous[-1].end() if previous else 0
    upper = end + following.start() if following else len(source_text)
    context = source_text[lower:upper]
    return not (_CONDITIONAL.search(context) or _NEGATIVE.search(context))
