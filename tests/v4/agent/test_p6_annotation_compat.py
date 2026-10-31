"""One exact clause-local annotation is idempotent; it never becomes a saved receipt."""

import pytest

from mingjing_core.validation.structural import ANNOTATION, check_structure


@pytest.mark.parametrize("text", ["已经保存" + ANNOTATION + "偏好", "我已经保存了喜欢徒步。" + ANNOTATION])
def test_exact_adjacent_annotation_is_not_added_twice_but_remains_unsupported(text: str) -> None:
    result = check_structure(text, {})
    assert result.text == text and result.text.count(ANNOTATION) == 1
    assert {item["code"] for item in result.warnings} == {"unsupported_save_claim"}


def test_new_unsupported_save_after_an_old_annotation_still_gets_new_warning() -> None:
    text = "已经保存" + ANNOTATION + "偏好。已经保存另一条安排。"
    result = check_structure(text, {})
    assert result.text.count(ANNOTATION) == 2 and "unsupported_save_claim" in str(result.warnings)


@pytest.mark.parametrize(
    "text",
    [
        "已经保存" + ANNOTATION.replace("，", ","),
        ANNOTATION + "。已经保存另一条安排。",
        "已经保存偏好。其他话" + ANNOTATION,
        "已经保存偏好。 " + ANNOTATION,
        "已经保存偏好，后面引用“" + ANNOTATION + "”",
    ],
)
def test_near_or_elsewhere_annotation_does_not_suppress_new_warning(text: str) -> None:
    result = check_structure(text, {})
    assert result.text.count(ANNOTATION) == text.count(ANNOTATION) + 1


def test_real_saved_receipt_preserves_old_rule_without_annotation() -> None:
    text = "我已经保存了喜欢徒步。"
    result = check_structure(text, {}, ({"write_status": "saved", "kind": "fact", "id": "fact-real"},))
    assert result.text == text and result.warnings == ()
