"""Frozen v1 SSE HTTP bridge; does not replace the module line's future event hub."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import Request
from fastapi.responses import StreamingResponse

from mingjing_core.agent.events import encode_sse, heartbeat
from mingjing_core.application.run_event_read import RunEventReader
from mingjing_core.domain.contracts import EvidenceError


def event_response(repo: Any, owner: str, ident: str, request: Request, after_seq: int = 0) -> StreamingResponse:
    header = request.headers.get("Last-Event-ID")
    try:
        after = int(header) if header is not None else after_seq
    except (ValueError, TypeError):
        raise EvidenceError("事件游标无效") from None
    if header is not None and after_seq not in {0, after}:
        raise EvidenceError("事件游标不一致")
    reader = RunEventReader(repo, owner, ident)
    reader.validate_cursor(after)

    async def stream() -> Any:
        cursor, last_ping = after, time.monotonic()
        while not await request.is_disconnected():
            events, cursor, finished = await asyncio.to_thread(reader.page, cursor)
            for event in events:
                yield encode_sse(event)
            if finished:
                return
            if time.monotonic() - last_ping >= 15:
                yield heartbeat()
                last_ping = time.monotonic()
            await asyncio.sleep(0.15)

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
