"""Fifteen independent positive/negative examples for each added deterministic rule."""

from datetime import UTC, datetime, timedelta

import pytest

from mingjing_core.timekit.clock import FrozenClock
from mingjing_core.validation.structural import StructuralContext, structural_check


def context(**kwargs: object) -> StructuralContext:
    return StructuralContext(clock=FrozenClock(datetime(2026, 10, 18, 2, tzinfo=UTC)), **kwargs)


@pytest.mark.parametrize("offset", range(15))
def test_weekday_fifteen_wrong_examples_get_corrected(offset: int) -> None:
    day = datetime(2026, 10, 18) + timedelta(days=offset)
    actual = "一二三四五六日"[day.weekday()]
    wrong = "一二三四五六日"[(day.weekday() + 1) % 7]
    text = f"{day.month}月{day.day}日（周{wrong}）可以再确认。"
    result = structural_check(text, context())
    assert result.text == text.replace(f"周{wrong}", f"周{actual}")
    assert any(finding.code == "weekday_fixed" for finding in result.findings)


@pytest.mark.parametrize("offset", range(15))
def test_weekday_fifteen_correct_examples_remain_byte_identical(offset: int) -> None:
    day = datetime(2026, 10, 18) + timedelta(days=offset)
    text = f"{day.month}/{day.day}（星期{'一二三四五六日'[day.weekday()]}）不用改。"
    result = structural_check(text, context())
    assert result.text == text
    assert not result.findings


@pytest.mark.parametrize("index", range(15))
def test_relative_fifteen_inconsistent_examples_use_civil_clock(index: int) -> None:
    name, delta = (("今天", 0), ("明天", 1), ("后天", 2), ("昨天", -1))[index % 4]
    incorrect = 21 + index
    day = datetime(2026, 10, 18) + timedelta(days=incorrect)
    text = f"{name}是{day.month}月{day.day}日，先核实。"
    result = structural_check(text, context(critic_available=False))
    actual = datetime(2026, 10, 18) + timedelta(days=delta)
    assert f"（日期以 {actual.month}月{actual.day}日 为准）" in result.text
    assert any(finding.item == "E1" and finding.severity == 5 for finding in result.findings)


@pytest.mark.parametrize("index", range(15))
def test_relative_fifteen_consistent_or_cross_clause_examples_do_not_warn(index: int) -> None:
    name, delta = (("今天", 0), ("明天", 1), ("后天", 2), ("昨天", -1))[index % 4]
    actual = datetime(2026, 10, 18) + timedelta(days=delta)
    text = f"{name}{actual.month}月{actual.day}日再确认。"
    if index >= 8:
        text = f"{name}先休息；12月{index}日另外有安排。"
    result = structural_check(text, context(critic_available=False))
    assert result.text == text
    assert not any(finding.code == "time_error" for finding in result.findings)


@pytest.mark.parametrize("index", range(15))
def test_farewell_fifteen_questions_are_removed_only_from_last_paragraph(index: int) -> None:
    text = f"前面问过的第{index + 1}个问题是什么？\n\n先好好休息。还要我帮你做什么？"
    result = structural_check(text, context(farewell=True))
    assert result.text == f"前面问过的第{index + 1}个问题是什么？\n\n先好好休息。"
    assert any(finding.code == "farewell_question_removed" for finding in result.findings)


@pytest.mark.parametrize("index", range(15))
def test_farewell_fifteen_no_question_last_paragraphs_are_untouched(index: int) -> None:
    text = f"前面的问题{index}你已经说清了？\n\n晚安，明天再聊。"
    result = structural_check(text, context(farewell=True))
    assert result.text == text
    assert not result.findings


def test_internal_failure_does_not_disclose_exception_or_swallow_draft() -> None:
    class BrokenClock:
        def now(self) -> datetime:
            raise RuntimeError("SYNTHETIC_PRIVATE_EXCEPTION_MARKER")

    draft = "这段正常回答需要照常交付。"
    result = structural_check(draft, StructuralContext(clock=BrokenClock()))
    assert result.text == draft
    assert any(finding.code == "structural_internal_error" for finding in result.findings)
    assert "SYNTHETIC_PRIVATE_EXCEPTION_MARKER" not in repr(result)


def test_invalid_counter_never_opens_an_additional_ask_or_removes_answer() -> None:
    result = structural_check("已有回答。", context(ask_user_calls=-1))
    assert result.text == "已有回答。"
    assert not result.ask_user_allowed


def test_nearest_year_ambiguity_is_reported_instead_of_guessing() -> None:
    clock = FrozenClock(datetime(2026, 7, 2, 2, tzinfo=UTC))
    text = "1月1日（周一）这里没有明确年份。"
    result = structural_check(text, StructuralContext(clock=clock))
    assert result.text == text
    assert any(finding.code == "date_unresolved" for finding in result.findings)
