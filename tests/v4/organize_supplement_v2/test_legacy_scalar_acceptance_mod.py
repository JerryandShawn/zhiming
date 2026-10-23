"""Five independent scalar boundaries, using only public synthetic source/review APIs."""

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from mingjing_core.memory2.contracts import MemoryScope, MemorySource, SourceAnchor
from mingjing_core.organize.changes import ChangeSet
from mingjing_core.organize.contracts import Message
from mingjing_core.organize.supplement_v2 import (
    EntityRecord,
    ReviewApproval,
    SupplementPlan,
    SupplementSnapshot,
    build_review_proposal,
    plan_review_labels,
    to_legacy_changeset,
)
from mingjing_core.organize.v2.contracts import Prediction
from mingjing_core.timekit.clock import FrozenClock

ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = ROOT / "docs/v4/evidence/MOD_2026-10-21/LEGACY_SCALAR_frozen_matrix_20261021.json"
MATRIX = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
SYNTHETIC = json.loads((ROOT / MATRIX["fixture"]).read_text(encoding="utf-8"))
LABEL_FIELDS = frozenset({"space_id", "topic_id", "space_secondary", "route_source", "route_confidence"})


@dataclass(frozen=True)
class ScalarScenario:
    scope: MemoryScope
    snapshot: SupplementSnapshot
    plan: SupplementPlan
    approval: ReviewApproval
    document: dict[str, Any]
    clock: FrozenClock


def scenario(case: dict[str, Any]) -> ScalarScenario:
    clock = FrozenClock(datetime.fromisoformat(case["source_at"]))
    scope = MemoryScope(SYNTHETIC["owner_id"], SYNTHETIC["subject_id"])
    source = MemorySource(
        SYNTHETIC["message_id"],
        scope.owner_id,
        scope.subject_id,
        SYNTHETIC["text"],
        clock.now(),
        revision=case["revision"],
    )
    message = Message(
        source.id,
        source.role,
        source.text,
        int(clock.now().timestamp() * 1000),
        scope.owner_id,
        scope.subject_id,
        revision=case["revision"],
    )
    anchor = SourceAnchor(source.id, source.revision, 0, len(source.text), source.text)
    entity = EntityRecord(source.id, scope, "message", source.text, source.at, (anchor,), revision=message.revision)
    snapshot = SupplementSnapshot(scope, entities=(entity,), sources=(source,))
    prediction = Prediction("career", 0.9, {"career": 3.0}, "synthetic_independent_input")
    proposal = build_review_proposal(
        snapshot,
        {entity.id: prediction},
        scope=scope,
        operation_id=f"scalar-{case['id']}",
    )
    approval = ReviewApproval(scope, proposal.fingerprint)
    plan = plan_review_labels(snapshot, proposal, scope=scope, approval=approval)
    record = {
        "id": message.id,
        "owner_id": message.owner_id,
        "subject_id": message.subject_id,
        "content": message.content,
        "role": message.role,
        "at_ms": case["raw_at_ms"],
        "revision": case["raw_revision"],
    }
    document = {
        "owner_id": scope.owner_id,
        "subject_id": scope.subject_id,
        "messages": {source.id: record},
        "topics": {},
    }
    return ScalarScenario(scope, snapshot, plan, approval, document, clock)


def encoded(document: dict[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def assert_label_only(changeset: ChangeSet, value: ScalarScenario) -> None:
    assert isinstance(changeset, ChangeSet)
    assert changeset.batch_id == value.plan.operation_id
    assert (changeset.owner_id, changeset.subject_id) == (value.scope.owner_id, value.scope.subject_id)
    assert changeset.ops
    assert all(op.collection == "messages" and op.field in LABEL_FIELDS for op in changeset.ops)
    assert {op.entity_id for op in changeset.ops} == {SYNTHETIC["message_id"]}
    assert any(op.field == "space_id" and op.after.value == "career" for op in changeset.ops)
    assert len(changeset.source_guards) == 1
    assert changeset.source_guards[0].entity_id == SYNTHETIC["message_id"]


@pytest.mark.parametrize("case", MATRIX["cases"], ids=[case["id"] for case in MATRIX["cases"]])
def test_public_bridge_scalar_contract(case: dict[str, Any]) -> None:
    value = scenario(case)
    before = encoded(deepcopy(value.document))
    original_sources = value.snapshot.sources
    original_entities = value.snapshot.entities
    try:
        if case["expected"] == "controlled_reject":
            with pytest.raises(ValueError) as caught:
                to_legacy_changeset(
                    value.snapshot,
                    value.plan,
                    value.document,
                    scope=value.scope,
                    approval=value.approval,
                )
            assert str(caught.value)
            assert SYNTHETIC["text"] not in str(caught.value)
            assert SYNTHETIC["owner_id"] not in str(caught.value)
        else:
            assert case["expected"] == "labels_only"
            changeset = to_legacy_changeset(
                value.snapshot,
                value.plan,
                value.document,
                scope=value.scope,
                approval=value.approval,
            )
            assert_label_only(changeset, value)
    finally:
        assert encoded(value.document) == before
        assert value.snapshot.sources == original_sources
        assert value.snapshot.entities == original_entities
        assert value.snapshot.sources[0].text == value.snapshot.entities[0].text == SYNTHETIC["text"]
        assert type(value.snapshot.sources[0].revision) is int
        assert value.snapshot.sources[0].revision == case["revision"]
        assert value.clock.now() == datetime.fromisoformat(case["source_at"])
