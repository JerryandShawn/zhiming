"""Decision, fixed-draw and consent views. Builders never make decisions or compute charts."""

from collections.abc import Sequence
from dataclasses import dataclass, field

from mingjing_core.adapters.channels.cards_contracts import CardAction, text_value

from .budget import finish
from .elements import CardJSON, action_button, literal, markdown


@dataclass(frozen=True)
class DecisionOption:
    action: CardAction = field(repr=False)
    benefits: str = field(repr=False)
    costs: str = field(repr=False)
    basis: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.action, CardAction):
            raise ValueError("decision_action_required")
        for value in (self.benefits, self.costs, self.basis):
            text_value(value, maximum=1000)


def decision_card(question: str, *, options: Sequence[DecisionOption]) -> CardJSON:
    text_value(question, maximum=2000)
    if not 2 <= len(options) <= 4 or any(
        not isinstance(row, DecisionOption) for row in options
    ):
        raise ValueError("decision_requires_two_to_four_options")
    if len({row.action.label for row in options}) != len(options):
        raise ValueError("decision_duplicate_option")
    elements = [markdown(literal(question), "decision")]
    for index, row in enumerate(options):
        content = (
            f"**{literal(row.action.label)}**\n好处：{literal(row.benefits)}\n"
            f"代价：{literal(row.costs)}\n依据：{literal(row.basis)}"
        )
        elements.extend(
            [markdown(content, f"option_{index}"), action_button(row.action)]
        )
    return finish("一起看看选项", elements, preview="明镜整理了几个选项")


def tarot_card(
    question: str,
    *,
    draw_id: str,
    draw_revision: int,
    selections: Sequence[CardAction] = (),
    revealed_cards: tuple[str, ...] = (),
) -> CardJSON:
    """Render one authoritative draw snapshot; no randomization or second draw is possible here."""
    text_value(question, maximum=2000)
    text_value(draw_id, maximum=160)
    if type(draw_revision) is not int or draw_revision < 1:
        raise ValueError("fixed_draw_revision_required")
    if not isinstance(revealed_cards, tuple) or any(
        not isinstance(row, CardAction) for row in selections
    ):
        raise ValueError("fixed_draw_view_invalid")
    if (
        bool(selections) == bool(revealed_cards)
        or len(selections) > 4
        or len(revealed_cards) > 3
    ):
        raise ValueError("fixed_draw_select_or_reveal_required")
    elements = [markdown(literal(question), "tarot_question")]
    if selections:
        if len({row.label for row in selections}) != len(selections):
            raise ValueError("fixed_draw_duplicate_selection")
        elements.append(markdown("牌已固定，请选择牌背。", "tarot_state"))
        elements.extend(action_button(row) for row in selections)
    else:
        for index, value in enumerate(revealed_cards):
            text_value(value, maximum=1000)
            elements.append(markdown(literal(value), f"revealed_{index}"))
    return finish("明镜 · 塔罗", elements, preview="明镜有一条牌面进展")


def synastry_confirmation_card(
    *,
    first_label: str,
    second_label: str,
    purpose: str,
    confirm: CardAction,
    decline: CardAction,
) -> CardJSON:
    """Opaque action capabilities bind actual consent scope in the host; no third-party birth data is rendered."""
    for value in (first_label, second_label):
        text_value(value, maximum=80)
    text_value(purpose, maximum=1000)
    if not isinstance(confirm, CardAction) or not isinstance(decline, CardAction):
        raise ValueError("synastry_consent_actions_required")
    if confirm.label == decline.label:
        raise ValueError("synastry_consent_choices_must_differ")
    text = (
        f"确认本次合盘：{literal(first_label)}与{literal(second_label)}。\n"
        f"用途：{literal(purpose)}\n只在你确认本次用途后继续，也可以选择不继续。"
    )
    elements = [
        markdown(text, "synastry_consent"),
        action_button(confirm),
        action_button(decline),
    ]
    return finish("合盘前请你确认", elements, preview="明镜有一项授权请你确认")
