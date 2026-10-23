"""Refusal recognition never treats quoted, hypothetical or negated speech as refusal."""

from __future__ import annotations

import pytest

from mingjing_core.application.agent_tools_clarification import declines_answer

POSITIVE = [
    "我不想说",
    "不想回答",
    "我不方便说",
    "暂时不说",
    "我不愿意透露",
    "别再问我",
    "你别问了",
    "先别问",
    "不要再问",
    "你先说",
    "随便",
    "随你吧",
    "不知道",
    "我不知道。",
    "不清楚",
    "没想好",
    "这个暂时不说了",
    "你先说吧，我听着",
]
NEGATIVE = [
    "我想说具体情况",
    "我可以回答",
    "我知道了",
    "我清楚自己的目标",
    "我想好了",
    "我不是不想说，只是想先整理一下",
    "并非不想回答，我现在回答",
    "我不是不知道，答案是夜班",
    "我不想说谎",
    "随便看看风景",
    "我不知道为什么会变",
    "你能告诉我不知道是什么意思吗？",
    "如果我说不知道，你怎么回答",
    "假设我不想说",
    "举个例子，不想说时怎么办",
    "他说“我不想说”",
    "她说「你别问了」",
    "原话是'不知道'",
    "请解释随便这个词",
]


@pytest.mark.parametrize("text", POSITIVE)
def test_declined_answer(text: str) -> None:
    assert declines_answer(text)


@pytest.mark.parametrize("text", NEGATIVE)
def test_current_answer_not_declined(text: str) -> None:
    assert not declines_answer(text)


def test_second_batch_schemas_flatten_nested_options_and_case_changes() -> None:
    from mingjing_core.agent.tools.interaction_parameters import (
        AskUser,
        CaseAddEvent,
        CaseList,
        CaseUpdate,
        PresentOptions,
        ScheduleFollowup,
        SetReminder,
    )
    from mingjing_core.models.schema_flatten import flatten_schema

    for model in (AskUser, CaseAddEvent, CaseList, CaseUpdate, PresentOptions, ScheduleFollowup, SetReminder):
        schema = flatten_schema(model.model_json_schema())
        assert "$ref" not in str(schema) and "$defs" not in str(schema)
        assert schema["additionalProperties"] is False


@pytest.mark.parametrize("options", [["单个"], ["", "另一个"], ["a"] * 5])
def test_ask_invalid_shortcuts_rejected(options: list[str]) -> None:
    from pydantic import ValidationError

    from mingjing_core.agent.tools.interaction_parameters import AskUser

    with pytest.raises(ValidationError):
        AskUser(question="合成问题", options=options, why="影响建议", slot="工作地点", changes_conclusion="改变结论")
