"""Explicit v4 forgetting matches the current original to one real active fact."""

from __future__ import annotations

import re
from typing import Any

from mingjing_core.application.memory2_forget_candidates import forget_candidates
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.memory.policy import clause, hypothetical, mask_quoted
from mingjing_core.memory.private import require_persistent_source
from mingjing_core.memory.tokenize import tokenize

DELETE = re.compile(r"删除|删掉|撤销|忘记|忘了|忘掉")
DENIAL = re.compile(
    r"(?:别|不要|不能|不许|请勿|不想|不需要|不必|不是要你|没有要求|未要求).{0,3}"
    r"(?:删除|删掉|撤销|忘记|忘了|忘掉)"
)
REPORTED = re.compile(
    r"他说|她说|别人说|医生(?:说|建议)|家人说|朋友说|同事说|有人说|引用|转述|示例|例句|提示词"
    r"|我(?:之前|曾经|以前).{0,8}(?:说|要求|叫|让)"
)
STOP = re.compile(r"停止(?:使用)?|别再(?:用|记)|不要再(?:用|记)")
MANY_PEOPLE = re.compile(r"我(?:和|与|跟)|我们|他们|她们|两人|双方")
FAMILY = (r"妈妈|母亲|我妈", r"爸爸|父亲|我爸", r"朋友|同事|家人", r"丈夫|妻子|伴侣")
GENERIC = frozenset({"删除", "删掉", "撤销", "忘记", "忘掉", "记忆", "这条", "那条", "事情", "一下", "所有"})


def unique_reference(text: str, facts: list[dict[str, Any]]) -> str:
    words = {word for word in tokenize(text) if len(word) >= 2 and word not in GENERIC}
    people = [pattern for pattern in FAMILY if re.search(pattern, text)]
    matches = []
    for fact in facts:
        original = fact.get("content", "")
        if words.intersection(tokenize(original)) and all(re.search(pattern, original) for pattern in people):
            matches.append(fact["id"])
    if len(matches) != 1:
        raise EvidenceError("原话未唯一指出要遗忘的记忆，请确认具体内容")
    return matches[0]


def retire_from_message(memory: Any, owner: str, fact_id: str, source_id: str, operation_id: str) -> dict[str, Any]:
    source = memory.get_source(owner, source_id)
    fact = memory.repo.get(owner, "fact", fact_id, include_deleted=True)
    require_persistent_source(source)
    if source.get("role") != "user" or source["status"] != "active" or source["subject_id"] != fact["subject_id"]:
        raise ScopeError("遗忘需要当前人物的有效用户原话")
    if fact.get("case_id") and fact["case_id"] not in source.get("case_ids", []):
        raise ScopeError("遗忘目标不在当前已选择事项")
    text = mask_quoted(source.get("content", ""))
    intent = DELETE.search(text)
    if not intent:
        if STOP.search(text) and not hypothetical(text, 0, len(text)):
            return memory.retire_from_message(owner, fact_id, source_id, operation_id)
        raise EvidenceError("当前原话没有明确遗忘指令")
    statement = clause(text, intent.start(), intent.end(), comma=False)
    if (
        DENIAL.search(statement)
        or MANY_PEOPLE.search(statement)
        or REPORTED.search(text[: intent.start()])
        or hypothetical(text, intent.start(), intent.end())
    ):
        raise EvidenceError("否定、假设或多人遗忘需要先确认具体意图")
    facts = forget_candidates(memory, owner, source["subject_id"], source.get("case_ids", []))
    if unique_reference(statement, facts) != fact_id:
        raise EvidenceError("所给事实ID与用户原话的唯一目标不符")
    return memory.retire_fact(
        owner,
        fact_id,
        expected_revision=fact["revision"],
        scope="source" if re.search(r"原话|整条消息|所有来源", statement) else "fact",
    )
