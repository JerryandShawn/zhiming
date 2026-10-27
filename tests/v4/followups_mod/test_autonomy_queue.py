import pytest
from mingjing_core.application.decision_autonomy_rules import (
    autonomy_decision,
    autonomy_warnings,
    detect_delegation,
)

POSITIVE_DELEGATIONS = [
    "你替我决定吧。",
    "这件事由你做主。",
    "我都听你的。",
    "你说选哪个就选哪个。",
    "按你说的选。",
    "听你的安排。",
    "全由你做主。",
    "交给你决定。",
    "别分析了，你选吧。",
    "不用解释了，直接定。",
    "直接告诉我选谁。",
    "随便你选。",
    "你来帮我拿主意。",
    "让你直接替我选一个。",
    "你帮我定下来。",
]
NEGATIVE_DELEGATIONS = [
    "我听你的分析，最后我自己决定。",
    "不要你替我决定，帮我列出选项就好。",
    "不用你做主，我只需要事实。",
    "不是让你替我决定，是请你指出风险。",
    "我不想听你的安排，只想知道代价。",
    "别替我做主，列优缺点就行。",
    "我不听你的安排，我想自己选。",
    "同事说：‘我听你的’，这不是我的意思。",
    "把“你替我决定”这句话改成“我自己选择”。",
    "如果有人问‘你替我决定’，应该怎么回复？",
    "我自己来选，你先说哪条证据可靠。",
    "决定还是我做，你给我一个比较框架。",
    "我听你的建议，但不会照单全收。",
    "这一步我会自己决定，请你帮我核对预算。",
    "你怎么看这个选项的风险？",
]


@pytest.mark.parametrize("text", POSITIVE_DELEGATIONS)
def test_fifteen_explicit_delegations_require_options_one_preference_question_and_no_unique_instruction(
    text: str,
) -> None:
    decision = autonomy_decision(text)
    assert (
        decision.delegated
        and decision.require_present_options
        and decision.ask_preference
    )
    assert decision.prohibit_unique_instruction and decision.max_questions == 1
    assert autonomy_warnings("选 A 吧", delegated=decision.delegated)


@pytest.mark.parametrize("text", NEGATIVE_DELEGATIONS)
def test_fifteen_non_delegations_do_not_override_user_agency(text: str) -> None:
    assert not detect_delegation(text)
    assert not autonomy_decision(text).require_present_options


def test_latest_explicit_change_of_mind_is_not_erased_by_an_earlier_self_decision_clause() -> (
    None
):
    assert detect_delegation("刚才说我自己选，现在改了，你替我决定吧。")


def test_existing_sourced_preference_is_used_without_asking_the_same_question_again() -> (
    None
):
    result = autonomy_decision(
        "我听你的", known_preference="优先减少通勤", preference_alias="fact_pref_1"
    )
    assert result.require_present_options and not result.ask_preference
    assert (
        result.preference == "优先减少通勤" and result.preference_alias == "fact_pref_1"
    )
    assert "减少通勤" not in repr(result)
    with pytest.raises(ValueError):
        autonomy_decision("你替我决定", known_preference="优先减少通勤")
