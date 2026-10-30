"""P8 acceptance support for the real v4 target (contracts/p8_acceptance_20261027/README.md).

Seeds confirmed profiles and the one-use consent ledger through the actual services, maps the
declared semantic tool arguments onto the registered signatures, and derives the
``p8_acceptance`` observations from native run steps and entity revisions, never from the
scenario's scripted ``db`` declarations.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from psycopg import sql

from mingjing_core.application.memory import MemoryService
from mingjing_core.application.synastry_consent import SynastryConsentService

P8_TOOLS = ("chart_compute", "daily_transit", "window_search", "almanac", "synastry")
# Strict mapping of native refusal codes onto the README's structured codes; nothing else maps.
REFUSALS = {
    "invalid_arguments": "INVALID_ARGUMENT",
    "invalid_tool_request": "INVALID_ARGUMENT",
    "CONSENT_REQUIRED": "CONSENT_REQUIRED",
}
# Run-scoped or audited-separately kinds; everything else in core_entities is long-term.
TRANSIENT_KINDS = frozenset(
    {"message", "runtime_step", "model_call", "synastry_consent", "thread", "session", "request", "delivery"}
)
OTHER_SUBJECT = "synthetic-xiaohe"
# P8SY02 chart_b; also used when a scenario declares the ledger absent but the person exists.
DEFAULT_OTHER_CHART = {
    "date": "1995-08-27",
    "reported_time": "14:10",
    "gender": "女",
    "place": {"lon": 120.15, "lat": 30.28, "tz": "Asia/Shanghai"},
    "clock_basis": "clock",
    "precision": "reported",
}


def active(seed: dict[str, Any]) -> bool:
    return isinstance(seed.get("controls", {}).get("p8_acceptance"), dict)


def map_scripted(seed: dict[str, Any]) -> list[dict[str, Any]]:
    """Declared semantic arguments -> registered signatures (README: 主线装配映射)."""
    scripted = deepcopy(seed.get("_scripted", []))
    if not active(seed):
        return scripted
    fixture = seed["controls"]["p8_acceptance"].get("consent_fixture", {})
    other = fixture.get("subject_b", OTHER_SUBJECT)
    for step in scripted:
        # result/db entries are FakeTarget replay declarations; the real target produces its own.
        step["model"] = [action for action in step.get("model", []) if "tool_call" in action or "text" in action]
        for action in step["model"]:
            call = action.get("tool_call")
            if not call:
                continue
            args = call.setdefault("arguments", {})
            if call["name"] == "window_search" and isinstance(args.get("range"), dict):
                span = args.pop("range")
                args.update(start_date=span["start_date"], end_date=span["end_date"])
            elif call["name"] == "synastry":
                args.setdefault("other_subject_id", other)
    return scripted


def _profile_fields(birth: dict[str, Any], gender: str | None) -> dict[str, Any]:
    if not birth.get("solar_datetime"):
        return {}
    location = birth.get("location") or {}
    fields = {
        "birth.solar_datetime": str(birth["solar_datetime"]),
        "birth.precision": birth.get("precision", "exact"),
        "birth.location.lng": location.get("lng"),
        "birth.location.lat": location.get("lat"),
        "birth.location.tz": location.get("tz"),
        "birth.clock_basis": birth.get("clock_basis"),
        "gender": gender,
    }
    return {key: value for key, value in fields.items() if value is not None}


def _other_fields(chart: dict[str, Any]) -> dict[str, Any]:
    place = chart["place"]
    return _profile_fields(
        {
            "solar_datetime": f"{chart['date']} {chart['reported_time']}:00",
            "precision": chart.get("precision", "reported"),
            "location": {"lng": place["lon"], "lat": place["lat"], "tz": place["tz"]},
            "clock_basis": chart.get("clock_basis", "clock"),
        },
        chart.get("gender"),
    )


class P8Acceptance:
    def __init__(self, target: Any) -> None:
        self.target = target
        self.repo = target.repo
        self.owner = target.owner
        self.memory = MemoryService(self.repo)
        self.observations: dict[str, Any] = {}
        self._before: set[tuple] = set()

    @property
    def conversation(self) -> str:
        return self.target.seed.get("context", {}).get("topic_id", "shared")

    def _save(self, subject: str, fields: dict[str, Any], prefix: str) -> None:
        current = {
            fact.get("field"): fact.get("value")
            for fact in self.memory.facts(self.owner, subject, [])
            if fact.get("field")
        }
        for field, value in fields.items():
            if current.get(field) == value:
                continue
            text = f"请保存资料{field}为{value}"
            ident = f"{prefix}-{field}"
            source = self.memory.receive(self.owner, subject, text, source_id=ident, conversation_id=self.conversation)
            saved = self.memory.save_fact(self.owner, subject, source["id"], text, "profile", field=field, value=value)
            if saved["write_status"] != "saved":
                raise ValueError(f"P8 acceptance profile field was not saved: {field}")

    def seed(self) -> None:
        seed = self.target.seed
        overrides = seed.get("profile_overrides", {})
        gender = {"male": "男", "female": "女"}.get(overrides.get("gender", "male"), overrides.get("gender"))
        # The base seeder already saved the declared birth facts; only missing fields are added so
        # no second spelling of the same field creates a conflict.
        self._save("self", _profile_fields(overrides.get("birth", {}), gender), "p8-self")
        fixture = seed["controls"]["p8_acceptance"].get("consent_fixture")
        if fixture is None:
            return
        other = fixture.get("subject_b", OTHER_SUBJECT)
        self.repo.create_subject(self.owner, other, "小禾（合成人物）")
        self._save(other, _other_fields(fixture.get("chart_b", DEFAULT_OTHER_CHART)), "p8-other")
        if fixture.get("status") == "absent":
            return
        self._grant(fixture, other)

    def _grant(self, fixture: dict[str, Any], other: str) -> None:
        """Simulated confirmation-card click; chat text never creates this ledger."""
        service = SynastryConsentService(self.repo)
        source = self.memory.receive(
            self.owner,
            "self",
            "（测试种子）确认卡按钮事件",
            source_id="p8-consent-card-source",
            conversation_id=self.conversation,
        )
        operation = fixture["confirmation_card_operation_id"]
        card = service.request(self.owner, "self", other, fixture["kind"], source["id"], operation)
        card = service.confirm(
            self.owner, card["id"], confirmed=True, expected_revision=card["revision"], request_id=operation + ":click"
        )
        if fixture.get("uses_left") == 0:
            service.consume(
                self.owner,
                card["id"],
                subject_a="self",
                subject_b=other,
                kind=fixture["kind"],
                operation_id=operation + ":earlier-use",
            )

    def _snapshot(self) -> set[tuple]:
        with self.repo.transaction(self.owner) as connection:
            entities = connection.execute(
                sql.SQL("SELECT kind,id,revision,status FROM {} WHERE owner=%s").format(
                    self.repo.table("core_entities")
                ),
                (self.owner,),
            ).fetchall()
            subjects = connection.execute(
                sql.SQL("SELECT * FROM {} WHERE owner=%s").format(self.repo.table("core_subjects")),
                (self.owner,),
            ).fetchall()
        rows = {
            (row["kind"], row["id"], row["revision"], row["status"])
            for row in entities
            if row["kind"] not in TRANSIENT_KINDS
        }
        rows |= {("subject", row["id"], str(sorted(row.items()))) for row in subjects}
        return rows

    def before_turn(self) -> None:
        self._before = self._snapshot()

    def observe(self, steps: list[dict[str, Any]]) -> None:
        calls = {name: 0 for name in P8_TOOLS}
        refusal = None
        for step in steps:
            if step["name"] not in calls:
                continue
            output = step.get("output") or {}
            if step["status"] == "completed" and output.get("ok") is True:
                calls[step["name"]] += 1
            elif refusal is None:
                refusal = REFUSALS.get((output.get("data") or {}).get("code"))
        changed = self._snapshot() - self._before
        self.observations = {
            "engine_calls": calls,
            "long_term_writes": len({row[:2] for row in changed}),
            **({"refusal_code": refusal} if refusal else {}),
        }
