"""SSE presentation reducer: reset replaces text, while stale sequence replay never rolls back."""

import hashlib
import json
from dataclasses import dataclass, field, replace

from .event_models import RunEvent, RunScope, event_data
from .stream_clock import StreamStateError


@dataclass(frozen=True)
class TextProjection:
    scope: RunScope
    last_seq: int = 0
    text: str = field(default="", repr=False)
    revision_id: str | None = None
    terminal: bool = False
    waiting_user: bool = False
    last_event_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.scope, RunScope) or type(self.last_seq) is not int or self.last_seq < 0:
            raise StreamStateError("文本投影范围或序号无效")
        if not isinstance(self.text, str) or type(self.terminal) is not bool or type(self.waiting_user) is not bool:
            raise StreamStateError("文本投影状态无效")


def _fingerprint(event: RunEvent) -> str:
    body = json.dumps({"type": event.type, "data": event_data(event)}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def reduce_event(state: TextProjection, event: RunEvent, *, scope: RunScope) -> TextProjection:
    if scope != state.scope or event.run_id != scope.run_id:
        raise StreamStateError("流式事件不属于当前对话运行")
    digest = _fingerprint(event)
    if event.seq < state.last_seq:
        return state
    if event.seq == state.last_seq:
        if digest != state.last_event_fingerprint:
            raise StreamStateError("同序号的流式事件内容不一致")
        return state
    if state.terminal:
        raise StreamStateError("运行已经结束，不能继续追加事件")
    if state.waiting_user and event.type in {"text_delta", "text_reset", "ask_user", "tool_call", "tool_result"}:
        raise StreamStateError("等待用户回答时不能继续生成")
    next_state = replace(state, last_seq=event.seq, last_event_fingerprint=digest)
    if event.type == "text_delta":
        return replace(next_state, text=state.text + event.payload["text"])
    if event.type == "text_reset":
        return replace(next_state, text=event.payload["text"], revision_id=event.payload.get("revision_id"))
    if event.type == "ask_user":
        return replace(next_state, waiting_user=True)
    if event.type == "final":
        return replace(next_state, text=event.payload["envelope"]["text"], terminal=True)
    if event.type == "error":
        return replace(next_state, terminal=True)
    return next_state
