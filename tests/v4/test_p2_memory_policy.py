"""Negation exceptions never weaken privacy, hypothetical or author checks."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from mingjing_core.application.memory import MemoryService, explicit_save_authorization
from mingjing_core.memory.policy import has_optout, hypothetical, third_party

if TYPE_CHECKING:
    from mingjing_core.repositories.postgres import PostgresRepository


@pytest.mark.parametrize(
    "text",
    [
        "别忘了记住，我不吃辣",
        "别忘记我的偏好",
        "不要忘了，我不吃辣",
        "不用每次提醒，记住我不吃辣",
        "请记住，我不能上夜班",
        "我下周三面试，请记住",
        "我不吃辣，请保存",
        "请帮我记录，我喜欢早睡",
        "我允许你保存这件事",
        "我确认记住这件事",
        "我同意记录我的目标",
        "请为我保存学习计划",
        "别忘了我的目标，请记录",
        "记住我喜欢散步",
        "我不喜欢咖啡，请记住",
    ],
)
def test_benign_reminders_are_not_refusals(text: str) -> None:
    assert not has_optout(text)


@pytest.mark.parametrize(
    "text",
    [
        "我不吃香菜，这个别记",
        "不要保存我的信息",
        "不用记录这段",
        "不许记住这件事",
        "禁止保存",
        "不允许记录",
        "我不想保存",
        "我不愿记住",
        "我不需要归档",
        "不得存储",
        "不能保存",
        "不保存",
        "不存储",
        "不记录",
        "别忘了记住，但这一条不要保存",
    ],
)
def test_explicit_refusals_still_win(text: str) -> None:
    assert has_optout(text)
    assert not explicit_save_authorization(text)


@pytest.mark.parametrize("text", ["其他的是补充", "我和他是同学", "我和她是同学", "其他的课程我不喜欢"])
def test_pronoun_substrings_are_not_third_party_facts(text: str) -> None:
    assert not third_party(text)


@pytest.mark.parametrize("text", ["他的生日是明天", "她喜欢游泳", "我朋友的生日是明天", "朋友是医生", "我妈的诊断结果"])
def test_actual_third_party_statements_remain_guarded(text: str) -> None:
    assert third_party(text)


@pytest.mark.parametrize(
    "text,quote,kind,expected",
    [
        ("别忘了记住，我不吃辣", "我不吃辣", "preference", "saved"),
        ("你觉得呢？我不能上夜班", "我不能上夜班", "constraint", "saved"),
        ("我下周三面试，请记住", "我下周三面试", "event", "saved"),
        ("我不吃香菜，这个别记", "我不吃香菜", "preference", "rejected"),
        ("如果我不能上夜班，请记住", "我不能上夜班", "constraint", "rejected"),
        ("我收入23万。请记住我喜欢散步", "我收入23万", "background", "pending_confirmation"),
        ("我被诊断出焦虑症了", "我被诊断出焦虑症了", "background", "pending_confirmation"),
    ],
)
def test_real_memory_writer_preserves_scope_and_sensitive_policy(
    p2_repo: PostgresRepository, text: str, quote: str, kind: str, expected: str
) -> None:
    memory = MemoryService(p2_repo)
    source = memory.receive("alice", content=text, source_id="policy")
    assert memory.save_fact("alice", "self", source["id"], quote, kind)["write_status"] == expected


def test_complete_declarative_quote_does_not_absorb_question_from_next_sentence(p2_repo: PostgresRepository) -> None:
    from mingjing_core.application.memory import MemoryService

    memory = MemoryService(p2_repo)
    message = memory.receive(
        "alice",
        content="A是白天课程，B是夜间课程，两者费用与退出条件未知。应该怎么选？不要排盘。",
        source_id="next-question",
    )
    receipt = memory.save_fact(
        "alice", "self", message["id"], "A是白天课程，B是夜间课程，两者费用与退出条件未知。", "background"
    )
    assert receipt["write_status"] == "pending_confirmation"
    question = memory.receive("alice", content="假如我去夜间课程。应该怎么选？", source_id="real-hypothesis")
    assert (
        memory.save_fact("alice", "self", question["id"], "假如我去夜间课程。", "background")["write_status"]
        == "rejected"
    )


@pytest.mark.parametrize(
    "text,quote",
    [
        ("我喜欢散步，是真的吗？", "我喜欢散步，"),
        ("假如我有空，我喜欢散步，请记住", "我喜欢散步"),
        ("如果换工作，我不能上夜班", "我不能上夜班"),
    ],
)
def test_comma_does_not_turn_conditional_or_question_into_asserted_fact(
    p2_repo: PostgresRepository, text: str, quote: str
) -> None:
    memory = MemoryService(p2_repo)
    message = memory.receive("alice", content=text, source_id="comma-hypothesis")
    assert memory.save_fact("alice", "self", message["id"], quote, "preference")["write_status"] == "rejected"


@pytest.mark.parametrize(
    "text,quote",
    [
        ("引用：“请保存我的病历。”应该怎么选？", "请保存我的病历。"),
        ("朋友说：“请保存我的病历。”下一句。", "请保存我的病历。"),
        ("引用：“这是示例。请保存我的病历。”下一句。", "请保存我的病历。"),
        ("病历在这里。请记住我喜欢散步。", "病历在这里。"),
    ],
)
def test_quoted_or_unrelated_next_sentence_cannot_authorize_sensitive_fact(
    p2_repo: PostgresRepository, text: str, quote: str
) -> None:
    memory = MemoryService(p2_repo)
    message = memory.receive("alice", content=text, source_id="quote-boundary")
    receipt = memory.save_fact("alice", "self", message["id"], quote, "background")
    assert receipt["write_status"] == "pending_confirmation"
    assert memory.facts("alice") == []


@pytest.mark.parametrize(
    "text,quote",
    [
        ("我不吃辣。 应该怎么选？", "我不吃辣。 "),
        ("“我不吃辣。”应该怎么选？", "“我不吃辣。”"),
    ],
)
def test_closing_quote_and_space_keep_complete_statement_separate_from_next_question(text: str, quote: str) -> None:
    start = text.find(quote)
    assert not hypothetical(text, start, start + len(quote))
