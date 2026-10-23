"""Independent evidence, date, and delivery boundaries for structural checks."""

from datetime import UTC, datetime

import pytest
from mingjing_core.validation.structural import StructuralContext, structural_check

from mingjing_core.timekit.clock import FrozenClock

SAVE_NOTE = "（这条还没有真正保存，需要的话告诉我）"


def context(**overrides: object) -> StructuralContext:
    values: dict[str, object] = {
        "clock": FrozenClock(datetime(2026, 10, 18, 2, 30, tzinfo=UTC)),
        "timezone": "Asia/Shanghai",
        "aliases": frozenset({"f1", "c1"}),
    }
    values.update(overrides)
    return StructuralContext(**values)


def codes(result: object) -> set[str]:
    return {finding.code for finding in result.findings}


def test_removes_only_unknown_alias_and_keeps_the_answer() -> None:
    result = structural_check("已有依据〔c1〕，另一个引用〔c99〕没有来源。", context())
    assert "〔c1〕" in result.text
    assert "〔c99〕" not in result.text
    assert "另一个引用" in result.text
    assert "unknown_alias" in codes(result)


@pytest.mark.parametrize("status", ["saved", "updated"])
def test_success_receipt_has_to_bind_to_the_claim_target(status: str) -> None:
    receipt = {"write_status": status, "alias": "f1", "summary": "喜欢简洁回答"}
    result = structural_check("已保存：喜欢简洁回答〔f1〕。", context(receipts=(receipt,)))
    assert SAVE_NOTE not in result.text
    assert "false_receipt" not in codes(result)


@pytest.mark.parametrize("status", ["pending_confirmation", "stopped", "deleted", "rejected", "success", ""])
def test_non_saved_status_cannot_authorise_a_saved_claim(status: str) -> None:
    receipt = {"write_status": status, "alias": "f1", "summary": "喜欢简洁回答"}
    result = structural_check("已保存：喜欢简洁回答〔f1〕。", context(receipts=(receipt,)))
    assert SAVE_NOTE in result.text
    assert "false_receipt" in codes(result)


def test_unrelated_saved_target_does_not_cover_another_fact() -> None:
    receipt = {"write_status": "saved", "alias": "f2", "summary": "喜欢喝热水"}
    result = structural_check("已保存：喜欢简洁回答〔f1〕。", context(receipts=(receipt,)))
    assert SAVE_NOTE in result.text


def test_inconsistent_legacy_and_new_status_fields_fail_to_authorise() -> None:
    receipt = {"write_status": "deleted", "status": "saved", "alias": "f1", "summary": "喜欢简洁回答"}
    result = structural_check("已保存：喜欢简洁回答〔f1〕。", context(receipts=(receipt,)))
    assert SAVE_NOTE in result.text


def test_matching_receipt_does_not_cover_another_sentence_in_the_same_answer() -> None:
    receipt = {"write_status": "saved", "alias": "f1", "summary": "喜欢简洁回答"}
    result = structural_check("已保存：喜欢简洁回答〔f1〕。已记住：喜欢喝热水〔f2〕。", context(receipts=(receipt,)))
    assert result.text.count(SAVE_NOTE) == 1
    assert "喜欢喝热水" in result.text


@pytest.mark.parametrize(
    "text",
    [
        "我已经记下了。",
        "已记住你的偏好。",
        "已保存这条内容。",
        "我已经保存了。",
        "已更新这条记录。",
        "已经帮你记住了。",
        "已经替你保存了。",
        "帮你记下了。",
        "我记住了。",
        "我记下了。",
        "这条已经保存。",
        "内容已保存。",
        "你的偏好已更新。",
        "已经记住。",
        "保存好了。",
    ],
)
def test_save_assertions_without_any_receipt_receive_exact_annotation(text: str) -> None:
    result = structural_check(text, context())
    assert SAVE_NOTE in result.text
    assert "false_receipt" in codes(result)
    assert any(finding.item == "E2" and finding.severity == 5 for finding in result.findings)


@pytest.mark.parametrize(
    "text",
    [
        "我没有记下。",
        "我不会记住。",
        "这条还没保存。",
        "这条尚未保存。",
        "我没有保存你的资料。",
        "我不会保存这段话。",
        "我还没有更新记录。",
        "这次未保存。",
        "请不要记住这件事。",
        "暂时不保存。",
        "如果你需要，我可以保存。",
        "你要我记住吗？",
        "需要的话告诉我，我再记下。",
        "我会在确认后保存。",
        "我记得你之前提过。",
    ],
)
def test_negated_future_and_question_save_wording_is_not_a_receipt_claim(text: str) -> None:
    result = structural_check(text, context())
    assert SAVE_NOTE not in result.text
    assert "false_receipt" not in codes(result)


@pytest.mark.parametrize("calls,allowed", [(0, True), (1, False), (2, False), (3, False)])
def test_ask_user_counter_gates_next_call_without_swallowing_answer(calls: int, allowed: bool) -> None:
    result = structural_check("先回答你关心的内容。", context(ask_user_calls=calls))
    assert result.ask_user_allowed is allowed
    assert bool("ask_user_limit" in codes(result)) is (calls >= 2)
    assert result.text == "先回答你关心的内容。"


