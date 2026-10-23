"""Answer/question builders from approved typed inputs; no runtime authorization is implied."""

from collections.abc import Sequence

from mingjing_core.adapters.channels.cards_contracts import CardAction, ReceiptLine, RouteLabel, app_url, text_value

from .budget import finish
from .elements import CardJSON, action_button, link_button, literal, markdown, receipt_elements, route_elements


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
        raise ValueError("card_stream_placeholder_mixed")
    if streaming:
        # Empty initial markdown is undocumented. Keep both elements nonempty, even for empty source text.
        elements = [
            markdown(text_value(status or "明镜正在回复…", maximum=300), "status"),
            markdown(text or "正在整理回复…", "answer"),
        ]
    else:
        elements = [markdown(text, "answer")]
    if evidence:
        elements.append(markdown(evidence, "evidence"))
    elements.extend(receipt_elements(receipts))
    if route is not None:
        elements.extend(route_elements(route))
    if open_url is not None:
        elements.append(link_button("在明镜台打开", open_url))
    return finish(
        "明镜",
        elements,
        preview="明镜正在回复…" if streaming else "明镜回复了你",
        streaming=streaming,
        shorten_ids=("answer", "evidence"),
    )


def question_card(
    question: str,
    *,
    why: str,
    options: Sequence[CardAction],
    selected_label: str | None = None,
) -> CardJSON:
    text_value(question, maximum=2000)
    text_value(why, maximum=1000)
    if any(not isinstance(item, CardAction) for item in options):
        raise ValueError("card_option_type_invalid")
    if len(options) > 4 or len({item.label for item in options}) != len(options):
        raise ValueError("card_option_limit")
    elements = [markdown(f"**{literal(question)}**\n为什么问：{literal(why)}", "question")]
    if selected_label is not None:
        if selected_label not in {item.label for item in options}:
            raise ValueError("card_selected_option_invalid")
        elements.append(markdown(f"你选了：{literal(selected_label)}", "selected"))
    else:
        elements.extend(action_button(item) for item in options)
        elements.append(markdown("我自己说：也可以直接打字告诉我。", "free_reply"))
    # Questions are mandatory literal text: oversize questions reject rather than silently changing their meaning.
    return finish("明镜想问你", elements, preview="明镜想问问你")


def memory_receipt_card(receipts: Sequence[ReceiptLine], *, open_url: str | None = None) -> CardJSON:
    if not receipts:
        raise ValueError("card_receipt_required")
    elements = receipt_elements(receipts)
    if open_url is not None:
        elements.append(link_button("在明镜台打开", open_url))
    return finish("明镜", elements, preview="明镜有一条记忆回执")


def proposal_card(summary: str, *, remember_token: str, decline_token: str, always_token: str) -> CardJSON:
    elements = [markdown("这个比较私人，要不要我记住？\n> " + literal(text_value(summary, maximum=2000)), "proposal")]
    elements.extend(
        action_button(item)
        for item in (
            CardAction("记住", remember_token, True),
            CardAction("不用", decline_token),
            CardAction("以后这类都记", always_token),
        )
    )
    return finish("明镜", elements, preview="明镜有一件事想和你确认")
