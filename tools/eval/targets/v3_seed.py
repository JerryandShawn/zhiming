"""Synthetic fixtures enter v3 through its existing source and fact services."""

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from mingjing_core.application.consultation import ConsultationService
from mingjing_core.domain.contracts import Fact, SourceRef
from mingjing_core.timekit import get_clock

PROFILE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "profiles.yaml"


class V3Seeder:
    def __init__(self, service: ConsultationService, owner: str, scenario: str) -> None:
        self.service = service
        self.owner = owner
        self.scenario = scenario
        self.ids: dict[str, str] = {}
        self.case_ids: list[str] = []
        self.profile_fact_ids: set[str] = set()

    def receive(self, message: dict[str, Any], source_id: str) -> dict[str, Any]:
        channel = message.get("channel", "web")
        external = None
        if channel not in {
            "web",
            "web-action",
            "synthetic",
            "migration",
            "tarot",
            "scheduled_report",
        }:
            external = "synthetic-eval-" + channel
            self.service.repo.bind_channel(self.owner, channel, external)
        role = message.get("role", "user")
        return self.service.memory.receive(
            self.owner,
            content=message.get("content", message.get("user", "")),
            channel=channel,
            source_id=source_id,
            external_id=external,
            role=role,
            at=message.get("at", get_clock().now().isoformat()),
            conversation_id=message.get("conversation_id", message.get("topic_id", "shared")),
            origin="current_user" if role == "user" else "system",
        )

    def save_fact(self, fixture: dict[str, Any], key: str) -> dict[str, Any]:
        quote = fixture.get("quote", fixture.get("content", fixture.get("summary", "")))
        source = self.receive({"content": "请保存" + quote}, "seed-fact-" + key)
        saved = self.service.memory.save_fact(
            self.owner,
            "self",
            source["id"],
            quote,
            {"relationship": "background", "habit": "preference"}.get(
                fixture.get("kind"), fixture.get("kind", "background")
            ),
            field=fixture.get("field"),
            value=fixture.get("value"),
            operation_id="seed-fact-" + key,
            valid_from=fixture.get("event_at", fixture.get("at")),
        )
        if saved.get("write_status") != "saved":
            raise ValueError("Synthetic fact could not be seeded through the v3 source contract")
        # Fixtures describe state already effective; source timestamps still remain intact.
        saved = self.service.repo.update(
            self.owner, "fact", saved["id"], {"valid_from": None}, expected_revision=saved["revision"]
        )
        self.ids[fixture.get("id", key)] = saved["id"]
        return saved

    def seed(self, seed: dict[str, Any]) -> None:
        profile = self.load_profile(seed)
        self.seed_profile(profile)
        for index, message in enumerate(seed.get("thread", [])):
            source = self.receive(message, "seed-history-" + str(index))
            if message.get("id"):
                self.ids[message["id"]] = source["id"]
        for index, fixture in enumerate(seed.get("facts", [])):
            if fixture.get("source_message_id"):
                self.seed_existing_fact(fixture)
            else:
                self.save_fact(fixture, "fact-" + str(index))
        for index, case in enumerate(seed.get("cases", [])):
            self.seed_case(case, index)
        for index, entity in enumerate(seed.get("entities", [])):
            if entity["kind"] == "case":
                self.seed_case({"id": entity["id"], **entity["data"]}, index)

    def seed_existing_fact(self, fixture: dict[str, Any]) -> None:
        source = self.service.memory.get_source(self.owner, self.ids[fixture["source_message_id"]])
        quote = fixture["quote"]
        if source["role"] != "user" or quote not in source["content"]:
            raise ValueError("Initial synthetic facts must reference an exact user-source range")
        start = source["content"].index(quote)
        reference = SourceRef(
            message_id=source["id"], version=source["revision"], start=start, end=start + len(quote), quote=quote
        )
        kind = {"relationship": "background", "habit": "preference"}.get(fixture["kind"], fixture["kind"])
        fact = Fact(
            id=fixture["id"],
            owner_user_id=self.owner,
            kind=kind,
            content=quote,
            source_refs=[reference],
            assertion_status="user_confirmed",
            consent="granted",
            status=fixture.get("status", "active"),
            valid_from=None,
        )
        # Initial fixtures declare existing consent; runtime writes still use the unmodified memory service.
        self.service.repo.put(
            self.owner,
            "fact",
            fact.id,
            fact.model_dump(mode="json"),
            expected_revision=0,
            operation_id="seed-existing-fact-" + fact.id,
        )
        self.ids[fixture["id"]] = fact.id

    @staticmethod
    def load_profile(seed: dict[str, Any]) -> dict[str, Any]:
        profiles = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
        profiles = profiles.get("profiles", profiles)
        key = seed.get("profile", "default_synthetic")
        if key not in profiles:
            raise ValueError("Unknown synthetic profile")
        profile = deepcopy(profiles[key])
        overrides = seed.get("profile_overrides", {})
        for field, value in overrides.items():
            if isinstance(value, dict) and isinstance(profile.get(field), dict):
                profile[field].update(value)
            else:
                profile[field] = value
        return profile

    def seed_profile(self, profile: dict[str, Any]) -> None:
        before = set(self.ids.values())
        fields = {key: profile[key] for key in ("name", "gender") if key in profile}
        if "gender" in fields:
            fields["gender"] = {"male": "男", "female": "女"}.get(fields["gender"], fields["gender"])
        if "nickname" in profile and "name" not in fields:
            fields["name"] = profile["nickname"]
        fields.update(self.birth_fields(profile.get("birth", {})))
        for index, (field, value) in enumerate(fields.items()):
            self.save_fact(
                {
                    "kind": "profile",
                    "content": f"{field}：{value}",
                    "field": field,
                    "value": value,
                },
                "profile-" + str(index),
            )
        for key in ("occupation", "residence", "goal", "preference"):
            if profile.get(key):
                self.save_fact(
                    {"content": str(profile[key]), "kind": "background"},
                    "profile-" + key,
                )
        for index, preference in enumerate(profile.get("preferences", [])):
            self.save_fact(
                {"content": preference, "kind": "preference"},
                "preference-" + str(index),
            )

        for index, goal in enumerate(profile.get("goals", [])):
            self.save_fact({"content": goal, "kind": "goal"}, "goal-" + str(index))
        self.profile_fact_ids.update(set(self.ids.values()) - before)

    @staticmethod
    def birth_fields(birth: dict[str, Any]) -> dict[str, Any]:
        if not birth:
            return {}
        result = {"birth.precision": birth.get("precision", "exact")}
        if birth.get("date"):
            nominal = str(birth["date"])
            if birth.get("time") and result["birth.precision"] != "unknown":
                nominal += " " + birth["time"]
            result["birth.solar_datetime"] = nominal
        if result["birth.precision"] == "unknown":
            result["birth.time_unknown"] = True
        for fixture_key, field in (
            ("longitude", "location.lng"),
            ("latitude", "location.lat"),
            ("city", "location.city"),
            ("timezone_offset", "timezone_offset"),
            ("solar_datetime", "solar_datetime"),
            ("interval_start", "interval_start"),
            ("interval_end", "interval_end"),
        ):
            if fixture_key in birth:
                result["birth." + field] = birth[fixture_key]
        if birth.get("timezone") == "Asia/Shanghai" and "birth.timezone_offset" not in result:
            result["birth.timezone_offset"] = 8
        return result

    def seed_case(self, case: dict[str, Any], index: int) -> None:
        goal = case.get("goal", case.get("state", {}).get("goal", ""))
        source_ids = [self.ids[ident] for ident in case.get("source_ids", [])]
        source = (
            self.service.memory.get_source(self.owner, source_ids[0])
            if source_ids
            else self.receive({"content": goal or case["title"]}, "seed-case-" + str(index))
        )
        saved = self.service.memory.create_case(
            self.owner,
            "self",
            case["title"],
            goal=goal,
            message_id=source["id"],
            case_id=case.get("id"),
            operation_id="seed-case-" + str(index),
            conversation_id="shared",
        )
        self.case_ids.append(saved["id"])
        events = case.get("events", case.get("state", {}).get("events", []))
        if events or source_ids:
            sources = [self.service.memory.get_source(self.owner, ident) for ident in source_ids]
            self.service.repo.update(
                self.owner,
                "case",
                saved["id"],
                {
                    "state": {**saved["state"], "events": events},
                    "source_refs": [{"message_id": item["id"], "version": item["revision"]} for item in sources]
                    if sources
                    else saved["source_refs"],
                },
                expected_revision=saved["revision"],
            )
