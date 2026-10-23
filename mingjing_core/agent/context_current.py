"""Native source identities accompany current user messages for verifiable tool writes."""

import json
from typing import Any

from mingjing_core.models.port import ChatMessage

from .context_types import ContextItem, ContextLayer, SourceSnapshot


def current_layer(snapshot: SourceSnapshot, aliases: Any) -> ContextLayer:
    rows = snapshot.extra_entities.get("turn_sources") or (snapshot.current,)
    items = []
    for row in rows:
        provenance = dict(
            source_message_id=row["id"],
            alias=aliases.add("m", "message", row),
            at=row.get("at"),
            channel=row.get("channel"),
            revision=row["revision"],
        )
        items.append(
            ContextItem(
                row["id"],
                (
                    ChatMessage("system", "本轮用户原话的程序来源标识：" + json.dumps(provenance, ensure_ascii=False)),
                    ChatMessage("user", row["content"]),
                ),
                True,
            )
        )
    return ContextLayer("L6", tuple(items))
