"""Independent public setup; fictional message text lives only in an explicit synthetic fixture."""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from mingjing_core.memory2.contracts import MemoryScope, MemorySource, SourceAnchor
from mingjing_core.organize.changes import ChangeSet
from mingjing_core.organize.supplement_v2 import (
    EntityRecord,
    ReviewApproval,
    SupplementPlan,
    SupplementSnapshot,
    TopicRecord,
    build_review_proposal,
    plan_archive_review,
    plan_review_labels,
    plan_topic_archive,
    to_legacy_changeset,
)
from mingjing_core.organize.v2.contracts import Prediction
from mingjing_core.timekit.clock import FrozenClock

ROOT = Path(__file__).resolve().parents[3]
MATRIX = ROOT / "docs/v4/evidence/MOD_2026-10-21/LEGACY_BRIDGE_frozen_matrix_20261021.json"
MATRIX_SHA = "883b171aa7589aa1ee807d439c1779714ee91f588c9a2b0755b269b07b3491b2"
CASES_SHA = "d2a66eac57234f68afc8c602394a8b359628addb8f4d7a938271840acdefa711"
SYNTHETIC = ROOT / "tools/eval/fixtures/mod_20261021/legacy_bridge_calendar_synthetic.json"
SCOPE = MemoryScope("synthetic-legacy-owner", "synthetic-legacy-self")
ZONE = ZoneInfo("Asia/Shanghai")
AT = datetime(2026, 10, 6, 9, 15, 30, 123000, tzinfo=ZONE)


