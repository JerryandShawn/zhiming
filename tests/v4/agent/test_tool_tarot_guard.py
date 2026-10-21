"""Question similarity and redraw consent are deterministic and preserve negation."""

from __future__ import annotations

import pytest

from mingjing_core.application.agent_tools_tarot_guard import explicit_redraw, normalize_question, similar_question


@pytest.mark.parametrize(
    "left,right",
    [
        (" 这次面试会顺利吗？", "这次面试会顺利吗"),
        ("ＡＢＣ １２３", "abc123"),
        ("合成面试，能通过吗？", "合成面试能通过吗！"),
        ("这次合成面试是否会顺利通过", "这次合成面试是否会顺利通过呢"),
    ],
)
def test_same_or_highly_similar_question(left: str, right: str) -> None:
    assert similar_question(left, right)


@pytest.mark.parametrize(
    "left,right",
    [
        ("", ""),
        ("工资", "工作"),
        ("升职吗", "离职吗"),
        ("这次合成面试能顺利通过吗", "我今晚适合去哪家餐厅吃饭"),
    ],
)
def test_different_questions_not_folded(left: str, right: str) -> None:
    assert not similar_question(left, right)


@pytest.mark.parametrize(
    "text",
    [
        "我坚持重新抽牌",
        "请重新抽牌",
        "请再抽一次",
        "我要重新抽",
        "我还是坚持重抽",
        "请重新抽牌，不要再问我",
        "别让我焦虑，我坚持重抽",
    ],
)
def test_current_user_explicit_redraw(text: str) -> None:
    assert explicit_redraw(text)


@pytest.mark.parametrize(
    "text",
    [
        "不要重新抽牌",
        "我不想重抽",
        "如果我坚持重新抽牌呢",
        "朋友说“请重新抽牌”",
        "我只是想回看旧牌",
        "请解释重新抽牌这个词",
        "我不用重抽",
    ],
)
def test_quoted_hypothetical_or_negative_words_do_not_authorize(text: str) -> None:
    assert not explicit_redraw(text)


def test_normalization_does_not_remove_negation() -> None:
    assert normalize_question("我不会被录取") != normalize_question("我会被录取")
