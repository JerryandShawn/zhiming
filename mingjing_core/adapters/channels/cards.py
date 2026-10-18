"""Envelope-only card builders. 外部JSON字段均为候选，待对照飞书官方文档核实。"""

import re
from collections.abc import Sequence
from datetime import date

from mingjing_core.adapters.channels.card_elements import (
    CardJSON,
    action_button,
    card,
    folded,
    link_button,
    literal,
    markdown,
    receipt_elements,
    route_elements,
)
from mingjing_core.adapters.channels.cards_contracts import (
    BriefSection,
    CardAction,
    ReceiptLine,
    RouteLabel,
    app_url,
    text_value,
)
from mingjing_core.application.followups_rules import safe_preview


def answer_card(
    text: str,
    *,
    streaming: bool = False,
    status: str | None = None,
    evidence: str = "",
    receipts: Sequence[ReceiptLine] = (),
    route: RouteLabel | None = None,
    open_url: str | None = None,
) -> CardJSON:
    text_value(text, empty=streaming)
    text_value(evidence, empty=True)
    app_url(open_url)
    if type(streaming) is not bool or (streaming and (evidence or receipts or route or open_url)):
        raise ValueError("流式占位卡不能混入最终回执或操作")
    elements = []
    if streaming:
        elements.append(markdown(text_value(status or "明镜正在回复…", maximum=300), "status"))
    if len(text) > 1500 and not streaming:
        elements.extend(
            [markdown(text[:1200] + "\n完整回答见下方。", "answer"), folded(text, "完整回答", "answer_full")]
        )
    else:
        elements.append(markdown(text, "answer"))
    if evidence:
        elements.append(folded(evidence, "命理依据", "evidence"))
    elements.extend(receipt_elements(receipts))
    if route:
        elements.extend(route_elements(route))
    if open_url:
        elements.append(link_button("在明镜台打开", open_url))
    return card("明镜", elements, preview="明镜正在回复…" if streaming else "明镜回复了你", streaming=streaming)


def question_card(
    question: str, *, why: str, options: Sequence[CardAction], selected_label: str | None = None
) -> CardJSON:
    text_value(question, maximum=2000)
    text_value(why, maximum=1000)
    if len(options) > 4 or len({action.label for action in options}) != len(options):
        raise ValueError("提问至多包含四个不同选项")
    elements = [markdown(f"**{literal(question)}**\n为什么问：{literal(why)}", "question")]
    if selected_label is not None:
        if selected_label not in {action.label for action in options}:
            raise ValueError("已选项不在本次问题中")
        elements.append(markdown(f"你选了：{literal(selected_label)}", "selected"))
    else:
        elements.extend(action_button(action) for action in options)
        elements.append(markdown("我自己说：也可以直接打字告诉我。", "free_reply"))
    return card("明镜想问你", elements, preview="明镜想问问你")


def memory_receipt_card(receipts: Sequence[ReceiptLine], *, open_url: str | None = None) -> CardJSON:
    if not receipts:
        raise ValueError("记忆卡需要真实回执")
    elements = receipt_elements(receipts)
    if open_url is not None:
        elements.append(link_button("在明镜台打开", open_url))
    return card("明镜", elements, preview="明镜有一条记忆回执")


def proposal_card(summary: str, *, remember_token: str, decline_token: str, always_token: str) -> CardJSON:
    elements = [markdown("这个比较私人，要不要我记住？\n> " + literal(text_value(summary, maximum=2000)), "proposal")]
    elements.extend(
        action_button(action)
        for action in [
            CardAction("记住", remember_token, True),
            CardAction("不用", decline_token),
            CardAction("以后这类都记", always_token),
        ]
    )
    return card("明镜", elements, preview="明镜有一件事想和你确认")


def followup_card(
    text: str, *, replies: Sequence[CardAction] = (), category: str = "", sensitive: bool = False
) -> CardJSON:
    text_value(text, maximum=2000)
    sentences = [part for part in re.split(r"[。！？!?]+|\n+", text) if part.strip()]
    if not 1 <= len(sentences) <= 3 or (replies and len(replies) not in {2, 3}):
        raise ValueError("跟进卡需要一至三句话及可选二至三个快捷回复")
    if type(sensitive) is not bool:
        raise ValueError("敏感标志必须明确")
    elements = [markdown(text, "followup"), *(action_button(action) for action in replies)]
    preview = safe_preview(text, category, proactive=True, sensitive=sensitive)
    return card("明镜", elements, preview=preview[:160])


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
    if type(day) is not date:
        raise ValueError("晨报需要owner本地日期")
    values = [("今日", calendar), ("你的安排", plans), ("今日流日一句", daily_flow)]
    elements = [
        markdown(f"**{label}**\n{text_value(value, maximum=4000)}", f"brief_{index}")
        for index, (label, value) in enumerate(values)
    ]
    if len({section.space for section in sections}) != len(sections):
        raise ValueError("晨报分区重复")
    elements.extend(
        markdown(f"**{literal(section.space)}**\n" + "\n".join(section.lines), f"space_{index}")
        for index, section in enumerate(sections)
    )
    elements.append(markdown(text_value(closing, maximum=1000), "closing"))
    if sum(len(element["content"]) for element in elements) > 1500:
        elements = [
            markdown(calendar[:300], "brief_date"),
            folded("\n\n".join(element["content"] for element in elements), "完整晨报", "brief_full"),
        ]
    if open_url:
        elements.append(link_button("和明镜聊聊", open_url))
    else:
        elements.append(markdown("想聊聊，直接回复我就好。", "reply"))
    weekday = "一二三四五六日"[day.weekday()]
    return card(f"{day.month}月{day.day}日 周{weekday} · 晨报", elements, preview="明镜的晨报到了")


def route_card(route: RouteLabel) -> CardJSON:
    return card("明镜", route_elements(route), preview="对话归属")
