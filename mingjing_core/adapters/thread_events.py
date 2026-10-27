"""Frozen v1 SSE HTTP bridge; committed hints only wake the authoritative PG reader."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import StreamingResponse

from mingjing_core.agent.events import encode_sse, heartbeat
from .run_event_follow import RunEventFollow


def event_response(
    repo: Any, owner: str, ident: str, request: Request, after_seq: int | None = None
) -> StreamingResponse:
    follow = RunEventFollow(repo, owner, ident, request, after_seq)

    async def stream() -> Any:
        try:
            async for event in follow.events():
                yield heartbeat() if event is None else encode_sse(event)
        finally:
            follow.close()

    return follow.response(stream())
