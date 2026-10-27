"""Followup/brief/route candidate layouts with explicit preview and body budgets."""

import re
from collections.abc import Sequence
from datetime import date

from mingjing_core.adapters.channels.cards_contracts import BriefSection, CardAction, RouteLabel, app_url, text_value
from mingjing_core.application.followups_rules import safe_preview

from .budget import finish
from .elements import CardJSON, action_button, link_button, literal, markdown, route_elements


def followup_card(
    text: str,
    *,
    replies: Sequence[CardAction] = (),
    category: str = "",
    sensitive: bool = False,
) -> CardJSON:
    text_value(text, maximum=2000)
    sentences = [part for part in re.split(r"[。！？!?]+|\n+", text) if part.strip()]
    if not 1 <= len(sentences) <= 3 or (replies and len(replies) not in {2, 3}):
        raise ValueError("card_followup_shape_invalid")
    if type(sensitive) is not bool or any(not isinstance(item, CardAction) for item in replies):
        raise ValueError("card_followup_type_invalid")
    elements = [markdown(text, "followup"), *(action_button(item) for item in replies)]
    preview = safe_preview(text, category, proactive=True, sensitive=sensitive)
    return finish("明镜", elements, preview=preview[:160])


def brief_card(
    day: date,
    *,
    calendar: str,
    plans: str,
    daily_flow: str,
    closing: str,
    sections: Sequence[BriefSection] = (),
    open_url: str | None = None,
) -> CardJSON:
    if type(day) is not date or any(not isinstance(item, BriefSection) for item in sections):
        raise ValueError("card_brief_type_invalid")
    app_url(open_url)
    if len({item.space for item in sections}) != len(sections):
        raise ValueError("card_brief_duplicate_area")
    values = [("今日", calendar), ("你的安排", plans), ("今日流日一句", daily_flow)]
    elements = [
        markdown(f"**{label}**\n{text_value(value, maximum=4000)}", f"brief_{index}")
        for index, (label, value) in enumerate(values)
    ]
    elements.extend(
        markdown(f"**{literal(item.space)}**\n" + "\n".join(item.lines), f"space_{index}")
        for index, item in enumerate(sections)
    )
    elements.append(markdown(text_value(closing, maximum=1000), "closing"))
    shorten_ids = tuple(item["element_id"] for item in elements)
    if open_url is not None:
        elements.append(link_button("和明镜聊聊", open_url))
    else:
        elements.append(markdown("想聊聊，直接回复我就好。", "reply"))
    weekday = "一二三四五六日"[day.weekday()]
    return finish(
        f"{day.month}月{day.day}日 周{weekday} · 晨报", elements, preview="明镜的晨报到了", shorten_ids=shorten_ids
    )


def route_card(route: RouteLabel) -> CardJSON:
    return finish("明镜", route_elements(route), preview="对话归属")
