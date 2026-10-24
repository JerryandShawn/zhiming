"""Only a complete, unquoted first-person withdrawal sentence selects a literal topic."""

from __future__ import annotations

import re
from typing import Any

from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.memory.policy import HYPOTHESIS, mask_quoted

FORGET = re.compile(
    r"把我(?P<topic>[^，。？！!?；;“”「」『』\"'`\n]{2,40}?)(?:的事|的信息|这件事)?(?:忘了|忘记)[。！!]?"
)


def forget_topic(text: str) -> str | None:
    match = FORGET.fullmatch(mask_quoted(text).strip())
    return match.group("topic").strip() if match else None


def require_unique_topic(facts: list[dict[str, Any]], topic: str, selected_id: str) -> None:
    matches = {fact["id"] for fact in facts if topic in fact.get("content", "")}
    if matches != {selected_id}:
        raise EvidenceError("需要明确要忘记的那一条记忆")


def withdrawal_denied(text: str) -> bool:
    command = mask_quoted(text)
    return bool(
        HYPOTHESIS.search(command)
        or re.search(r"(?:别|不要|不能|不想|不用|不必)[^，,。；;\n]{0,40}(?:删除|忘记|忘了)", command)
    )
