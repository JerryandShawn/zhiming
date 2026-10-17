"""Negation exceptions never weaken privacy, hypothetical or author checks."""

import pytest

from mingjing_core.application.memory import MemoryService, explicit_save_authorization
from mingjing_core.memory.policy import has_optout, third_party


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
def test_benign_reminders_are_not_refusals(text):
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
def test_explicit_refusals_still_win(text):
    assert has_optout(text)
    assert not explicit_save_authorization(text)


@pytest.mark.parametrize("text", ["其他的是补充", "我和他是同学", "我和她是同学", "其他的课程我不喜欢"])
def test_pronoun_substrings_are_not_third_party_facts(text):
    assert not third_party(text)


@pytest.mark.parametrize("text", ["他的生日是明天", "她喜欢游泳", "我朋友的生日是明天", "朋友是医生", "我妈的诊断结果"])
def test_actual_third_party_statements_remain_guarded(text):
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
def test_real_memory_writer_preserves_scope_and_sensitive_policy(p2_repo, text, quote, kind, expected):
    memory = MemoryService(p2_repo)
    source = memory.receive("alice", content=text, source_id="policy")
    assert memory.save_fact("alice", "self", source["id"], quote, kind)["write_status"] == expected
