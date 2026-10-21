"""Synthetic host snapshots built from explicit fixture text, never a real source query."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from mingjing_core.application.reflection_v3 import (
    BackgroundPermit,
    ProfileDocument,
    ProfileEntry,
    ThreadState,
    schedule_reflection,
)
from mingjing_core.memory2.contracts import MemoryFact, MemoryScope, MemorySnapshot, MemorySource, SourceAnchor
from mingjing_core.memory2.reflection import ProfileItem
from mingjing_core.timekit.clock import FrozenClock

ROOT = Path(__file__).resolve().parents[3]
TEXTS = json.loads((ROOT / "tools/eval/fixtures/mod_20261021/reflection_background_synthetic.json").read_bytes())[
    "texts"
]
SCOPE = MemoryScope("synthetic-reflection-owner", "synthetic-reflection-self")
AT = datetime(2026, 10, 20, 18, tzinfo=UTC)


def fact(number=1, text_key="background", kind="background", **changes):
    body, said = TEXTS[text_key], AT - timedelta(hours=1)
    role = "assistant" if text_key == "assistant" else "user"
    source = MemorySource(
        f"synthetic-source-{number}",
        SCOPE.owner_id,
        SCOPE.subject_id,
        body,
        said,
        role=role,
        origin="assistant" if role == "assistant" else "current_user",
    )
    anchor = SourceAnchor(source.id, 1, 0, len(body), body)
    values = dict(
        id=f"synthetic-fact-{number}",
        owner_id=SCOPE.owner_id,
        subject_id=SCOPE.subject_id,
        kind=kind,
        text=body,
        source_ids=(source.id,),
        said_at=said,
        recorded_at=said,
        anchors=(anchor,),
        origin="assistant_claim" if role == "assistant" else "user",
    )
    values.update(changes)
    return MemoryFact(**values), source


def context(*pairs):
    pairs = pairs or (fact(),)
    snapshot = MemorySnapshot(
        SCOPE, tuple(row[0] for row in pairs), tuple(row[1] for row in pairs), revision=3, source_epoch=4
    )
    thread = ThreadState(SCOPE, "synthetic-thread", 2, AT - timedelta(minutes=10), tuple(row[1].id for row in pairs))
    permit, clock = BackgroundPermit(SCOPE, 1, 1, True, False), FrozenClock(AT)
    values = dict(snapshot=snapshot, thread=thread, scope=SCOPE, clock=clock, permit=permit)
    return values


def profile(snapshot, *, selected=None, section=2, pinned=False, edited=False, origin="user_fact"):
    chosen = snapshot.facts if selected is None else selected
    rows = []
    for current in chosen:
        item = ProfileItem(
            "profile:" + current.id,
            section,
            current.text,
            current.source_ids,
            (current.id,),
            updated_at=AT - timedelta(minutes=30),
            pinned=pinned,
            edited_by_user=edited,
        )
        rows.append(ProfileEntry(SCOPE, item, 1, current.anchors, origin))
    return ProfileDocument(SCOPE, 5, snapshot.revision, snapshot.source_epoch, tuple(rows))


def intent_for(values):
    return schedule_reflection(**values).intent


def changed_source(values, **changes):
    snapshot = values["snapshot"]
    return {
        **values,
        "snapshot": replace(snapshot, sources=(replace(snapshot.sources[0], **changes), *snapshot.sources[1:])),
    }
