"""M01-M24 frozen public-input truths; no stochastic lifecycle duplication."""

from dataclasses import fields, replace
from datetime import timedelta

import pytest

from mingjing_core.memory2.contracts import MemoryScope, MemorySettings
from mingjing_core.memory2.forget import plan_forget
from mingjing_core.memory2.guards import MemoryGuardError
from mingjing_core.memory2.mutation_contracts import FactChange, MutationConflict, MutationPlan
from mingjing_core.memory2.mutations import apply_plan, plan_changes
from mingjing_core.memory2.undo import undo_plan

from .mutation_boundary_support_acceptance_mod import SCOPE, archive, forgotten, reseal, scenario, write, written


def test_m01_missing_fingerprint_does_not_apply_or_record_an_operation() -> None:
    item = scenario()
    plan = replace(write(item), fingerprint="")
    with pytest.raises(MutationConflict):
        apply_plan(item.snapshot, plan, clock=item.clock)
    assert item.snapshot.facts == () and item.snapshot.operations == ()


def test_m02_current_plan_cannot_apply_under_another_subject() -> None:
    item = scenario()
    foreign = scenario(scope=MemoryScope(SCOPE.owner_id, "foreign-subject"), text="我喜欢种植薄荷。（合成测试）")
    with pytest.raises(MutationConflict):
        apply_plan(foreign.snapshot, write(item), clock=item.clock)
    assert foreign.snapshot.facts == () and item.snapshot.facts == ()


def test_m03_changed_cached_summary_does_not_keep_the_old_content_fingerprint() -> None:
    item = scenario()
    with pytest.raises(MutationConflict):
        apply_plan(item.snapshot, replace(write(item), summary="虚构改写回执"), clock=item.clock)
    assert item.snapshot.operations == ()


def test_m04_metadata_cannot_create_a_fact() -> None:
    item = scenario()
    with pytest.raises(MutationConflict):
        plan_changes(
            item.snapshot, (FactChange(item.fact.id, None, item.fact),), scope=item.scope, operation_id="create"
        )
    assert item.snapshot.facts == ()


def test_m05_metadata_cannot_delete_a_fact() -> None:
    item, snapshot, _ = archive()
    with pytest.raises(MutationConflict):
        plan_changes(snapshot, (FactChange(item.fact.id, item.fact, None),), scope=item.scope, operation_id="delete")
    assert snapshot.fact(item.fact.id) == item.fact


def test_m06_metadata_cannot_import_foreign_owner_content() -> None:
    item = scenario()
    foreign = scenario(scope=MemoryScope("foreign-owner", SCOPE.subject_id), identity="foreign")
    change = FactChange(foreign.fact.id, foreign.fact, replace(foreign.fact, status="archived", revision=2))
    with pytest.raises(MemoryGuardError) as caught:
        plan_changes(item.snapshot, (change,), scope=item.scope, operation_id="foreign")
    assert foreign.fact.text not in str(caught.value) and item.snapshot.facts == ()


def test_m07_metadata_cannot_import_foreign_subject_content() -> None:
    item = scenario()
    foreign = scenario(scope=MemoryScope(SCOPE.owner_id, "foreign-subject"), identity="foreign")
    change = FactChange(foreign.fact.id, foreign.fact, replace(foreign.fact, status="archived", revision=2))
    with pytest.raises(MemoryGuardError):
        plan_changes(item.snapshot, (change,), scope=item.scope, operation_id="foreign")
    assert item.snapshot.sources == (item.source,)


def test_m08_archive_metadata_cannot_change_event_end() -> None:
    item, snapshot, plan = archive()
    after = replace(item.fact, status="archived", revision=2, event_end=item.clock.now() + timedelta(hours=1))
    with pytest.raises(MutationConflict):
        plan_changes(snapshot, (FactChange(item.fact.id, item.fact, after),), scope=item.scope, operation_id="bad-time")
    assert snapshot.fact(item.fact.id).event_end is None and plan.changes[0].after.event_end is None


def test_m09_stale_before_image_is_rejected_even_if_host_snapshot_revision_was_not_bumped() -> None:
    item, snapshot, plan = archive()
    changed = replace(snapshot, facts=(replace(item.fact, revision=2),))
    with pytest.raises(MutationConflict) as caught:
        apply_plan(changed, plan, clock=item.clock)
    assert str(caught.value) == "fact_revision_changed" and changed.fact(item.fact.id).status == "active"


def test_m10_save_replay_after_public_forget_does_not_revive_the_fact() -> None:
    item, saved, _, snapshot = forgotten()
    result = apply_plan(snapshot, saved, clock=item.clock)
    assert result.replayed and result.write_status == "unavailable" and result.snapshot == snapshot
    assert result.snapshot.fact(item.fact.id).text == "已遗忘"


def test_m11_forget_replay_with_tombstone_is_an_unchanged_successful_replay() -> None:
    item, _, forget, snapshot = forgotten()
    result = apply_plan(snapshot, forget, clock=item.clock)
    assert result.replayed and result.write_status == "forgotten" and result.snapshot == snapshot
    assert result.snapshot.revision == snapshot.revision and not result.snapshot.fact(item.fact.id).source_ids


