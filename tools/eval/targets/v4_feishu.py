"""Actual durable Feishu intake and exactly-once delivery, with a local transport."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.adapters.feishu_gateway import FeishuGateway
from mingjing_core.timekit.clock import FrozenClock, get_clock
from mingjing_core.timekit.timestamps import history_instant

from .v4_observations import delivery_rows


class FeishuBatchDriver:
    def __init__(self, target: Any) -> None:
        self.target = target
        self.inbound_ids: list[str] = []
        self.sent: list[tuple[Any, ...]] = []
        self.proof: dict[str, Any] = {}
        self.gateway = FeishuGateway(target.service, self._transport)

    def _transport(self, *args: Any) -> str:
        self.sent.append(args)
        return "om_syntheticEvalReceipt"

    def _event(self, row: dict[str, Any]) -> dict[str, Any]:
        stamp = datetime.fromisoformat(row["at"])
        if stamp.tzinfo is None:
            raise ValueError("Synthetic native Feishu timestamp must be aware")
        return {
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "sender": {
                    "sender_type": "user",
                    "sender_id": {"open_id": "ou_syntheticEval"},
                },
                "message": {
                    "chat_type": "p2p",
                    "message_type": "text",
                    "message_id": row["id"],
                    "chat_id": "oc_syntheticEval",
                    "create_time": str(int(stamp.timestamp() * 1000)),
                    "content": json.dumps({"text": row["content"]}, ensure_ascii=False),
                },
            },
        }

    def _input_rows(self, turn: dict[str, Any] | None) -> list[dict[str, Any]]:
        if turn is not None:
            return [
                {
                    "id": f"fs-{self.target.seed['_scenario_id']}-{turn['_index']}",
                    "at": get_clock().now().isoformat(),
                    "content": turn["user"],
                }
            ]
        if self.target.seed["controls"].get("debounce_seconds") != 2.5:
            raise ValueError("Batch fixture must exercise the actual 2500ms contract")
        return self.target.seed["controls"]["inbound_batch"]

    def prepare(self, turn: dict[str, Any] | None = None) -> dict[str, Any]:
        target, clock = self.target, get_clock()
        if not isinstance(clock, FrozenClock):
            raise ValueError("Batch evaluation requires a frozen synthetic clock")
        rows = self._input_rows(turn)
        if not rows:
            raise ValueError("Batch fixture must exercise the actual 2500ms contract")
        target.repo.bind_channel(target.owner, "feishu", "ou_syntheticEval")
        with target.repo.transaction(target.owner) as connection:
            settings = dict(target.repo.assert_scope(target.owner)["settings"], runtime="v4")
            connection.execute(
                sql.SQL("UPDATE {} SET settings=%s WHERE id=%s").format(target.repo.table("core_owners")),
                (Jsonb(settings), target.owner),
            )
        start = clock.now()
        for row in rows:
            at = history_instant(row["at"])
            if not start <= at < start + timedelta(milliseconds=2500) or at < clock.now():
                raise ValueError("Synthetic batch is outside the first fixed intake window")
            clock.advance(at - clock.now())
            accepted = self.gateway.accept(self._event(row))
            if accepted["run_id"] is not None or target.port.calls or self.sent:
                raise AssertionError("Gateway executed work before the debounce boundary")
            self.inbound_ids.append(accepted["inbound_id"])
        clock.advance(start + timedelta(milliseconds=2500) - clock.now())
        queued = self.gateway.ingress.flush(target.owner, self.inbound_ids[0])
        run = target.repo.fetch_run(target.owner, queued["run_id"])
        if run["runtime"] != "v4" or run["status"] != "queued":
            raise AssertionError("Verified native intake did not pin a queued v4 run")
        if turn is not None:
            target.bindings[f"turn-{turn['_index']}"] = run["request"]["source_message_id"]
        self.proof = self._observe(run)
        return target.repo.claim_run(target.owner, run["id"], lease_seconds=150)

    def _observe(self, run: dict[str, Any]) -> dict[str, Any]:
        target = self.target
        sources = [target.repo.get(target.owner, "message", ident) for ident in run["request"]["source_message_ids"]]
        with target.repo.transaction(target.owner) as connection:
            count = connection.execute(
                sql.SQL("SELECT count(*) AS n FROM {} WHERE owner=%s").format(target.repo.table("core_runs")),
                (target.owner,),
            ).fetchone()["n"]
        return {
            "source_store": "core_runs.request + independently persisted native messages",
            "run_id": run["id"],
            "run_count": count,
            "input_message_ids": [row["source_id"] for row in sources],
            "source_segments": run["request"]["source_segments"],
            "source_segments_count": len(run["request"]["source_segments"]),
            "distinct_timestamps": len({row["at"] for row in sources}),
            "sent_count": len(self.sent),
        }

    def finish(self, run_id: str) -> list[dict[str, Any]]:
        target = self.target

        async def deliver() -> None:
            for ident in self.inbound_ids * 2:
                receipt = await self.gateway.process(target.owner, ident)
                if receipt["status"] != "sent":
                    raise AssertionError("Committed synthetic delivery did not reach sent")

        asyncio.run(deliver())
        run = target.repo.fetch_run(target.owner, run_id)
        self.proof = self._observe(run)
        users = [row.content for row in target.port.requests[0]["messages"] if row.role == "user"]
        sources = [target.repo.get(target.owner, "message", ident) for ident in run["request"]["source_message_ids"]]
        self.proof["all_input_messages_present"] = all(row["content"] in users for row in sources)
        self.proof["external_channel_sends"] = 0
        persisted = [row for row in delivery_rows(target.repo, target.owner) if row["data"]["run_id"] == run_id]
        if len(persisted) != 1 or persisted[0]["status"] != "sent" or len(self.sent) != 1:
            raise AssertionError("Native gateway must persist exactly one locally delivered outbox")
        return [
            {
                "name": "delivery.sent",
                "source_store": "delivery_outbox + injected local transport receipt",
                "run_id": run_id,
                "outbox_id": persisted[0]["id"],
                "local_transport_sends": len(self.sent),
                "external_channel_sends": 0,
                "rule": "succeeded native Feishu run; duplicate process calls reuse the sent outbox",
            }
        ]