def test_empty_fallback_still_has_unknown_alias_and_false_receipt_checked() -> None:
    result = structural_check("  \n ", context(last_model_text="我已经记下了〔f99〕。"))
    assert result.text.strip()
    assert "〔f99〕" not in result.text
    assert SAVE_NOTE in result.text
    assert {"empty_answer", "unknown_alias", "false_receipt"} <= codes(result)


def test_empty_answer_and_empty_last_text_get_friendly_nonempty_fallback() -> None:
    result = structural_check("", context(last_model_text="  "))
    assert result.text.strip()
    assert "empty_answer" in codes(result)


@pytest.mark.parametrize(
    "wrong,right",
    [
        ("10月21日（周四）", "10月21日（周三）"),
        ("10月21日(周四)", "10月21日(周三)"),
        ("10月21日（星期四）", "10月21日（星期三）"),
        ("10/21（周四）", "10/21（周三）"),
        ("10/21(星期四)", "10/21(星期三)"),
        ("2026年10月21日（周四）", "2026年10月21日（周三）"),
        ("2026-10-21（周四）", "2026-10-21（周三）"),
        ("2026/10/21（周四）", "2026/10/21（周三）"),
    ],
)
def test_weekday_correction_preserves_date_and_surrounding_style(wrong: str, right: str) -> None:
    result = structural_check(f"安排在{wrong}，到时确认。", context())
    assert result.text == f"安排在{right}，到时确认。"
    assert "weekday_fixed" in codes(result)


def test_yearless_date_uses_nearest_year_across_new_year() -> None:
    clock = FrozenClock(datetime(2026, 1, 2, 2, tzinfo=UTC))
    result = structural_check("12月31日（周四）已经结束。", context(clock=clock))
    assert "12月31日（周三）" in result.text


def test_explicit_year_is_not_overwritten_with_clock_year() -> None:
    result = structural_check("2025年10月21日（周四）已经过去。", context())
    assert "2025年10月21日（周二）" in result.text


@pytest.mark.parametrize(
    "text,expected",
    [
        ("今天10月21日可以再看。", "10月18日"),
        ("明天10月21日再确认。", "10月19日"),
        ("后天10月21日见。", "10月20日"),
        ("昨天10月21日聊过。", "10月17日"),
        ("明天是10/21。", "10月19日"),
        ("明天是2026-10-21。", "10月19日"),
    ],
)
def test_relative_date_disagreement_adds_exact_fallback_if_critic_unavailable(text: str, expected: str) -> None:
    result = structural_check(text, context(critic_available=False))
    assert f"（日期以 {expected} 为准）" in result.text
    assert "time_error" in codes(result)
    assert any(finding.item == "E1" and finding.severity == 5 for finding in result.findings)


def test_relative_date_uses_owner_civil_day_rather_than_utc_day() -> None:
    clock = FrozenClock(datetime(2026, 10, 18, 23, 30, tzinfo=UTC))
    result = structural_check("明天10月19日再聊。", context(clock=clock, critic_available=False))
    assert "（日期以 10月20日 为准）" in result.text


def test_available_critic_gets_evidence_issue_without_fallback_annotation() -> None:
    result = structural_check("明天10月21日再确认。", context(critic_available=True))
    assert "time_error" in codes(result)
    assert "（日期以 " not in result.text


@pytest.mark.parametrize(
    "text",
    [
        "今天10月18日可以休息。",
        "明天10月19日再确认。",
        "后天10月20日见。",
        "昨天10月17日聊过。",
        "今天先休息；10月21日再确认。",
        "今天先休息。10月21日再确认。",
        "明天的事以后说！10月21日还有安排。",
    ],
)
def test_matching_dates_or_different_clauses_are_not_false_time_errors(text: str) -> None:
    result = structural_check(text, context(critic_available=False))
    assert "time_error" not in codes(result)
    assert "（日期以 " not in result.text


def test_farewell_removes_question_sentence_only_from_the_last_paragraph() -> None:
    text = "前面讨论的问题是什么？\n\n晚安，好好休息。还想再聊聊吗？"
    result = structural_check(text, context(farewell=True))
    assert result.text == "前面讨论的问题是什么？\n\n晚安，好好休息。"
    assert "farewell_question_removed" in codes(result)


def test_farewell_question_only_reply_is_preserved_to_avoid_empty_delivery() -> None:
    text = "还想聊点什么吗？"
    result = structural_check(text, context(farewell=True))
    assert result.text == text
    assert "farewell_question_removed" in codes(result)


def test_regular_turn_question_is_not_deleted() -> None:
    text = "你最在乎什么？"
    result = structural_check(text, context(farewell=False))
    assert result.text == text
    assert "farewell_question_removed" not in codes(result)


def test_findings_do_not_expose_synthetic_answer_in_repr() -> None:
    result = structural_check("已保存：合成私密测试标记XYZ。", context())
    assert "合成私密测试标记XYZ" not in repr(result.findings)
