"""Offline performance jobs: real builders/capabilities/client, fake only at the wire boundary.

Run with ``python -m tools.mod_overnight.benchmark_cards`` from the repository.
Only aggregate counters are returned or printed; tokens and card bodies are not.
Timing and allocation measurements belong to the caller, not FrozenClock.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any

from mingjing_core.adapters.channels.action_tokens import ActionTokenService, MemoryActionTokenStore
from mingjing_core.adapters.channels.cardkit_client import CardKitClient
from mingjing_core.adapters.channels.cardkit_contracts import CardKitAck, CardScope
from mingjing_core.adapters.channels.cardkit_store import MemoryCardKitStore
from mingjing_core.adapters.channels.cards import (
    answer_card,
    brief_card,
    followup_card,
    memory_receipt_card,
    proposal_card,
    question_card,
    route_card,
)
from mingjing_core.adapters.channels.cards_contracts import BriefSection, CardAction, ReceiptLine, RouteLabel
from mingjing_core.timekit.clock import FrozenClock

COUNT = 1000
TOKENS = ("a" * 43, "b" * 43, "c" * 43)


def _build_one(index: int) -> dict[str, Any]:
    actions = (CardAction("选项甲", TOKENS[0]), CardAction("选项乙", TOKENS[1]))
    route = RouteLabel("家庭", "合成安排", TOKENS[1], TOKENS[2])
    receipts = (ReceiptLine("synthetic-receipt", "saved", "合成记忆摘要", TOKENS[0]),)
    match index % 7:
        case 0:
            return answer_card(
                "合成回答：先核对实际安排。",
                evidence="合成依据摘要",
                receipts=receipts,
                route=route,
                open_url="https://example.invalid/#/me",
            )
        case 1:
            return question_card("合成问题，哪项更合适？", why="确认本轮偏好", options=actions)
        case 2:
            return memory_receipt_card(receipts)
        case 3:
            return proposal_card(
                "合成私人事项待确认", remember_token=TOKENS[0], decline_token=TOKENS[1], always_token=TOKENS[2]
            )
        case 4:
            return followup_card("合成健康事项有新情况吗？", replies=actions, category="wellbeing", sensitive=True)
        case 5:
            return brief_card(
                date(2026, 10, 19),
                calendar="合成日期信息",
                plans="合成待办",
                daily_flow="象征性反思",
                closing="按自己的节奏就好。",
                sections=(BriefSection("家庭", ("合成近况",)),),
            )
        case _:
            return route_card(route)


def _builders_job() -> dict[str, int]:
    serialized_bytes = 0
    for index in range(COUNT):
        layout = _build_one(index)
        serialized_bytes += len(json.dumps(layout, ensure_ascii=False).encode("utf-8"))
    return {"cards": COUNT, "card_types": 7, "serialized_bytes": serialized_bytes}


def _tokens_job() -> dict[str, int]:
    clock = FrozenClock(datetime(2026, 10, 19, 1, tzinfo=UTC))
    store = MemoryActionTokenStore(capacity=COUNT * 2)
    service = ActionTokenService(store, clock=clock)
    executions = replays = 0
    operations = set()
    for index in range(COUNT):
        claim = {
            "owner_id": "synthetic-owner",
            "subject_id": "synthetic-subject",
            "open_id": "ou_synthetic",
            "kind": "question.answer",
            "entity_id": f"synthetic-question-{index}",
            "payload_fingerprint": hashlib.sha256(f"synthetic-revision-option-{index}".encode()).hexdigest(),
        }
        issued = service.issue(**claim)
        initial = service.consume(issued.token, **claim)
        replay = service.consume(issued.token, **claim)
        if not initial.should_execute or replay.should_execute or initial.operation_id != replay.operation_id:
            raise AssertionError("offline token lifecycle invariant failed")
        executions += initial.should_execute
        replays += replay.replayed
        operations.add(initial.operation_id)
    if len(operations) != COUNT:
        raise AssertionError("offline token operation identities collided")
    return {"issued": COUNT, "executions": executions, "replays": replays, "stored_hash_records": len(store.snapshot())}


class _Wire:
    """No transport I/O; every external method/field mapping is 待对照飞书官方文档核实。"""

    def __init__(self, clock: FrozenClock) -> None:
        self.clock = clock
        self.creates = self.sends = self.updates = self.closes = self.last_sequence = 0
        self.last_at_ms: int | None = None

    def create(self, card: Mapping[str, Any], *, operation_id: str) -> CardKitAck:
        self.creates += 1
        return CardKitAck(card_id="synthetic-card")

    def send(self, card_id: str, open_id: str, *, operation_id: str) -> CardKitAck:
        if card_id != "synthetic-card" or open_id != "ou_synthetic":
            raise AssertionError("offline card send identity mismatch")
        self.sends += 1
        self.last_at_ms = int(self.clock.now().timestamp() * 1000)
        return CardKitAck(card_id=card_id, message_id="synthetic-message")

    def _mutation(self, card_id: str, sequence: int) -> None:
        now_ms = int(self.clock.now().timestamp() * 1000)
        if (
            card_id != "synthetic-card"
            or sequence != self.last_sequence + 1
            or self.last_at_ms is None
            or not 300 <= now_ms - self.last_at_ms <= 500
        ):
            raise AssertionError("offline card mutation invariant failed")
        self.last_sequence, self.last_at_ms = sequence, now_ms

    def update(self, card_id: str, element_id: str, text: str, *, sequence: int, operation_id: str) -> CardKitAck:
        self._mutation(card_id, sequence)
        self.updates += 1
        return CardKitAck(card_id=card_id, sequence=sequence)

    def close(self, card_id: str, final_card: Mapping[str, Any], *, sequence: int, operation_id: str) -> CardKitAck:
        if final_card["config"]["streaming_mode"] is not False:  # 待对照飞书官方文档核实。
            raise AssertionError("offline final card was not explicitly closed")
        self._mutation(card_id, sequence)
        self.closes += 1
        return CardKitAck(card_id=card_id, sequence=sequence)


def _cardkit_job() -> dict[str, int | bool]:
    clock = FrozenClock(datetime(2026, 10, 19, 1, tzinfo=UTC))
    scope = CardScope("synthetic-owner", "synthetic-subject", "ou_synthetic", "synthetic-stream")
    wire = _Wire(clock)
    client = CardKitClient(scope, transport=wire, clock=clock, store=MemoryCardKitStore(), interval_ms=400)
    if client.start(answer_card("", streaming=True)).status != "streaming":
        raise AssertionError("offline card did not start")
    for index in range(COUNT):
        client.offer_text(f"合成片段 {index}")
        clock.advance(timedelta(milliseconds=400))
        if client.flush().status != "streaming":
            raise AssertionError("offline update failed")
    checkpoint = client.snapshot()
    recovered_store = MemoryCardKitStore.from_snapshot(checkpoint, scope=scope)
    recovered = CardKitClient(scope, transport=wire, clock=clock, store=recovered_store, interval_ms=400)
    clock.advance(timedelta(milliseconds=400))
    result = recovered.recover(answer_card("合成权威最终回答。"))
    if result.status != "closed" or wire.creates != 1 or wire.sends != 1 or wire.closes != 1:
        raise AssertionError("offline recovery did not close the existing card")
    return {
        "updates": wire.updates,
        "creates": wire.creates,
        "sends": wire.sends,
        "closes": wire.closes,
        "last_sequence": wire.last_sequence,
        "restored_same_card": result.checkpoint.card_id == "synthetic-card",
    }


def cases() -> list[tuple[str, Callable[[], object], int]]:
    return [
        ("cards_builders_1000", _builders_job, COUNT),
        ("cards_tokens_1000", _tokens_job, COUNT),
        ("cards_stream_recovery_1000", _cardkit_job, COUNT),
    ]


if __name__ == "__main__":
    print(json.dumps({name: job() for name, job, _ in cases()}, ensure_ascii=False, sort_keys=True))
