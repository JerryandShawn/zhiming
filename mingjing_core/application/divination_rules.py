"""Thread-scoped recurrence signals only; no inference, draw, persistence or model call."""

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

from mingjing_core.timekit.clock import Clock


@dataclass(frozen=True)
class DivinationScope:
    owner_id: str
    subject_id: str
    thread_id: str

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (self.owner_id, self.subject_id, self.thread_id)
        ):
            raise ValueError("占卜计数需要明确归属和线程")


@dataclass(frozen=True)
class DivinationTurn:
    id: str
    scope: DivinationScope
    at: datetime
    text: str = field(repr=False)
    topic_tag: str | None = None
    fate_query: bool | None = None
    reference_alias: str | None = None
    active: bool = True
    source_revoked: bool = False

    def __post_init__(self) -> None:
        _instant(self.at)
        if (
            not isinstance(self.id, str)
            or not self.id.strip()
            or not isinstance(self.text, str)
            or not isinstance(self.scope, DivinationScope)
        ):
            raise ValueError("占卜计数输入无效")
        if self.fate_query is not None and type(self.fate_query) is not bool:
            raise ValueError("命运类标签必须为明确布尔值")
        if type(self.active) is not bool or type(self.source_revoked) is not bool:
            raise ValueError("来源状态必须为明确布尔值")
        if self.topic_tag is not None and (
            not isinstance(self.topic_tag, str) or not self.topic_tag.strip() or len(self.topic_tag) > 200
        ):
            raise ValueError("主题标签无效")
        if self.reference_alias is not None and not re.fullmatch(
            r"[A-Za-z][A-Za-z0-9:_-]{0,120}", self.reference_alias
        ):
            raise ValueError("已有档案引用必须是有效别名")


@dataclass(frozen=True)
class RepetitionDecision:
    occurrence: int
    mode: Literal["normal", "repeat", "reframe"]
    topic_key: str
    topic_source: Literal["rule", "label"]
    l3_hint: str
    reference_alias: str | None
    allow_new_conclusion: bool
    expose_tarot_start: bool
    max_questions: int = 1
    max_actions: int = 2


def _instant(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("占卜时间需要时区")
    return value.astimezone(UTC)


def is_fate_query(text: str) -> bool:
    if re.search(r"(?:不想|不要|不需要|不用|不再)(?:再)?(?:占卜|抽牌|算命|塔罗)", text):
        return False
    if re.search(r"占卜|抽牌|算命|运势|命运|再抽一次|塔罗.{0,8}(?:问|看|抽)", text):
        return True
    return bool(
        re.search(r"会不会|能不能|是否会|是不是会", text)
        and re.search(r"回来|复合|联系|面试|成功|感情|跳槽|录用|结婚|升职|财运", text)
    )


def _topic(turn: DivinationTurn) -> tuple[str, Literal["rule", "label"]]:
    if turn.topic_tag is not None:
        raw, source = turn.topic_tag.strip(), "label"
    else:
        raw = re.sub(r"[\W_]+", "", turn.text.casefold())
        if re.search(r"回来|复合|联系我|找我", raw):
            actor = re.split(r"还|到底|会不会|能不能|是否|会|回来|复合|联系|找我", raw, maxsplit=1)[0]
            raw = "relationship_return:" + actor
        else:
            raw = re.sub(r"(?:请|帮我|我想|再问|再算|再抽|会不会|能不能|是不是|到底|这次|一次|一下|吗|呢)", "", raw)
        source = "rule"
    return hashlib.sha256(raw.encode()).hexdigest()[:32], source


def repetition_decision(
    current: DivinationTurn, history: Sequence[DivinationTurn], *, clock: Clock
) -> RepetitionDecision:
    now = _instant(clock.now())
    if not current.active or current.source_revoked or _instant(current.at) > now:
        raise ValueError("当前来源无效或时间超前")
    topic, source = _topic(current)
    eligible = current.fate_query if current.fate_query is not None else is_fate_query(current.text)
    if not eligible:
        return RepetitionDecision(0, "normal", topic, source, "", None, True, True)
    seen: dict[str, DivinationTurn] = {current.id: current}
    versions: dict[str, DivinationTurn] = {current.id: current}
    for turn in history:
        if turn.scope != current.scope or not turn.active or turn.source_revoked:
            continue
        if not timedelta(0) <= now - _instant(turn.at) < timedelta(hours=24):
            continue
        if turn.id in versions and turn != versions[turn.id]:
            raise ValueError("同一来源标识发生冲突")
        versions[turn.id] = turn
        if _topic(turn)[0] == topic and (turn.fate_query if turn.fate_query is not None else is_fate_query(turn.text)):
            seen[turn.id] = turn
    count = len(seen)
    prior = sorted((turn for turn in seen.values() if turn.id != current.id), key=lambda turn: _instant(turn.at))
    reference = next((turn.reference_alias for turn in reversed(prior) if turn.reference_alias), None)
    if count >= 3:
        return RepetitionDecision(count, "reframe", topic, source, "用户可能在焦虑", reference, False, False)
    if count == 2:
        return RepetitionDecision(
            count, "repeat", topic, source, "同一问题第2次；先复用档案或牌面，询问新情况", reference, False, True
        )
    return RepetitionDecision(count, "normal", topic, source, "", None, True, True)
