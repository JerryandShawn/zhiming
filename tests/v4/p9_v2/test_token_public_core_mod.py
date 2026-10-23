"""Nine independent public K3 flows; no private validators, token logging or external effects."""

from dataclasses import replace
from datetime import timedelta

import pytest
from token_public_support_core_mod import (
    AT,
    GuardLookup,
    SnapshotPort,
    assert_generic_error,
    assert_recovered_first_then_replay,
    assert_unconsumed,
    capability,
    issue,
    sole_record,
)

from mingjing_core.adapters.channels.action_token_contracts import ActionTokenError
from mingjing_core.adapters.channels.action_token_policy_v2 import K3TokenService
from mingjing_core.adapters.channels.action_token_refresh_v2 import MemoryTokenMetadataLookup


def test_r01_snapshot_exception_is_generic_without_consuming_or_refreshing() -> None:
    case = capability()
    lookup = MemoryTokenMetadataLookup(SnapshotPort((), fail=True))
    service = K3TokenService(case.store, clock=case.clock, lookup=lookup)
    with pytest.raises(ActionTokenError) as caught:
        service.consume(case.issued.token, **case.claim)
    assert_generic_error(caught.value)
    assert_unconsumed(case)


def test_r02_list_snapshot_does_not_become_authorized_metadata() -> None:
    case = capability()
    lookup = MemoryTokenMetadataLookup(SnapshotPort(list(case.store.snapshot())))
    service = K3TokenService(case.store, clock=case.clock, lookup=lookup)
    with pytest.raises(ActionTokenError) as caught:
        service.consume(case.issued.token, **case.claim)
    assert_generic_error(caught.value)
    assert_unconsumed(case)


def test_r03_mixed_snapshot_is_rejected_instead_of_selecting_the_good_record() -> None:
    case = capability()
    lookup = MemoryTokenMetadataLookup(SnapshotPort((*case.store.snapshot(), None)))
    service = K3TokenService(case.store, clock=case.clock, lookup=lookup)
    with pytest.raises(ActionTokenError) as caught:
        service.consume(case.issued.token, **case.claim)
    assert_generic_error(caught.value)
    assert_unconsumed(case)


def test_r04_nonfirst_owner_is_found_and_other_revocation_does_not_cross_bindings() -> None:
    case = capability()
    target_claim = {**case.claim, "owner_id": "synthetic-owner-乙", "entity_id": "synthetic-entity-乙"}
    target = issue(case.service, target_claim)
    records = case.store.snapshot()
    first = next(record for record in records if record.claim.owner_id == case.claim["owner_id"])
    second = next(record for record in records if record.claim.owner_id == target_claim["owner_id"])
    lookup = MemoryTokenMetadataLookup(SnapshotPort((first, second)))
    lookup.revoke(first.digest)
    service = K3TokenService(case.store, clock=case.clock, lookup=lookup)
    click = service.consume(target.token, **target_claim)
    assert click.should_execute and not click.refresh_needed and click.operation_id == target.operation_id
    with pytest.raises(ActionTokenError) as caught:
        service.consume(case.issued.token, **case.claim)
    assert_generic_error(caught.value)
    assert all(record.used_at is None for record in records)
    current = {record.claim.owner_id: record for record in case.store.snapshot()}
    assert current[case.claim["owner_id"]].used_at is None and current[target_claim["owner_id"]].used_at == AT


def test_r05_guard_entry_failure_never_reaches_lookup_or_consume() -> None:
    case = capability()
    lookup = GuardLookup(case.lookup, phase="enter")
    service = K3TokenService(case.store, clock=case.clock, lookup=lookup)
    with pytest.raises(ActionTokenError) as caught:
        service.consume(case.issued.token, **case.claim)
    assert_generic_error(caught.value)
    assert lookup.lookup_calls == 0 and case.store.consume_calls == 0
    assert_unconsumed(case)


def test_r06_guard_exit_failure_after_local_consume_only_allows_later_replay() -> None:
    case = capability()
    lookup = GuardLookup(case.lookup, phase="exit")
    service = K3TokenService(case.store, clock=case.clock, lookup=lookup)
    with pytest.raises(ActionTokenError) as caught:
        service.consume(case.issued.token, **case.claim)
    assert_generic_error(caught.value)
    assert sole_record(case).used_at == AT
    lookup.phase = None
    case.clock.at += timedelta(seconds=1)
    replay = service.consume(case.issued.token, **case.claim)
    assert not replay.should_execute and not replay.refresh_needed
    assert replay.consumption is not None and replay.consumption.replayed
    assert replay.operation_id == case.issued.operation_id and replay.consumption.used_at == AT


def test_r07_consume_clock_exception_does_not_burn_token_before_clock_recovery() -> None:
    case = capability()
    case.clock.mode = "error"
    with pytest.raises(ActionTokenError) as caught:
        case.service.consume(case.issued.token, **case.claim)
    assert_generic_error(caught.value)
    assert_unconsumed(case)
    assert_recovered_first_then_replay(case)


def test_r08_naive_consume_clock_does_not_burn_token_before_clock_recovery() -> None:
    case = capability()
    case.clock.mode = "naive"
    with pytest.raises(ActionTokenError) as caught:
        case.service.consume(case.issued.token, **case.claim)
    assert_generic_error(caught.value)
    assert_unconsumed(case)
    assert_recovered_first_then_replay(case)


def test_r09_expired_metadata_with_another_operation_is_invalid_not_refreshable() -> None:
    case = capability()
    record = sole_record(case)
    other = "feishu-card:" + ("0" if case.issued.operation_id != "feishu-card:" + "0" * 64 else "1") * 64
    assert other != case.issued.operation_id
    current = replace(record, operation_id=other)
    lookup = MemoryTokenMetadataLookup(SnapshotPort((current,)))
    service = K3TokenService(case.store, clock=case.clock, lookup=lookup)
    case.clock.at = case.issued.expires_at
    with pytest.raises(ActionTokenError) as caught:
        service.consume(case.issued.token, **case.claim)
    assert_generic_error(caught.value)
    assert_unconsumed(case)
