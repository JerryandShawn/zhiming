"""Slot names are explicit and bounded; temporary/hypothetical states are counterexamples."""

import pytest

from mingjing_core.memory.slots import SLOTS, compatible_statement, normalize_slot

SINGLE_EXAMPLES = [
    ("residence_city", "我现在住在杭州", "我搬到上海了"),
    ("employer", "我入职了合成甲公司", "我入职了合成乙公司"),
    ("job_role", "我的岗位是合成教师", "我转岗做合成设计师"),
    ("relationship_status", "我现在单身", "我结婚了"),
    ("spice_preference", "我不吃辣", "我最近能吃点辣了"),
    ("sleep_schedule", "我习惯早睡早起", "我现在改为晚睡"),
    ("exam_goal", "我准备考合成甲证", "我准备考合成乙证"),
    ("preferred_name", "以后叫我合成甲", "现在叫我合成乙"),
]


@pytest.mark.parametrize("name,old,new", SINGLE_EXAMPLES)
def test_single_slots_have_update_clues(name: str, old: str, new: str) -> None:
    assert SLOTS[name].cardinality == "single"
    assert compatible_statement(name, old) and compatible_statement(name, new)


@pytest.mark.parametrize(
    "name,text",
    [
        ("residence_city", "我在上海出差一周"),
        ("residence_city", "我在上海暂住"),
        ("residence_city", "下周去上海旅游"),
        ("residence_city", "如果我搬到上海呢？"),
        ("employer", "今天在合成甲公司临时工作"),
        ("job_role", "明天临时担任合成教师"),
        ("sleep_schedule", "今晚临时代夜班"),
        ("spice_preference", "今天试吃辣椒"),
        ("preferred_name", "临时叫我合成队长"),
        ("exam_goal", "假设我准备考合成甲证"),
    ],
)
def test_temporary_and_hypothetical_states_do_not_replace_long_term_values(name: str, text: str) -> None:
    assert not compatible_statement(name, text)


@pytest.mark.parametrize("value", [None, "", "未知槽", "工作城市", 1, True, [], {}])
def test_unknown_slot_is_omitted_without_inference(value: object) -> None:
    assert normalize_slot(value) is None


def test_catalog_is_finite_immutable_and_supports_chinese_labels() -> None:
    assert 10 <= len(SLOTS) <= 30
    assert normalize_slot(" 居住城市 ") == "residence_city"
    assert SLOTS["hobbies"].cardinality == SLOTS["important_people"].cardinality == "multi"
    assert all(slot.counterexamples for slot in SLOTS.values())
    with pytest.raises(TypeError):
        SLOTS["extra"] = SLOTS["hobbies"]
