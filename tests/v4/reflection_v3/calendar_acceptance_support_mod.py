"""Independent synthetic source projections constructed only through public contracts."""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from mingjing_core.application.reflection_v3 import BackgroundPermit, ThreadState, schedule_reflection
from mingjing_core.application.reflection_v3.profile_contracts import AboutMeView, ProfileDocument, ProfileEntry
from mingjing_core.application.reflection_v3.profile_renderer import render_about_me
from mingjing_core.memory2.contracts import MemoryFact, MemoryScope, MemorySnapshot, MemorySource, SourceAnchor
from mingjing_core.memory2.reflection import ProfileItem
from mingjing_core.timekit.clock import FrozenClock

ROOT = Path(__file__).resolve().parents[3]
EXPECTED_SHA = "c69f9956b75c891b2ca18e7a9df0cecf920f76db11b9a497ed4962f37c06464e"
EXPECTED_LF_SHA = "4687a792b15d043f636a7a0f71f338ee5d4d74af17d04db158946a30b80ef918"
SCOPE = MemoryScope("synthetic-reflection-owner", "synthetic-reflection-subject")
NOW = datetime(2026, 10, 21, 2, tzinfo=UTC)


@dataclass(frozen=True)
class Bundle:
    snapshot: MemorySnapshot
    thread: ThreadState
    permit: BackgroundPermit
    clock: FrozenClock


def expected() -> dict[str, Any]:
    content = (Path(__file__).parent / "fixtures/expected_calendar_mod.json").read_bytes()
    return frozen_expected_bytes(content)


def frozen_expected_bytes(content: bytes) -> dict[str, Any]:
    # Git may check out the identical frozen JSON as LF; only those two exact artifacts are accepted.
    assert hashlib.sha256(content).hexdigest() in {EXPECTED_SHA, EXPECTED_LF_SHA}
    return json.loads(content)


def wording(key: str) -> str:
    path = ROOT / "tools/eval/fixtures/mod_20261021/reflection_calendar_mod_synthetic.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    assert value["synthetic"] is True
    return value["texts"][key]


def bundle(
    *,
    now: datetime = NOW,
    idle: timedelta = timedelta(minutes=10),
    text_key: str = "preference",
    timezone: str = "Asia/Shanghai",
) -> Bundle:
    at = now - idle
    text = wording(text_key)
    source = MemorySource("synthetic-source-one", SCOPE.owner_id, SCOPE.subject_id, text, at)
    anchor = SourceAnchor(source.id, source.revision, 0, len(text), text)
    fact = MemoryFact(
        "synthetic-fact-one",
        SCOPE.owner_id,
        SCOPE.subject_id,
        "preference",
        text,
        (source.id,),
        at,
        at,
        (anchor,),
    )
    snapshot = MemorySnapshot(SCOPE, (fact,), (source,), revision=4, source_epoch=3)
    thread = ThreadState(
        SCOPE, "synthetic-thread-one", 2, at, (source.id,), daily_completed_on=now.astimezone(ZoneInfo(timezone)).date()
    )
    permit = BackgroundPermit(SCOPE, 2, 2, enabled=True, quota_stopped=False)
    return Bundle(snapshot, thread, permit, FrozenClock(now))


def schedule(data: Bundle, **overrides: Any) -> Any:
    values: dict[str, Any] = {
        "snapshot": data.snapshot,
        "thread": data.thread,
        "scope": SCOPE,
        "clock": data.clock,
        "permit": data.permit,
    }
    return schedule_reflection(**(values | overrides))


def profile(data: Bundle, *, section: int = 5, **overrides: Any) -> ProfileDocument:
    fact = data.snapshot.facts[0]
    item = ProfileItem(
        "synthetic-profile-one", section, fact.text, fact.source_ids, (fact.id,), updated_at=fact.recorded_at
    )
    entry = ProfileEntry(SCOPE, item, 1, fact.anchors)
    values: dict[str, Any] = {
        "scope": SCOPE,
        "revision": 5,
        "snapshot_revision": data.snapshot.revision,
        "source_epoch": data.snapshot.source_epoch,
        "entries": (entry,),
    }
    return ProfileDocument(**(values | overrides))


def view(data: Bundle, document: ProfileDocument | None = None, **overrides: Any) -> AboutMeView:
    document = document or profile(data)
    values: dict[str, Any] = {
        "snapshot": data.snapshot,
        "scope": SCOPE,
        "clock": data.clock,
        "current_profile_revision": document.revision,
    }
    return render_about_me(document, **(values | overrides))


def shown(value: AboutMeView) -> tuple[Any, ...]:
    return tuple(line for section in value.sections for line in section.lines)


def work(data: Bundle, intent: Any, **overrides: Any) -> Any:
    from mingjing_core.application.reflection_v3.work import plan_reflection_work

    values: dict[str, Any] = {
        "snapshot": data.snapshot,
        "thread": data.thread,
        "scope": SCOPE,
        "clock": data.clock,
        "permit": data.permit,
    }
    return plan_reflection_work(intent, **(values | overrides))
