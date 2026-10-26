"""Synthetic tarot setup/actions go through the existing fixed-draw service."""

from __future__ import annotations

from typing import Any

from mingjing_core.adapters.tarot import TarotService
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.models.errors import ModelUnavailable
from tools.eval.targets.v3_seed import V3Seeder


class TarotDriver:
    def __init__(self, service: ConsultationService, seeder: V3Seeder) -> None:
        self.service, self.seeder = service, seeder
        self.cards = TarotService(service.repo)
        self.ids: dict[str, str] = {}
        self.failed_reading: str | None = None
        self.retry_reading: str | None = None

    def seed(self, seed: dict[str, Any]) -> None:
        for fixture in seed.get("entities", []):
            if fixture["kind"] != "tarot_draw":
                continue
            label = fixture["id"]
            question = "合成固定牌阵 " + label
            source = self.seeder.receive({"content": question}, "draw-source:" + label)
            case = self.service.memory.create_case(
                self.seeder.owner,
                "self",
                question,
                goal=question,
                message_id=source["id"],
                operation_id="draw-case:" + label,
            )
            cards = [{"card_id": card["id"], "orientation": card["orientation"]} for card in fixture["data"]["cards"]]
            draw = self.cards.create_draw(
                self.seeder.owner,
                subject_id="self",
                case_id=case["id"],
                question=question,
                spread_id="focus1",
                draw_source="manual",
                manual_cards=cards,
                idempotency_key="draw-seed:" + label,
                context_snapshot={
                    "question_message_id": source["id"],
                    "source_refs": [{"message_id": source["id"], "version": source["revision"]}],
                },
            )["draw"]
            if fixture["status"] == "revealed":
                self.cards.reveal(self.seeder.owner, draw["id"])
            self.ids[label] = draw["id"]
        if seed.get("controls", {}).get("fail_first_tarot_explanation"):
            self._failed_explanation()

    def _failed_explanation(self) -> None:
        if len(self.ids) != 1:
            raise ValueError("Synthetic retry needs one exact seeded draw")
        draw_id = next(iter(self.ids.values()))
        reading = self.cards.begin_reading(
            self.seeder.owner,
            draw_id,
            model="scripted",
            prompt_version="core4.0",
            context_snapshot={},
            idempotency_key="v4-eval-initial-reading",
        )["reading"]
        try:
            raise ModelUnavailable()
        except ModelUnavailable:
            saved = self.cards.finish_reading(self.seeder.owner, reading["id"], error="合成供应商失败")
        if saved["status"] != "failed":
            raise ValueError("Synthetic failure was not persisted")
        self.failed_reading = reading["id"]

    def reveal(self, action: dict[str, Any]) -> str:
        label = action["draw_id"]
        ident = self.ids.get(label)
        if not ident:
            draws = self.cards.list_draws(self.seeder.owner)
            if len(draws) != 1:
                raise ValueError("A fixture draw label must resolve unambiguously")
            ident = self.ids[label] = draws[0]["id"]
        draw = self.cards.get(self.seeder.owner, ident)
        for position in action.get("positions", []):
            if draw["draw_source"] == "pick":
                back = draw["backs"][position]["back_id"]
                draw = self.cards.select(self.seeder.owner, ident, back, f"eval-select:{ident}:{position}")
        self.cards.reveal(self.seeder.owner, ident)
        return ident

    def requested(self, script: dict[str, Any]) -> str | None:
        for action in script["model"]:
            call = action.get("tool_call", {})
            if call.get("name") == "tarot_read":
                return self.ids.get(call.get("arguments", {}).get("draw_id"))
        return None

    def resume(self, run: dict[str, Any]) -> None:
        if self.failed_reading:
            self.cards.resume_reading(self.seeder.owner, self.failed_reading, run["id"])
            self.retry_reading = self.failed_reading

    def finish(self, result: dict[str, Any]) -> dict[str, Any] | None:
        if not self.retry_reading:
            return None
        reading = self.cards.finish_reading(
            self.seeder.owner, self.retry_reading, result=result, validation=result["validation"]
        )
        if reading["status"] != "success":
            raise ValueError("Synthetic reading retry did not finish")
        return {
            "name": "tarot.explanation_retried",
            "source_store": "tarot_readings.payload",
            "reading_id": reading["id"],
            "rule": "persisted failed -> running -> success; evaluator-only",
        }

    def rows(self) -> list[dict[str, Any]]:
        reverse = {ident: label for label, ident in self.ids.items()}
        rows = []
        for draw in self.cards.list_draws(self.seeder.owner):
            label = reverse.get(draw["id"], "new-draw")
            data = dict(draw, native_id=draw["id"])
            # Auto draws have selected but still face-down cards; the public view correctly hides their identity.
            data["cards"] = [
                {"id": card["card_id"], "orientation": card["orientation"]}
                for card in draw["cards"]
                if card.get("revealed") is True
            ]
            rows.append(
                {
                    "id": label,
                    "kind": "tarot_draw",
                    "status": "revealed" if draw["status"] == "ready" else "pending",
                    "data": data,
                    "source_store": "tarot_draws.payload",
                    "native_id": draw["id"],
                }
            )
        return rows
