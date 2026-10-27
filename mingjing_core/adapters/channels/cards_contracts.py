"""Trusted-envelope inputs for offline candidate Feishu cards; no service or model access."""

import re
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlsplit


def text_value(value: str, *, maximum: int = 20_000, empty: bool = False) -> str:
    if (
        not isinstance(value, str)
        or (not empty and not value.strip())
        or len(value) > maximum
        or "\x00" in value
    ):
        raise ValueError("卡片文字为空或超过限制")
    return value


def token_value(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", value):
        raise ValueError("卡片操作凭证无效")
    return value


def app_url(value: str | None) -> str | None:
    if value is None:
        return None
    text_value(value, maximum=2000)
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme == "https"
            and parsed.hostname
            and not parsed.username
            and not parsed.password
        )
        valid = valid and not any(ord(char) <= 32 or ord(char) == 127 for char in value)
        _ = parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("明镜台链接需要有效的HTTPS地址")
    # Host/app allowlisting belongs to the trusted application boundary, never a model-supplied URL.
    return value


@dataclass(frozen=True)
class CardAction:
    label: str = field(repr=False)
    token: str = field(repr=False)
    primary: bool = False

    def __post_init__(self) -> None:
        text_value(self.label, maximum=40)
        token_value(self.token)
        if type(self.primary) is not bool:
            raise ValueError("按钮样式无效")


ReceiptStatus = Literal[
    "saved",
    "updated",
    "pending_confirmation",
    "stopped",
    "deleted",
    "rejected",
    "skipped",
    "failed",
    "undone",
]
RECEIPT_LABELS = {
    "saved": "记下了",
    "updated": "改好了",
    "pending_confirmation": "待你确认",
    "stopped": "已停用",
    "deleted": "已删除",
    "rejected": "这次没有记下",
    "skipped": "这次没有记下",
    "failed": "这次没有记下",
    "undone": "已撤销",
}


@dataclass(frozen=True)
class ReceiptLine:
    receipt_id: str
    status: ReceiptStatus
    summary: str = field(repr=False)
    action_token: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        text_value(self.receipt_id, maximum=160)
        text_value(self.summary, maximum=500)
        if self.status not in RECEIPT_LABELS:
            raise ValueError("记忆回执状态无效")
        if self.action_token is not None:
            token_value(self.action_token)
            if self.status not in {"saved", "updated"}:
                raise ValueError("只有真实成功写入回执可提供撤销按钮")


@dataclass(frozen=True)
class RouteLabel:
    space: str = field(repr=False)
    topic: str = field(repr=False)
    change_token: str = field(repr=False)
    new_topic_token: str = field(repr=False)

    def __post_init__(self) -> None:
        text_value(self.space, maximum=60)
        text_value(self.topic, maximum=120)
        token_value(self.change_token)
        token_value(self.new_topic_token)
        if self.change_token == self.new_topic_token:
            raise ValueError("改区与新话题需要独立操作凭证")


@dataclass(frozen=True)
class BriefSection:
    space: str = field(repr=False)
    lines: tuple[str, ...] = field(repr=False)

    def __post_init__(self) -> None:
        text_value(self.space, maximum=60)
        if not isinstance(self.lines, tuple) or not 1 <= len(self.lines) <= 30:
            raise ValueError("晨报分区内容无效")
        for line in self.lines:
            text_value(line, maximum=2000)
