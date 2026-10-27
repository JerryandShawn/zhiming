"""Full synthetic period content composition, including input construction and output assertions."""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mingjing_core.adapters.channels.cardkit_contracts import fingerprint  # noqa: E402
from mingjing_core.application.briefing_v2 import calendar_snapshot  # noqa: E402
from mingjing_core.application.followups_contracts import FollowupScope  # noqa: E402
from mingjing_core.application.reports_v2 import (  # noqa: E402
    BasisRef,
    BriefSourceState,
    DailyTransitInput,
    ReportRecord,
    compose_period_report,
)
from mingjing_core.timekit.clock import FrozenClock, SystemClock  # noqa: E402
from tools.mod_week.performance import measure, write_report  # noqa: E402

FIXTURE = ROOT / "tests/v4/briefing_v2/fixtures/daily_transit_synthetic_20261021.json"
AT = datetime(2026, 10, 21, 8, tzinfo=ZoneInfo("Asia/Shanghai"))


def record(scope: FollowupScope, index: int) -> ReportRecord:
    body = f"纯合成期间记录 {index}，不是用户真实经历。"
    digest = fingerprint(body)
    ref = BasisRef("m1", f"synthetic-period-source-{index}", 1, scope.owner_id, scope.subject_id, digest)
    state = BriefSourceState(ref.source_id, scope, 1, digest, revoked=index == 10)
    return ReportRecord(
        scope,
        f"synthetic-record-{index}",
        ("fact", "arrangement", "followup")[index % 3],
        body,
        AT - timedelta(days=1),
        (ref,),
        (state,),
        at=AT - timedelta(hours=index + 1),
        area_id=("daily", "career", "family")[index % 3],
        status="archived" if index == 9 else "active",
        valid_to=AT if index == 11 else None,
    )


def one_report(fixture: bytes, kind: str) -> None:
    payload = json.loads(fixture)
    scope = FollowupScope(payload["scope"]["owner_user_id"], payload["scope"]["subject_id"])
    if not scope.owner_id.startswith("synthetic-") or not scope.subject_id.startswith("synthetic-"):
        raise ValueError("benchmark_requires_synthetic_scope")
    clock = FrozenClock(AT)
    revision, document = payload["scope"]["revision"], payload["document_id"]
    source = BriefSourceState(document, scope, revision, document[5:])
    transit = DailyTransitInput(AT.date(), payload, source)
    rows = tuple(record(scope, index) for index in range(12))
    result = compose_period_report(
        scope=scope,
        kind=kind,
        day=AT.date(),
        clock=clock,
        records=rows,
        calendar=calendar_snapshot(scope=scope, clock=clock),
        transits=(transit,),
        profile_revision=revision,
    )
    assert len(result.used_record_ids) == 9 and len(result.omissions) == 3
    assert result.coverage.rendered_snapshot_days == (AT.date(),)
    assert len([line for section in result.sections if section.category == "symbolic" for line in section.lines]) == 6
    assert result.used_claim_ids and all(row.basis.owner_id == scope.owner_id for row in result.citations)
    assert any(section.id == "now_calendar" for section in result.sections)
    assert result.effects.model_calls == result.effects.writes == result.effects.notifications == 0
    assert not hasattr(result, "delivery")


def workload(fixture: bytes) -> int:
    for index in range(90):
        one_report(fixture, ("weekly", "monthly", "quarterly")[index % 3])
    return 90


def sources() -> tuple[Path, ...]:
    directories = ("mingjing_core/application/reports_v2", "mingjing_core/application/briefing_v2")
    files = [path for directory in directories for path in (ROOT / directory).glob("*.py")]
    files.extend(
        ROOT / name
        for name in (
            "mingjing_core/domain/report_schedules.py",
            "mingjing_core/adapters/channels/cardkit_contracts.py",
            "mingjing_core/streaming/json_values.py",
            "mingjing_core/timekit/clock.py",
            "mingjing_core/timekit/almanac.py",
            "mingjing_core/timekit/calendar_cn.py",
            "tools/mod_week/performance.py",
        )
    )
    return (*files, Path(__file__), FIXTURE)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve().exists():
        raise ValueError("period_benchmark_output_must_be_new")
    fixture, paths = FIXTURE.read_bytes(), sources()
    before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    cases = [measure("complete_period_reports_90_30_per_kind", lambda: workload(fixture))]
    cases[0]["timed_work"] = (
        "90 reports: fixture JSON decode, immutable inputs, 12 source records and current manifests per report, "
        "P2 calendar snapshot calculation, full P8 document/claim checks, compose, and assertions"
    )
    cases[0]["excluded_preparation"] = "fixture byte read, module imports, source hashing, report-file write"
    if before != {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}:
        raise ValueError("period_benchmark_source_changed")
    write_report(args.output, cases, paths, clock=SystemClock())
    print("complete_period_reports_90", cases[0]["median_seconds"], cases[0]["separate_tracemalloc_peak_bytes"])


if __name__ == "__main__":
    main()
