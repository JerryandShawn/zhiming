"""Approved semantic alternatives still need actual injected evidence."""

import re

from tools.eval.targets.base import TurnResult


def cited_memory(result: TurnResult, query: str, *, constraint: bool = False) -> bool:
    injected = result.db.get("context", {}).get("injected_facts", [])
    return any(
        isinstance(row.get("alias"), str)
        and query in row.get("text", "")
        and (not constraint or row.get("kind") == "constraint")
        and "〔" + row["alias"] + "〕" in result.text
        for row in injected
    )


def naming_only_questions(text: str) -> bool:
    questions = re.split(r"[？?]", text)[:-1]
    return bool(questions) and all(
        re.search(r"怎么称呼|叫什么|怎么叫|叫我什么|叫你什么|名字", re.split(r"[。！!\n]", part)[-1])
        for part in questions
    )