def frozen_cases() -> tuple[dict[str, Any], ...]:
    raw = MATRIX.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == MATRIX_SHA
    value = json.loads(raw)
    cases = value["cases"]
    canonical = json.dumps(cases, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(canonical).hexdigest() == CASES_SHA
    assert len(cases) == 15 and [item["id"] for item in cases] == [f"LB{i:02}" for i in range(1, 16)]
    return tuple(cases)


def fictional_values() -> dict[str, Any]:
    result = json.loads(SYNTHETIC.read_text(encoding="utf-8"))
    assert result["synthetic"] is True
    return result


@dataclass(frozen=True)
class LegacyCase:
    snapshot: SupplementSnapshot = field(repr=False)
    plan: SupplementPlan = field(repr=False)
    document: dict[str, Any] = field(repr=False)
    approval: ReviewApproval = field(repr=False)


def source_for(case_id: str, text: str) -> MemorySource:
    identity = "synthetic-other-source" if case_id == "LB10" else "synthetic-message-legacy-001"
    return MemorySource(
        identity,
        SCOPE.owner_id,
        SCOPE.subject_id,
        text,
        AT,
        revision=2 if case_id == "LB13" else 1,
    )


def anchors_for(case_id: str, source: MemorySource) -> tuple[SourceAnchor, ...]:
    text = source.text
    if case_id == "LB11":
        end = text.index("，")
        return (SourceAnchor(source.id, source.revision, 0, end, text[:end]),)
    if case_id == "LB12":
        middle = len(text) // 2
        return (
            SourceAnchor(source.id, source.revision, 0, middle, text[:middle]),
            SourceAnchor(source.id, source.revision, middle, len(text), text[middle:]),
        )
    return (SourceAnchor(source.id, source.revision, 0, len(text), text),)


def message_document(source: MemorySource) -> dict[str, Any]:
    identity = "synthetic-message-legacy-001"
    return {
        "owner_id": SCOPE.owner_id,
        "subject_id": SCOPE.subject_id,
        "topics": {},
        "messages": {
            identity: {
                "id": identity,
                "owner_id": SCOPE.owner_id,
                "subject_id": SCOPE.subject_id,
                "content": source.text,
                "role": "user",
                "at_ms": int(source.at.timestamp() * 1000),
                "revision": 1,
            }
        },
    }


def change_document(document: dict[str, Any], case_id: str, values: dict[str, Any]) -> None:
    record = document["messages"]["synthetic-message-legacy-001"]
    if case_id == "LB01":
        document["owner_id"] = "synthetic-other-owner"
    elif case_id == "LB02":
        document["subject_id"] = "synthetic-other-subject"
    elif case_id == "LB03":
        document["messages"] = {}
    elif case_id == "LB04":
        record["content"] = values["changed_text"]
    elif case_id == "LB05":
        record["role"] = "assistant"
    elif case_id == "LB06":
        record["at_ms"] += 1
    elif case_id == "LB07":
        record["revision"] = 2
    elif case_id == "LB08":
        record["revision"] = True
    elif case_id == "LB09":
        record["topic_id"] = None
    elif case_id == "LB15":
        record.pop("revision")


def archive_case(source: MemorySource, values: dict[str, Any]) -> LegacyCase:
    anchors = anchors_for("LB14", source)
    topic = TopicRecord("synthetic-old-topic", SCOPE, source.at, anchors, title=values["topic_title"])
    snapshot = SupplementSnapshot(SCOPE, topics=(topic,), sources=(source,), revision=7, source_epoch=3)
    clock = FrozenClock(datetime(2026, 10, 21, 10, tzinfo=ZONE))
    proposal = plan_topic_archive(snapshot, scope=SCOPE, clock=clock, operation_id="synthetic-legacy-batch-LB14")
    assert len(proposal.entries) == 1
    approval = ReviewApproval(SCOPE, proposal.fingerprint)
    plan = plan_archive_review(snapshot, proposal, scope=SCOPE, approval=approval)
    document = {"owner_id": SCOPE.owner_id, "subject_id": SCOPE.subject_id, "messages": {}, "topics": {}}
    return LegacyCase(snapshot, plan, document, approval)


def make_case(case_id: str) -> LegacyCase:
    values = fictional_values()
    source = source_for(case_id, values["source_text"])
    if case_id == "LB14":
        return archive_case(source, values)
    anchors = anchors_for(case_id, source)
    text = anchors[0].quote if case_id == "LB11" else source.text
    entity = EntityRecord("synthetic-message-legacy-001", SCOPE, "message", text, source.at, anchors)
    snapshot = SupplementSnapshot(SCOPE, entities=(entity,), sources=(source,), revision=7, source_epoch=3)
    prediction = Prediction("career", 0.91, {"career": 1.0}, "synthetic-explicit-input")
    proposal = build_review_proposal(
        snapshot, {entity.id: prediction}, scope=SCOPE, operation_id="synthetic-legacy-batch-" + case_id
    )
    approval = ReviewApproval(SCOPE, proposal.fingerprint)
    plan = plan_review_labels(snapshot, proposal, scope=SCOPE, approval=approval)
    assert plan.ops and plan.reviewed == proposal
    document = message_document(source)
    change_document(document, case_id, values)
    return LegacyCase(snapshot, plan, document, approval)


def plain_value(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: plain_value(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {key: plain_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain_value(item) for item in value]
    return value


def protected_fingerprint(case: LegacyCase) -> str:
    encoded = json.dumps(plain_value(case), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def observed_call(case_id: str, case: LegacyCase) -> ChangeSet | Exception:
    try:
        result = to_legacy_changeset(case.snapshot, case.plan, case.document, scope=SCOPE, approval=case.approval)
    except Exception as error:
        values = fictional_values()
        safe = not any(values[key] in str(error) for key in ("source_text", "changed_text", "topic_title"))
        observation = {
            "case_id": case_id,
            "outcome": "exception",
            "error_type": type(error).__name__,
            "reason": str(error) if safe else "[redacted unexpected source text]",
            "no_fixture_text_in_error": safe,
        }
        print("LEGACY_BRIDGE_OBSERVATION=" + json.dumps(observation, ensure_ascii=False), flush=True)
        return error
    observation = {
        "case_id": case_id,
        "outcome": "returned",
        "returned_type": type(result).__name__,
        "operation_paths": [(op.collection, op.entity_id, op.field) for op in result.ops],
    }
    print("LEGACY_BRIDGE_OBSERVATION=" + json.dumps(observation, ensure_ascii=False), flush=True)
    return result
