"""Public input constructors; synthetic wording is held only in an explicit fixture."""

import hashlib
import json
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from mingjing_core.application.followups_contracts import FollowupScope
from mingjing_core.application.reports_v2 import (
    BasisRef,
    BriefSourceState,
    DailyTransitInput,
    PeriodReport,
    ReportRecord,
    SyntheticSymbolicInput,
    compose_period_report,
)
from mingjing_core.timekit.clock import FrozenClock

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).parent / "fixtures"
EXPECTED_SHA = "380252aa72c237eeb6ded44dc6b73cc590b1b030806a3ae4420ee78fbf08db76"
SCOPE = FollowupScope("synthetic-report-owner", "synthetic-report-subject")
DAY = date(2026, 10, 21)
NOW = datetime(2026, 11, 2, 12, tzinfo=UTC)
SAID = datetime(2026, 10, 20, 2, tzinfo=UTC)


def expected() -> dict[str, Any]:
    value = (FIXTURES / "expected_calendar_mod.json").read_bytes()
    assert hashlib.sha256(value).hexdigest() == EXPECTED_SHA
    return json.loads(value)


def wording(key: str) -> str:
    path = ROOT / "tools/eval/fixtures/mod_20261021/reports_calendar_mod_synthetic.json"
    fixture = json.loads(path.read_text(encoding="utf-8"))
    assert fixture["synthetic"] is True
    return fixture["texts"][key]


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def record(index: int = 1, **overrides: Any) -> ReportRecord:
    text = wording("fact_one" if index == 1 else "fact_two")
    ref = BasisRef(
        "f1", f"source-{index}", 1, SCOPE.owner_id, SCOPE.subject_id, digest(text), f"document-{index}", "/facts/0"
    )
    state = BriefSourceState(ref.source_id, SCOPE, ref.revision, ref.value_sha256)
    original = ReportRecord(SCOPE, f"record-{index}", "fact", text, SAID, (ref,), (state,))
    return replace(original, **overrides)


def report(**overrides: Any) -> PeriodReport:
    values: dict[str, Any] = {"scope": SCOPE, "kind": "monthly", "day": DAY, "clock": FrozenClock(NOW)}
    return compose_period_report(**(values | overrides))


def rendered(value: PeriodReport) -> str:
    return "\n".join(line.text for section in value.sections for line in section.lines)


def record_citations(value: PeriodReport, source_id: str) -> tuple[Any, ...]:
    return tuple(citation for citation in value.citations if citation.basis.source_id == source_id)


def p8_payload() -> dict[str, Any]:
    descriptor = expected()["P8_readonly_synthetic_reference"]
    content = (ROOT / descriptor["path"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == descriptor["sha256"]
    return json.loads(content)


def p8_scope(payload: dict[str, Any]) -> FollowupScope:
    return FollowupScope(payload["scope"]["owner_user_id"], payload["scope"]["subject_id"])


def p8_state(payload: dict[str, Any]) -> BriefSourceState:
    document_id = payload["document_id"]
    return BriefSourceState(document_id, p8_scope(payload), payload["scope"]["revision"], document_id[5:])


def p8_report(payload: dict[str, Any], *, current: BriefSourceState | None = None, **overrides: Any) -> PeriodReport:
    transit = DailyTransitInput(DAY, payload, current or p8_state(payload))
    values: dict[str, Any] = {
        "scope": p8_scope(payload),
        "transits": (transit,),
        "profile_revision": payload["scope"]["revision"],
    }
    return report(**(values | overrides))


def symbolic(**overrides: Any) -> SyntheticSymbolicInput:
    text = wording("symbolic")
    ref = BasisRef("s1", "synthetic-symbolic-one", 1, SCOPE.owner_id, SCOPE.subject_id, digest(text))
    state = BriefSourceState(ref.source_id, SCOPE, ref.revision, ref.value_sha256)
    row = SyntheticSymbolicInput(SCOPE, "synthetic-one", DAY, text, "synthetic-demonstration", (ref,), (state,))
    return replace(row, **overrides)
