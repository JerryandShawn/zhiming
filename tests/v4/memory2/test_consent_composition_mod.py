"""A benign reminder instruction must never swallow a later explicit storage refusal."""

import pytest

from mingjing_core.memory2.consent_text import has_storage_optout


@pytest.mark.parametrize("prefix", ["不要提醒我", "不用再提醒我", "别重复提醒我"])
@pytest.mark.parametrize("joiner", ["也", "而且", "但是", "，"])
@pytest.mark.parametrize("refusal", ["不要保存这段", "不要记住这件事", "别把它写进记忆"])
def test_reminder_and_storage_refusal_can_coexist(prefix, joiner, refusal):
    assert has_storage_optout(prefix + joiner + refusal)


@pytest.mark.parametrize("joiner", ["但是", "但现在", "不过", "可是", "，"])
def test_negated_old_refusal_cannot_mask_current_refusal(joiner):
    text = "我不是说不要保存旧资料" + joiner + "这段不要保存"
    assert has_storage_optout(text)


@pytest.mark.parametrize(
    "text", ["不要提醒我，我会记住复习", "我不是说不要保存，记下我喜欢清淡", "别忘了记住我喜欢清淡"]
)
def test_benign_negation_or_reminder_is_not_storage_refusal(text):
    assert not has_storage_optout(text)
