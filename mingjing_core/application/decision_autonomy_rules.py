"""Observable decision delegation signals; the caller owns present_options and ask_user."""

import re
from dataclasses import dataclass, field

DELEGATION_PATTERNS = (
    re.compile(
        r"(?:你|由你|让你)(?:来|直接)?(?:替我|帮我)?(?:决定|做主|拿主意|选一个|选哪|定吧|定下来)"
    ),
    re.compile(
        r"我(?:都)?听你的|你说选哪个就选哪个|按你说的选|听你的安排|全由你做主|交给你决定"
    ),
    re.compile(
        r"(?:别|不用)(?:分析|解释).{0,6}(?:你选|直接定)|直接告诉我选谁|随便你选"
    ),
)


@dataclass(frozen=True)
class AutonomyDecision:
    delegated: bool
    require_present_options: bool
    ask_preference: bool
    preference: str | None = field(repr=False)
    preference_alias: str | None
    prohibit_unique_instruction: bool
    max_questions: int = 1


def detect_delegation(text: str) -> bool:
    quoted = [
        (match.start(), match.end())
        for match in re.finditer(r"[“\"「『‘][^”\"」』’\n]*[”\"」』’]", text)
    ]
    self_choices = re.finditer(
        r"(?:我自己|我会自己|我想自己|我要自己|决定还是我|自己来)(?:做)?(?:决定|选|挑)|"
        r"听你的分析|(?:我)?不(?:会)?听你的|(?:不会|不想|不)(?:照单全收|照做|全听|全收)",
        text,
    )
    last_self = max(
        (
            match.end()
            for match in self_choices
            if not any(
                start <= match.start() and match.end() <= end for start, end in quoted
            )
        ),
        default=-1,
    )
    for pattern in DELEGATION_PATTERNS:
        for match in pattern.finditer(text):
            if any(
                start <= match.start() and match.end() <= end for start, end in quoted
            ):
                continue
            if match.end() <= last_self:
                continue
            prefix = text[max(0, match.start() - 8) : match.start()]
            if re.search(r"别|不要|不用|不让|无需|不是|并非|不想", prefix):
                continue
            return True
    return False


def autonomy_decision(
    text: str,
    *,
    known_preference: str | None = None,
    preference_alias: str | None = None,
) -> AutonomyDecision:
    delegated = detect_delegation(text)
    if known_preference is not None and (
        not known_preference.strip()
        or not preference_alias
        or not re.fullmatch(r"[A-Za-z][A-Za-z0-9:_-]{0,120}", preference_alias)
    ):
        raise ValueError("复用已有偏好必须提供有效来源别名")
    return AutonomyDecision(
        delegated,
        delegated,
        delegated and known_preference is None,
        known_preference if delegated else None,
        preference_alias if delegated else None,
        delegated,
    )


def autonomy_warnings(text: str, *, delegated: bool) -> tuple[str, ...]:
    if delegated and re.search(
        r"(?:就|直接|必须)?选\s*[A-D甲乙丙丁]|就选这个|听我的选", text
    ):
        return ("J4_unique_instruction_after_delegation",)
    return ()


def dependency_copy_warnings(text: str) -> tuple[str, ...]:
    banned = ("连签", "打卡", "别错过明天", "记得每天来看", "每天必看")
    return tuple("dependency_copy:" + token for token in banned if token in text)
