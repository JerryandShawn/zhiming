"""Adversarial contracts found by independently reading the first implementation."""

from datetime import UTC, datetime

import pytest

from mingjing_core.timekit.clock import FrozenClock
from mingjing_core.validation.structural import StructuralContext, structural_check

SAVE_NOTE = "（这条还没有真正保存，需要的话告诉我）"


def context(**overrides: object) -> StructuralContext:
    values: dict[str, object] = {
        "clock": FrozenClock(datetime(2026, 10, 18, 2, 30, tzinfo=UTC)),
        "aliases": frozenset({"f1", "c1"}),
    }
    values.update(overrides)
    return StructuralContext(**values)


def codes(result: object) -> set[str]:
    return {finding.code for finding in result.findings}


@pytest.mark.parametrize("text", [" 〔c99〕 ", "\n〔f99〕\n", "〔c99〕", "〔c99〕 〔f99〕"])
def test_removing_all_unsupported_aliases_cannot_leave_blank_delivery(text: str) -> None:
    result = structural_check(text, context())
    assert result.text.strip()
    assert "unknown_alias" in codes(result)
    assert "〔c99〕" not in result.text
    assert "〔f99〕" not in result.text


@pytest.mark.parametrize(
    "text",
    [
        "喜欢简洁回答〔f1〕供参考：已保存喜欢喝热水。",
        "已保存喜欢喝热水（此前的简洁回答偏好见〔f1〕）。",
        "参考喜欢简洁回答〔f1〕以及喜欢喝热水：后者已保存。",
    ],
)
def test_unrelated_success_alias_in_the_same_clause_cannot_authorise_saved_target(text: str) -> None:
    receipt = {"write_status": "saved", "alias": "f1", "summary": "喜欢简洁回答"}
    result = structural_check(text, context(receipts=(receipt,)))
    assert SAVE_NOTE in result.text
    assert "false_receipt" in codes(result)


@pytest.mark.parametrize(
    "text",
    [
        "此前没有保存但现在已经保存了。",
        "之前不会记住然而这次已经记住了。",
        "尚未保存是过去的状态而现在已保存了。",
        "并非没有保存：我已经保存了。",
    ],
)
def test_earlier_negation_does_not_hide_a_later_positive_save_claim(text: str) -> None:
    result = structural_check(text, context())
    assert SAVE_NOTE in result.text
    assert "false_receipt" in codes(result)


@pytest.mark.parametrize(
    "text",
    ["没有保存，也没有更新。", "我不会记住但会继续回答。", "不是已经保存了，需要你确认后才会保存。"],
)
def test_real_negation_remains_a_non_claim_after_contrast_handling(text: str) -> None:
    result = structural_check(text, context())
    assert SAVE_NOTE not in result.text
    assert "false_receipt" not in codes(result)


@pytest.mark.parametrize("text", ["2月30日（周一）", "2026年2月29日（星期日）", "13/1（周五）"])
def test_illegal_calendar_date_is_reported_and_preserved_instead_of_invented(text: str) -> None:
    result = structural_check(text, context())
    assert result.text == text
    assert "date_unresolved" in codes(result)
    assert "weekday_fixed" not in codes(result)


def test_illegal_relative_date_is_not_silently_treated_as_consistent() -> None:
    result = structural_check("明天2026-02-30再确认。", context(critic_available=False))
    assert {"date_unresolved", "time_error"} & codes(result)
    assert result.text.strip()
    assert "2026-02-30" in result.text


def test_ambiguous_year_with_two_candidates_does_not_get_guessed_weekday() -> None:
    clock = FrozenClock(datetime(2026, 10, 1, 2, tzinfo=UTC))
    text = "4月1日（周五）再确认。"
    result = structural_check(text, context(clock=clock))
    assert result.text == text
    assert "date_unresolved" in codes(result)
    assert "weekday_fixed" not in codes(result)


def test_year_explicit_leap_day_is_evaluated_in_its_own_year() -> None:
    result = structural_check("2028年2月29日（周一）再确认。", context())
    assert "2028年2月29日（周二）" in result.text
    assert "weekday_fixed" in codes(result)


def test_unsupported_alias_as_last_model_fallback_cannot_escape_nonempty_guard() -> None:
    result = structural_check("", context(last_model_text=" 〔c99〕 "))
    assert result.text.strip()
    assert {"empty_answer", "unknown_alias"} <= codes(result)


def test_farewell_trim_preserves_previous_paragraph_and_trailing_newlines() -> None:
    text = "已有的说明？这段保留。\n\n晚安。还要继续吗？\n\n"
    result = structural_check(text, context(farewell=True))
    assert "已有的说明？这段保留。" in result.text
    assert "晚安。" in result.text
    assert "还要继续吗" not in result.text
    assert result.text.endswith("\n\n")


@pytest.mark.parametrize("text", ["已保存喜欢简洁回答。", "明天10月21日再确认。"])
def test_rerunning_structural_checks_does_not_repeat_the_same_annotation(text: str) -> None:
    ctx = context(critic_available=False)
    once = structural_check(text, ctx)
    twice = structural_check(once.text, ctx)
    assert twice.text == once.text
