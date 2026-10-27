"""One authorized PG follow loop serves both frozen and legacy SSE encoders."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import Request
from fastapi.responses import StreamingResponse

from mingjing_core.application.run_event_read import RunEventReader

from .event_cursor import header_cursors, resolve_event_cursor


class _FollowResponse(StreamingResponse):
    def __init__(self, body: Any, follow: RunEventFollow) -> None:
        super().__init__(
            body,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
        self.follow = follow

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.follow.close()


class RunEventFollow:
    def __init__(
        self,
        repo: Any,
        owner: str,
        ident: str,
        request: Request,
        after_seq: int | None = None,
    ) -> None:
        # GET aliases are resolved by its route; POST retains only the original header.
        self.after = resolve_event_cursor(
            header_cursors(request.headers), trusted_after_seq=after_seq
        )
        self.reader, self.request = RunEventReader(repo, owner, ident), request
        self.reader.validate_cursor(self.after)
        self.subscription = self._subscribe(repo, owner, ident)
        self.finished = False

    def _subscribe(self, repo: Any, owner: str, ident: str) -> Any:
        app = getattr(self.request, "scope", {}).get("app")
        state = getattr(getattr(app, "state", None), "core", {})
        service = state.get("event_hints") if isinstance(state, dict) else None
        return service.subscribe(repo, owner, ident) if service is not None else None

    def close(self) -> None:
        if self.subscription is not None:
            self.subscription.close()

    def response(self, body: Any) -> StreamingResponse:
        return _FollowResponse(body, self)

    async def events(self) -> AsyncIterator[dict[str, Any] | None]:
        cursor, last_ping = self.after, time.monotonic()
        try:
            while not await self.request.is_disconnected():
                if self.subscription is not None and self.subscription.closed:
                    return
                previous = cursor
                events, cursor, finished = await asyncio.to_thread(
                    self.reader.page, cursor
                )
                for event in events:
                    yield event
                if finished:
                    self.finished = True
                    return
                # Hints never advance the cursor, and erased rows still advance a PG page.
                if cursor > previous:
                    continue
                if time.monotonic() - last_ping >= 15:
                    yield None
                    last_ping = time.monotonic()
                if self.subscription is not None:
                    await self.subscription.wait(0.15)
                else:
                    await asyncio.sleep(0.15)
        finally:
            self.close()
