"""Three-value chains must keep exactly one current value through late operations."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from random import Random

import pytest

from mingjing_core.memory2.contracts import (
    MemoryFact,
    MemoryScope,
    MemorySnapshot,
    MemorySource,
    SourceAnchor,
)
from mingjing_core.memory2.forget import plan_forget
from mingjing_core.memory2.guards import MemoryGuardError, authorize_fact
from mingjing_core.memory2.mutation_contracts import MutationConflict
from mingjing_core.memory2.mutations import apply_plan, plan_write
from mingjing_core.memory2.undo import undo_plan
from mingjing_core.timekit.clock import FrozenClock

AT = datetime(2026, 10, 21, tzinfo=UTC)
SCOPE = MemoryScope("owner", "self")
CLOCK = FrozenClock(AT + timedelta(days=1))


def chain():
    facts, sources = [], []
    for i, (identity, city) in enumerate(zip(("a", "b", "c"), ("苏州", "南京", "成都"), strict=True)):
        text, at = f"我现在常住{city}。", AT + timedelta(hours=i)
        source = MemorySource("s" + identity, "owner", "self", text, at)
        anchor = SourceAnchor(source.id, 1, 0, len(text), text)
        fact = MemoryFact(
            identity,
            "owner",
            "self",
            "background",
            text,
            (source.id,),
            at,
            at,
            anchors=(anchor,),
            slot="residence_city",
            value=city,
        )
        facts.append(fact)
        sources.append(source)
    initial = MemorySnapshot(SCOPE, facts=(facts[0],), sources=tuple(sources))
    ab = plan_write(initial, facts[1], scope=SCOPE, operation_id="ab", clock=CLOCK)
    stage = apply_plan(initial, ab).snapshot
    bc = plan_write(stage, facts[2], scope=SCOPE, operation_id="bc", clock=CLOCK)
    return apply_plan(stage, bc).snapshot, ab, bc


def currents(snapshot):
    return {
        fact.id for fact in snapshot.facts if fact.status == "active" and fact.valid_to is None and fact.source_valid
    }


def forget(snapshot, identity):
    plan = plan_forget(snapshot, identity, scope=SCOPE, operation_id="forget-" + identity)
    return apply_plan(snapshot, plan).snapshot


def authorized_currents(snapshot, clock):
    result = set()
    for fact in snapshot.facts:
        if fact.status != "active" or fact.valid_to is not None or fact.valid_from > clock.now():
            continue
        try:
            authorize_fact(fact, snapshot, SCOPE)
        except MemoryGuardError:
            continue
        result.add(fact.id)
    return result


def add_residence(snapshot, identity, city, clock):
    text, at = f"我现在常住{city}。", clock.now()
    source = MemorySource("s" + identity, "owner", "self", text, at)
    anchor = SourceAnchor(source.id, 1, 0, len(text), text)
    incoming = MemoryFact(
        identity,
        "owner",
        "self",
        "background",
        text,
        (source.id,),
        at,
        at,
        anchors=(anchor,),
        slot="residence_city",
        value=city,
    )
    state = replace(
        snapshot,
        sources=(*snapshot.sources, source),
        revision=snapshot.revision + 1,
        source_epoch=snapshot.source_epoch + 1,
    )
    plan = plan_write(state, incoming, scope=SCOPE, operation_id="write-" + identity, clock=clock)
    return apply_plan(state, plan).snapshot, plan


def test_late_undo_of_earlier_update_does_not_create_a_second_current_value():
    snapshot, ab, _ = chain()
    outcome = undo_plan(snapshot, ab, operation_id="late-undo-ab")
    assert currents(outcome.snapshot) == {"c"}
    assert outcome.snapshot.fact("a").valid_to is not None
    assert outcome.snapshot.fact("b").valid_to == snapshot.fact("b").valid_to
    assert outcome.snapshot.fact("c") == snapshot.fact("c")
    assert outcome.conflicts


def test_forgetting_middle_value_cannot_restore_predecessor_while_successor_is_current():
    snapshot, ab, _ = chain()
    forgotten = forget(snapshot, "b")
    assert currents(forgotten) == {"c"}
    assert forgotten.fact("b").status == "deleted"
    assert forgotten.fact("a").superseded_by is None and forgotten.fact("a").valid_to is not None
    assert forgotten.fact("c").supersedes is None
    later = undo_plan(forgotten, ab, operation_id="late-undo-ab").snapshot
    assert currents(later) == {"c"}
    assert later.fact("b").status == "deleted"


def test_forgetting_oldest_value_preserves_later_chain_and_old_undo_does_not_revive_it():
    snapshot, ab, _ = chain()
    forgotten = forget(snapshot, "a")
    assert currents(forgotten) == {"c"}
    assert forgotten.fact("b").supersedes is None and forgotten.fact("b").superseded_by == "c"
    later = undo_plan(forgotten, ab, operation_id="late-undo-ab").snapshot
    assert currents(later) == {"c"}
    assert later.fact("a").status == "deleted"


def test_reverse_order_undo_restores_the_chain_one_step_at_a_time():
    snapshot, ab, bc = chain()
    stage = undo_plan(snapshot, bc, operation_id="undo-bc").snapshot
    assert currents(stage) == {"b"}
    final = undo_plan(stage, ab, operation_id="undo-ab").snapshot
    assert currents(final) == {"a"}
    assert final.fact("b").status == final.fact("c").status == "retired"


@pytest.mark.parametrize("operation", ["forget", "undo"])
def test_withdrawal_detached_new_chain_blocks_old_chain_restoration(operation):
    snapshot, _, bc = chain()
    sources = tuple(replace(source, revoked=True) if source.id == "sc" else source for source in snapshot.sources)
    snapshot = replace(snapshot, sources=sources, source_epoch=1, revision=snapshot.revision + 1)
    clock = FrozenClock(AT + timedelta(hours=4))
    detached, _ = add_residence(snapshot, "d", "青岛", clock)
    assert authorized_currents(detached, clock) == {"d"}
    final = forget(detached, "c") if operation == "forget" else undo_plan(detached, bc, operation_id="undo-bc").snapshot
    assert authorized_currents(final, clock) == {"d"}
    assert final.fact("b").valid_to is not None


@pytest.mark.parametrize("revoked", ["a", "b"])
def test_successive_forget_cannot_resurrect_a_withdrawn_source(revoked):
    snapshot, _, _ = chain()
    sources = tuple(
        replace(source, revoked=True) if source.id == "s" + revoked else source for source in snapshot.sources
    )
    snapshot = replace(snapshot, sources=sources, source_epoch=1, revision=snapshot.revision + 1)
    without_c = forget(snapshot, "c")
    if revoked == "a":
        assert currents(without_c) == {"b"}
    else:
        assert not currents(without_c)
    final = forget(without_c, "b")
    assert final.fact("c").status == final.fact("b").status == "deleted"
    if revoked == "a":
        assert not currents(final)
    else:
        assert currents(final) <= {"a"}


@pytest.mark.parametrize("seed", range(40))
def test_random_write_late_undo_forget_withdrawal_keeps_deleted_content_absorbing(seed):
    rng = Random(716503 + seed)
    snapshot, ab, bc = chain()
    clock = FrozenClock(AT + timedelta(hours=3))
    deleted, withdrawn, plans = set(), set(), [ab, bc]
    for step in range(25):
        clock.advance(timedelta(minutes=1))
        operation = rng.choice(("write", "undo", "forget", "withdraw"))
        try:
            if operation == "write":
                snapshot, plan = add_residence(
                    snapshot,
                    f"n{seed}-{step}",
                    rng.choice(("青岛", "宁波", "厦门")),
                    clock,
                )
                plans.append(plan)
            elif operation == "forget":
                plan = plan_forget(
                    snapshot,
                    rng.choice(snapshot.facts).id,
                    scope=SCOPE,
                    operation_id=f"s{step}",
                )
                snapshot = apply_plan(snapshot, plan).snapshot
            elif operation == "withdraw":
                chosen = rng.choice(snapshot.sources).id
                sources = tuple(
                    replace(source, revoked=True) if source.id == chosen else source for source in snapshot.sources
                )
                snapshot = replace(
                    snapshot,
                    sources=sources,
                    revision=snapshot.revision + 1,
                    source_epoch=snapshot.source_epoch + 1,
                )
            else:
                snapshot = undo_plan(snapshot, rng.choice(plans), operation_id=f"s{step}").snapshot
        except (MutationConflict, MemoryGuardError):
            pass
        assert len(authorized_currents(snapshot, clock)) <= 1, (seed, step, operation)
        assert all(snapshot.fact(identity).status == "deleted" for identity in deleted)
        assert all(snapshot.source(identity).revoked for identity in withdrawn)
        deleted |= {fact.id for fact in snapshot.facts if fact.status == "deleted"}
        withdrawn |= {source.id for source in snapshot.sources if source.revoked}
        assert all(not fact.source_ids and not fact.anchors for fact in snapshot.facts if fact.id in deleted)
