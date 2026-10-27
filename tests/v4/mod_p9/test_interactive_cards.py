from copy import deepcopy

import pytest

from mingjing_core.adapters.channels.cards_contracts import CardAction
from mingjing_core.adapters.channels.cards_official_v3 import validate_card
from mingjing_core.adapters.channels.cards_official_v3.interactive import (
    DecisionOption,
    decision_card,
    synastry_confirmation_card,
    tarot_card,
)


def action(index, label=None):
    return CardAction(label or f"合成选项{index}", f"synthetic_token_{index:032d}")


def option(index):
    return DecisionOption(action(index), "合成好处", "合成代价", "已提供的依据〔m1〕")


@pytest.mark.parametrize("count", [2, 3, 4])
def test_decision_card_preserves_tradeoffs_without_selecting_for_user(count):
    rows = [option(i) for i in range(count)]
    before = deepcopy(rows)
    card = decision_card("合成问题", options=rows)
    assert validate_card(card) == card and rows == before
    assert (
        len([row for row in card["body"]["elements"] if row["tag"] == "button"])
        == count
    )
    assert all(not row.action.primary for row in rows)


@pytest.mark.parametrize("count", [0, 1, 5])
def test_invalid_decision_option_counts_fail_closed(count):
    with pytest.raises(ValueError):
        decision_card("合成问题", options=[option(i) for i in range(count)])


def test_fixed_draw_selection_and_reveal_have_only_opaque_callback_values():
    select = tarot_card(
        "合成牌题",
        draw_id="synthetic-draw",
        draw_revision=1,
        selections=[action(1, "牌背一"), action(2, "牌背二")],
    )
    revealed = tarot_card(
        "合成牌题",
        draw_id="synthetic-draw",
        draw_revision=2,
        revealed_cards=("固定牌一·正位", "固定牌二·逆位"),
    )
    for card in (select, revealed):
        assert validate_card(card) == card
        for row in card["body"]["elements"]:
            if row["tag"] == "button":
                assert set(row["behaviors"][0]["value"]) == {"t"}
    assert not any(row["tag"] == "button" for row in revealed["body"]["elements"])


@pytest.mark.parametrize("revision", [0, True, 1.0])
def test_fixed_draw_version_is_exact_integer(revision):
    with pytest.raises(ValueError):
        tarot_card(
            "问题", draw_id="draw", draw_revision=revision, selections=[action(1)]
        )


def test_draw_rejects_mixed_stages_and_consent_does_not_disclose_private_context_in_preview():
    with pytest.raises(ValueError):
        tarot_card(
            "问题",
            draw_id="draw",
            draw_revision=1,
            selections=[action(1)],
            revealed_cards=("牌一",),
        )
    card = synastry_confirmation_card(
        first_label="合成甲",
        second_label="合成乙",
        purpose="合成私人用途",
        confirm=action(1, "同意本次用途"),
        decline=action(2, "不用了"),
    )
    assert "合成私人用途" not in card["config"]["summary"]["content"]
    assert validate_card(card) == card


def test_duplicate_capabilities_fail_closed_for_all_card_types():
    with pytest.raises(ValueError):
        decision_card("问题", options=[option(1), option(1)])
    with pytest.raises(ValueError):
        tarot_card(
            "问题", draw_id="draw", draw_revision=1, selections=[action(1), action(1)]
        )
    with pytest.raises(ValueError):
        synastry_confirmation_card(
            first_label="甲",
            second_label="乙",
            purpose="合成用途",
            confirm=action(1),
            decline=CardAction("不用", action(1).token),
        )