def test_m12_removed_current_projection_does_not_reconstruct_saved_result_from_plan() -> None:
    item, plan, snapshot = written()
    current = replace(snapshot, facts=())
    result = apply_plan(current, plan, clock=item.clock)
    assert result.replayed and result.write_status == "unavailable" and result.snapshot == current
    assert result.snapshot.facts == ()


def test_m13_forget_replay_does_not_recreate_a_removed_tombstone() -> None:
    item, _, plan, snapshot = forgotten()
    current = replace(snapshot, facts=())
    result = apply_plan(current, plan, clock=item.clock)
    assert result.replayed and result.write_status == "forgotten" and result.snapshot == current
    assert result.snapshot.facts == ()


def test_m14_hash_alone_cannot_authorize_a_plan_without_incoming_source_policy() -> None:
    item = scenario()
    plan = reseal(MutationPlan("unsigned-save", item.scope, 0, 0, policy_action="save"))
    with pytest.raises(MutationConflict) as caught:
        apply_plan(item.snapshot, plan, clock=item.clock)
    assert str(caught.value) == "mutation_authorization_required" and item.snapshot.facts == ()


def test_m15_reconstructed_write_without_policy_time_is_rejected() -> None:
    item = scenario()
    plan = reseal(replace(write(item), evaluated_at=None))
    with pytest.raises(MutationConflict) as caught:
        apply_plan(item.snapshot, plan, clock=item.clock)
    assert str(caught.value) == "policy_time_required" and item.snapshot.operations == ()


def test_m16_forget_plan_requires_one_deleted_target() -> None:
    item = scenario()
    plan = reseal(MutationPlan("not-a-forget", item.scope, 0, 0, write_status="forgotten", policy_action="forget"))
    with pytest.raises(MutationConflict) as caught:
        apply_plan(item.snapshot, plan, clock=item.clock)
    assert str(caught.value) == "forget_plan_invalid" and item.snapshot.facts == ()


def test_m17_valid_forget_cannot_smuggle_a_neighbor_content_rewrite() -> None:
    item, _, snapshot = written()
    neighbor = scenario(identity="neighbor", text="我习惯用纸本记读书笔记。（合成测试）")
    current = replace(snapshot, facts=(*snapshot.facts, neighbor.fact), sources=(*snapshot.sources, neighbor.source))
    plan = plan_forget(current, item.fact.id, scope=item.scope, operation_id="forget-target")
    change = FactChange(neighbor.fact.id, neighbor.fact, replace(neighbor.fact, text="虚构未经授权的邻居改写"))
    forged = reseal(replace(plan, changes=(*plan.changes, change)))
    with pytest.raises(MutationConflict) as caught:
        apply_plan(current, forged, clock=item.clock)
    assert str(caught.value) == "forget_plan_invalid" and current.fact(neighbor.fact.id) == neighbor.fact


def test_m18_change_identity_must_match_the_target_fact() -> None:
    item = scenario()
    with pytest.raises(ValueError):
        FactChange(item.fact.id, item.fact, replace(item.fact, id="other-fact"))


def test_m19_public_plan_does_not_coerce_scope() -> None:
    item = scenario()
    with pytest.raises(ValueError):
        replace(write(item), scope={"owner_id": SCOPE.owner_id, "subject_id": SCOPE.subject_id})


def test_m20_public_plan_does_not_coerce_untyped_incoming_json() -> None:
    item = scenario()
    with pytest.raises(ValueError):
        replace(write(item), incoming={"text": item.fact.text})


def test_m21_public_plan_does_not_treat_json_as_confirmation() -> None:
    item = scenario()
    with pytest.raises(ValueError):
        replace(write(item), confirmation={"decision": "granted"})


def test_m22_long_term_authorized_categories_are_not_a_character_string() -> None:
    with pytest.raises(ValueError):
        MemorySettings(auto_save_categories="health")


def test_m23_resealed_assistant_claim_cannot_be_written_as_user_memory() -> None:
    item = scenario(assistant=True, text="明镜建议先列三个方案。（合成测试）")
    rejected = write(item)
    assert rejected.policy_action == "reject" and not rejected.changes
    plan = reseal(
        replace(
            rejected, policy_action="save", write_status="saved", changes=(FactChange(item.fact.id, None, item.fact),)
        )
    )
    with pytest.raises(MemoryGuardError) as caught:
        apply_plan(item.snapshot, plan, clock=item.clock)
    assert str(caught.value) == "assistant_cannot_be_user_fact" and item.snapshot.facts == ()


def test_m24_archive_and_undo_keep_every_fact_content_field_and_original_source() -> None:
    item, before, plan = archive()
    archived = apply_plan(before, plan, clock=item.clock)
    assert archived.write_status == "archived" and archived.snapshot.fact(item.fact.id).status == "archived"
    result = undo_plan(archived.snapshot, plan, operation_id="fictional-undo-archive")
    restored = result.snapshot.fact(item.fact.id)
    assert all(getattr(restored, field.name) == getattr(item.fact, field.name) for field in fields(item.fact))
    assert result.snapshot.sources == before.sources and result.snapshot.source(item.source.id).active
    assert not result.snapshot.source(item.source.id).revoked and not result.conflicts
