"""Old fetch readers consume outer data.type frames from the same PG follow loop."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import Request
from fastapi.responses import StreamingResponse

from mingjing_core.agent.events import heartbeat
from mingjing_core.application.legacy_stream_projection import LegacyStreamProjection

from .run_event_follow import RunEventFollow


def legacy_event_response(
    repo: Any, owner: str, ident: str, request: Request
) -> StreamingResponse:
    projection = LegacyStreamProjection(repo, owner, ident)
    follow = RunEventFollow(repo, owner, ident, request)

    async def stream() -> Any:
        try:
            async for event in follow.events():
                if event is None:
                    yield heartbeat()
                else:
                    for value in await asyncio.to_thread(projection.project, event):
                        payload = json.dumps(
                            value,
                            ensure_ascii=False,
                            separators=(",", ":"),
                            allow_nan=False,
                        )
                        yield f"id: {value['seq']}\ndata: {payload}\n\n"
            if follow.finished:
                yield "data: [DONE]\n\n"
        finally:
            follow.close()

    return follow.response(stream())
