"""Frozen v1 SSE HTTP bridge; committed hints only wake the authoritative PG reader."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import Request
from fastapi.responses import StreamingResponse

from mingjing_core.agent.events import encode_sse, heartbeat
from mingjing_core.application.run_event_read import RunEventReader
from mingjing_core.domain.contracts import EvidenceError


class _SubscribedResponse(StreamingResponse):
    def __init__(self, *args: Any, subscription: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.subscription = subscription

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            if self.subscription is not None:
                self.subscription.close()


def _subscribe(repo: Any, owner: str, ident: str, request: Request) -> Any:
    app = getattr(request, "scope", {}).get("app")
    state = getattr(getattr(app, "state", None), "core", {})
    service = state.get("event_hints") if isinstance(state, dict) else None
    return service.subscribe(repo, owner, ident) if service is not None else None


def event_response(
    repo: Any, owner: str, ident: str, request: Request, after_seq: int = 0
) -> StreamingResponse:
    header = request.headers.get("Last-Event-ID")
    try:
        after = int(header) if header is not None else after_seq
    except (ValueError, TypeError):
        raise EvidenceError("事件游标无效") from None
    if header is not None and after_seq not in {0, after}:
        raise EvidenceError("事件游标不一致")
    reader = RunEventReader(repo, owner, ident)
    reader.validate_cursor(after)
    subscription = _subscribe(repo, owner, ident, request)

    async def stream() -> Any:
        cursor, last_ping = after, time.monotonic()
        try:
            while not await request.is_disconnected():
                if subscription is not None and subscription.closed:
                    return
                previous = cursor
                events, cursor, finished = await asyncio.to_thread(reader.page, cursor)
                for event in events:
                    yield encode_sse(event)
                if finished:
                    return
                # Exhaust persistent pages before waiting, including intentionally erased rows.
                if cursor > previous:
                    continue
                if time.monotonic() - last_ping >= 15:
                    yield heartbeat()
                    last_ping = time.monotonic()
                if subscription is not None:
                    await subscription.wait(0.15)
                else:
                    await asyncio.sleep(0.15)
        finally:
            if subscription is not None:
                subscription.close()

    return _SubscribedResponse(
        stream(),
        subscription=subscription,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
