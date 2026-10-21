"""Frozen v1 SSE HTTP bridge; committed hints only wake the authoritative PG reader."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import Request
from fastapi.responses import StreamingResponse

from mingjing_core.agent.events import encode_sse, heartbeat
from mingjing_core.application.run_event_read import RunEventReader

from .event_cursor import header_cursors, resolve_event_cursor


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
    repo: Any, owner: str, ident: str, request: Request, after_seq: int | None = None
) -> StreamingResponse:
    # GET has already resolved its raw query aliases. Legacy POST only has this header.
    after = resolve_event_cursor(
        header_cursors(request.headers), trusted_after_seq=after_seq
    )
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
