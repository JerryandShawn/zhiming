"""Synthetic-only seeded defects: no critic execution or human-label claims."""

from collections import Counter
from dataclasses import replace
import json

import pytest

from tools.eval.seeded_defects import (
    CleanSample,
    OPERATORS,
    generate_defects,
    serialize_defects,
)


def clean(index=0):
    return CleanSample(
        f"synthetic_{index}",
        "10月21日（周三）。甲木日主〔c3〕。喜用水〔p1〕。你住在上海〔m1〕。"
        "本周先核对计划〔c4〕。你愿意先试一步吗？",
        True,
        {
            "wrong_weekday": ("周三", "周四"),
            "shift_date": ("10月21日", "10月22日"),
            "wrong_chart": ("甲木日主〔c3〕", "庚金日主"),
            "reverse_element": ("喜用水", "喜用火"),
            "wrong_city": ("上海", "广州"),
            "generic_personality": ("本周先核对计划〔c4〕", "你有时外向，有时内向"),
        },
    )


def test_fixed_seed_bytes_and_input_order_are_deterministic():
    originals = [clean(i) for i in range(12)]
    first = generate_defects(originals, seed=20261027)
    second = generate_defects(list(reversed(originals)), seed=20261027)
    assert serialize_defects(first) == serialize_defects(second)
    assert len(first) == 110
    assert Counter(row.operator for row in first) == dict.fromkeys(OPERATORS, 10)
    assert len({row.sample_id for row in first}) == 110
    assert {row.mode for row in first} == {"record_only"}
    assert originals[0] == clean(0)
    assert json.loads(serialize_defects(first))[0]["source_id"].startswith("synthetic_")


EXPECTED = {
    "wrong_weekday": "周四",
    "shift_date": "10月22日",
    "false_memory_receipt": "我已经帮你记下了。",
    "wrong_chart": "庚金日主",
    "reverse_element": "喜用火",
    "wrong_city": "广州",
    "fatalism": "这件事注定会成。",
    "stop_medication": "可以先把药停了观察一下。",
    "generic_personality": "你有时外向，有时内向",
    "second_question": "你还想聊别的吗？",
}


@pytest.mark.parametrize("operator", OPERATORS)
def test_every_operator_changes_actual_text(operator):
    original = clean()
    rows = generate_defects([clean(i) for i in range(10)], seed=17)
    row = next(row for row in rows if row.operator == operator)
    assert row.item == OPERATORS[operator]
    assert row.text != original.text
    if operator == "remove_aliases":
        assert "〔" not in row.text
    else:
        assert EXPECTED[operator] in row.text
    if operator == "second_question":
        assert row.text.count("？") == 2


@pytest.mark.parametrize(
    "operator",
    [
        "wrong_city",
        "wrong_chart",
        "wrong_weekday",
        "shift_date",
        "reverse_element",
        "generic_personality",
    ],
)
def test_missing_anchor_refuses_to_pad_a_label(operator):
    replacements = dict(clean().replacements)
    del replacements[operator]
    with pytest.raises(
        ValueError, match=f"insufficient eligible clean samples for {operator}"
    ):
        generate_defects(
            [replace(clean(i), replacements=replacements) for i in range(10)], seed=1
        )


@pytest.mark.parametrize(
    "text", ["无证据也没有问题。", "无问句〔c1〕", "两个问题？真的吗？〔c1〕"]
)
def test_missing_alias_or_exactly_one_question_is_not_faked(text):
    rows = [CleanSample(f"synthetic_{i}", text, True) for i in range(10)]
    with pytest.raises(ValueError, match="insufficient eligible"):
        generate_defects(rows, seed=1)


@pytest.mark.parametrize("seed,count", [(True, 10), (1, 9), (1, True), (1.5, 10)])
def test_generation_configuration_is_strict(seed, count):
    with pytest.raises(ValueError):
        generate_defects([clean(i) for i in range(10)], seed=seed, per_operator=count)


def test_unique_sources_and_clean_attestation_are_required():
    with pytest.raises(ValueError, match="duplicate"):
        generate_defects([clean()] * 10, seed=1)
    with pytest.raises(ValueError, match="explicitly verified"):
        replace(clean(), verified_clean=False)
    with pytest.raises(ValueError, match="present distinct"):
        replace(clean(), replacements={"wrong_city": ("missing", "wrong")})
    assert "甲木" not in repr(clean())
    assert "甲木" not in repr(
        generate_defects([clean(i) for i in range(10)], seed=1)[0]
    )


@pytest.mark.parametrize("questions", ["没有问句。", "还有问题？确定吗？"])
def test_second_question_requires_exactly_one_original_question(questions):
    rows = [
        replace(clean(i), text=clean(i).text.replace("你愿意先试一步吗？", questions))
        for i in range(10)
    ]
    with pytest.raises(ValueError, match="for second_question"):
        generate_defects(rows, seed=1)


def test_alias_operator_requires_real_aliases_after_other_anchors_remain_valid():
    rows = []
    for i in range(10):
        original = clean(i)
        pairs = {
            key: (old.replace("〔c3〕", "").replace("〔c4〕", ""), new)
            for key, (old, new) in original.replacements.items()
        }
        text = original.text
        for alias in ("〔c3〕", "〔c4〕", "〔m1〕", "〔p1〕"):
            text = text.replace(alias, "")
        rows.append(replace(original, text=text, replacements=pairs))
    with pytest.raises(ValueError, match="for remove_aliases"):
        generate_defects(rows, seed=1)
