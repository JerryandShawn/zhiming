"""Fictional public memory inputs; each scenario owns its mutable FrozenClock."""

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from mingjing_core.memory2.contracts import MemoryFact, MemoryScope, MemorySnapshot, MemorySource, SourceAnchor
from mingjing_core.memory2.forget import plan_forget
from mingjing_core.memory2.mutation_contracts import FactChange, MutationPlan
from mingjing_core.memory2.mutations import apply_plan, plan_changes, plan_write
from mingjing_core.memory2.plan_builder import fingerprint
from mingjing_core.timekit.clock import FrozenClock

AT = datetime(2026, 10, 21, 2, tzinfo=UTC)
SCOPE = MemoryScope("mutation-coverage-owner", "mutation-coverage-self")
TEXT = "我喜欢每周整理书架。（合成测试）"


@dataclass(frozen=True)
class Scenario:
    scope: MemoryScope
    source: MemorySource
    fact: MemoryFact
    snapshot: MemorySnapshot
    clock: FrozenClock


def scenario(
    *, scope: MemoryScope = SCOPE, identity: str = "fictional-fact", text: str = TEXT, assistant: bool = False
) -> Scenario:
    said = AT - timedelta(hours=1)
    source = MemorySource(
        "source-" + identity,
        scope.owner_id,
        scope.subject_id,
        text,
        said,
        role="assistant" if assistant else "user",
        origin="system" if assistant else "current_user",
    )
    fact = MemoryFact(
        identity,
        scope.owner_id,
        scope.subject_id,
        "note" if assistant else "background",
        text,
        (source.id,),
        said,
        said + timedelta(minutes=1),
        anchors=(SourceAnchor(source.id, 1, 0, len(text), text),),
        origin="assistant_claim" if assistant else "user",
    )
    return Scenario(scope, source, fact, MemorySnapshot(scope, sources=(source,)), FrozenClock(AT))


def reseal(plan: MutationPlan) -> MutationPlan:
    return replace(plan, fingerprint=fingerprint(plan))


def write(item: Scenario) -> MutationPlan:
    return plan_write(item.snapshot, item.fact, scope=item.scope, operation_id="fictional-write", clock=item.clock)


def written() -> tuple[Scenario, MutationPlan, MemorySnapshot]:
    item = scenario()
    plan = write(item)
    result = apply_plan(item.snapshot, plan, clock=item.clock)
    assert result.write_status == "saved" and result.snapshot.fact(item.fact.id) == item.fact
    return item, plan, result.snapshot


def forgotten() -> tuple[Scenario, MutationPlan, MutationPlan, MemorySnapshot]:
    item, saved, snapshot = written()
    forget = plan_forget(snapshot, item.fact.id, scope=item.scope, operation_id="fictional-forget")
    result = apply_plan(snapshot, forget, clock=item.clock)
    assert result.write_status == "forgotten" and result.snapshot.fact(item.fact.id).status == "deleted"
    return item, saved, forget, result.snapshot


def archive() -> tuple[Scenario, MemorySnapshot, MutationPlan]:
    item = scenario()
    before = replace(item.snapshot, facts=(item.fact,))
    change = FactChange(item.fact.id, item.fact, replace(item.fact, status="archived", revision=item.fact.revision + 1))
    plan = plan_changes(before, (change,), scope=item.scope, operation_id="fictional-archive")
    return item, before, plan
