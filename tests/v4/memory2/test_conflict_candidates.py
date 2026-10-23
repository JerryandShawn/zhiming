"""Candidate opposition is conservative and never claims general semantic coverage."""

import pytest

from mingjing_core.memory2.conflict_candidates import opposing_preferences


@pytest.mark.parametrize(
    "old,new",
    [
        ("我喜欢合成徒步", "我不喜欢合成徒步"),
        ("我喜欢合成徒步。", "我讨厌合成徒步"),
        ("我不喜欢合成夜班", "我最近喜欢合成夜班"),
        ("我喜爱合成跑步", "我现在不爱合成跑步"),
        ("我不再喜欢合成音乐", "目前我热爱合成音乐"),
    ],
)
def test_exact_topic_opposing_preferences_are_only_candidates(old: str, new: str) -> None:
    assert opposing_preferences(old, new)
    assert opposing_preferences(new, old)


@pytest.mark.parametrize(
    "old,new",
    [
        ("我喜欢合成徒步", "我喜欢合成徒步"),
        ("我不喜欢合成徒步", "我讨厌合成徒步"),
        ("我喜欢合成徒步", "我不喜欢合成夜班"),
        ("我喜欢合成徒步", "如果我不喜欢合成徒步"),
        ("我喜欢合成徒步", "我不喜欢合成徒步吗？"),
        ("我喜欢合成徒步", "我喜欢合成音乐但不喜欢合成徒步"),
        ("我喜欢合成徒步", "我不喜欢合成徒步中的竞争"),
        ("我喜欢《现在》", "我不喜欢《》"),
        ("我喜欢合成甲、乙", "我不喜欢合成甲乙"),
        ("我喜欢new york", "我不喜欢newyork"),
        ("我喜欢合成徒步", "我最近不想走路"),
        ("", "我不喜欢合成徒步"),
    ],
)
def test_different_topics_qualifiers_or_uncertain_semantics_are_not_classified(old: str, new: str) -> None:
    assert not opposing_preferences(old, new)
