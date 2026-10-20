"""Synthetic SDK events enter the actual PG gateway and local delivery transport."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def gateway_scenarios(factory: Callable[..., dict]) -> list[dict[str, Any]]:
    data = factory(
        "X07",
        "robustness",
        "SDK三原话合并为真实运行且本机投递一次",
        [
            {
                "user": "合并飞书入站消息",
                "channel": "feishu",
                "kind": "action",
                "action": {"type": "ingest_batch"},
                "expect": {
                    "must_include_all": ["面试", "紧张"],
                    "db": [
                        {"path": "run_meta.ingress.input_message_ids", "equals": ["fs-one", "fs-two", "fs-three"]},
                        {"path": "run_meta.ingress.run_count", "equals": 1},
                        {"path": "run_meta.ingress.sent_count", "equals": 1},
                        {"path": "run_meta.ingress.source_segments_count", "equals": 3},
                        {"path": "run_meta.ingress.distinct_timestamps", "equals": 3},
                        {"path": "run_meta.ingress.all_input_messages_present", "equals": True},
                        {"kind": "outbox", "status": "sent", "count": 1},
                    ],
                },
            }
        ],
        [[{"text": "收到：你今天有面试，而且有点紧张。我们先准备最关键的两段经历。"}]],
    )
    data["seed"]["controls"] = {
        "inbound_batch": [
            {"id": "fs-one", "at": "2026-10-17T10:30:00+08:00", "content": "我今天有面试"},
            {"id": "fs-two", "at": "2026-10-17T10:30:01+08:00", "content": "有点紧张"},
            {"id": "fs-three", "at": "2026-10-17T10:30:02+08:00", "content": "帮我准备一下"},
        ],
        "debounce_seconds": 2.5,
    }
    return [data]
