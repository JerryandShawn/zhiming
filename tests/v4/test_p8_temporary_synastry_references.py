"""Run-local opt-in reference lifecycle, using an actual synthetic comparison."""

from __future__ import annotations

import json
import pickle
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from mingjing_core.adapters.charts.tool_evidence import (
    content_hash,
    evidence_result,
    pointer,
)
from mingjing_core.skills.temporary_synastry_references import (
    NOTICE,
    TemporarySynastryReferences,
    seal_generated_text,
)
from mingjing_core.skills.temporary_synastry_scope import ConsumedGrant, SynastryBinding
from mingjing_core.timekit.clock import FrozenClock

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def setup():
    result = json.loads(
        (ROOT / "docs/v4/contracts/samples/synastry-ayuan-xiaohe.json").read_bytes()
    )
    scope = result["scope"]
    binding = SynastryBinding(
        scope["owner_user_id"],
        "synthetic-run",
        tuple(scope["subject_ids"]),
        tuple(scope["revisions"]),
        tuple(scope["operation_ids"]),
        "synthetic-compute-operation",
        "synthetic-button-grant",
        result["data"]["kind"],
    )
    clock = FrozenClock(datetime(2026, 10, 27, 0, tzinfo=UTC))
    grant = ConsumedGrant(
        binding,
        clock.now(),
        clock.now() + timedelta(hours=24),
        binding.compute_operation_id,
    )
    state = {"grant": grant, "calls": 0}

    def revalidate(current):
        state["calls"] += 1
        assert current == binding
        return state["grant"]

    def build(**kwargs):
        args = dict(
            clock=clock,
            run_deadline=clock.now() + timedelta(minutes=5),
            revalidate=revalidate,
            enabled=True,
        )
        return TemporarySynastryReferences(binding, **(args | kwargs))

    return result, binding, clock, state, build


def test_defaults_closed_and_missing_grant_rejects_before_result(setup):
    _, binding, _, state, build = setup
    with pytest.raises(ValueError, match="TEMPORARY_PROTOCOL_DISABLED"):
        build(enabled=False).register({}, binding=binding)
    state["grant"] = None
    with pytest.raises(ValueError, match="CITATION_UNAVAILABLE"):
        build().register({}, binding=binding)


def test_actual_result_every_reference_resolves_and_replay_is_idempotent(setup):
    result, binding, _, state, build = setup
    registry = build()
    view = registry.register(result, binding=binding)
    assert registry.register(deepcopy(result), binding=binding) == view
    for category in ("c", "r"):
        for row in view["aliases"][category]:
            value = registry.resolve(
                row["alias"], binding=binding, document_id=view["document_id"]
            )
            assert value == pointer(result, row["path"])
            assert content_hash(value) == row["value_sha256"]
            assert row["document_id"] == view["document_id"]
            assert row["claim_id"] == "claim-" + content_hash(
                [view["document_id"], row["path"], row["value_sha256"]]
            )
    assert state["calls"] > 4
    assert result["document_id"] not in repr(view)
    assert "data" not in view and "scope" not in view


@pytest.mark.parametrize(
    "change",
    [
        {"owner_user_id": "other"},
        {"run_id": "other"},
        {"revisions": (9, 9)},
        {"subject_ids": ("other-a", "other-b")},
        {"kind": "collaboration"},
        {"compute_operation_id": "other"},
        {"grant_id": "other"},
        {"operation_ids": ("other-a", "other-b")},
    ],
)
def test_cross_scope_is_uniform_and_does_not_reveal_existing_result(setup, change):
    result, binding, _, _, build = setup
    registry = build()
    view = registry.register(result, binding=binding)
    for document in (view["document_id"], "missing"):
        with pytest.raises(ValueError, match="^CITATION_UNAVAILABLE$"):
            registry.resolve(
                "c1", binding=replace(binding, **change), document_id=document
            )


@pytest.mark.parametrize(
    "mutation", ["revoked", "revision", "operation", "expiry", "future"]
)
def test_live_grant_revalidated_after_success(setup, mutation):
    result, binding, clock, state, build = setup
    registry = build()
    view = registry.register(result, binding=binding)
    grant = state["grant"]
    if mutation == "revoked":
        grant = replace(grant, revoked=True)
    elif mutation == "revision":
        grant = replace(grant, binding=replace(binding, revisions=(9, 9)))
    elif mutation == "operation":
        grant = replace(grant, consumed_operation_id="other")
    elif mutation == "expiry":
        grant = replace(grant, expires_at=clock.now())
    else:
        grant = replace(grant, confirmed_at=clock.now() + timedelta(hours=1))
    state["grant"] = grant
    with pytest.raises(ValueError, match="CITATION_UNAVAILABLE"):
        registry.resolve("c1", binding=binding, document_id=view["document_id"])
    assert registry._root is None


@pytest.mark.parametrize("seconds", [300, 86400])
def test_run_deadline_and_authorization_expiry_clear_data(setup, seconds):
    result, binding, clock, _, build = setup
    registry = (
        build(run_deadline=clock.now() + timedelta(hours=25))
        if seconds == 86400
        else build()
    )
    view = registry.register(result, binding=binding)
    clock.advance(timedelta(seconds=seconds))
    with pytest.raises(ValueError, match="CITATION_EXPIRED"):
        registry.resolve("c1", binding=binding, document_id=view["document_id"])
    assert registry._root is None and registry._document_id is None


def test_new_run_cannot_use_old_document_or_claim_ids(setup):
    result, binding, _, _, build = setup
    old, new = build(), build()
    left = old.register(result, binding=binding)
    right = new.register(result, binding=binding)
    assert left["document_id"] != right["document_id"]
    assert left["aliases"]["c"][0]["claim_id"] != right["aliases"]["c"][0]["claim_id"]
    with pytest.raises(ValueError, match="CITATION_UNAVAILABLE"):
        new.resolve("c1", binding=binding, document_id=left["document_id"])


@pytest.mark.parametrize(
    "mutation", ["false", "data", "alias", "scope", "kind", "consent"]
)
def test_tampered_worker_result_cannot_register(setup, mutation):
    result, binding, _, _, build = setup
    changed = deepcopy(result)
    if mutation == "false":
        changed["rule_hits"][0]["met"] = False
    elif mutation == "data":
        changed["data"]["as_of_date"] = "2000-01-01"
    elif mutation == "alias":
        changed["aliases"]["c"][0]["path"] = "/data/missing"
    elif mutation == "scope":
        changed["scope"]["owner_user_id"] = "other"
    else:
        changed["data"][mutation] = "wrong"
    with pytest.raises(ValueError, match="TEMPORARY_RESULT_INVALID"):
        build().register(changed, binding=binding)


def test_exception_cleanup_serialization_and_durable_text_redaction(setup):
    result, binding, _, _, build = setup
    registry = build()
    view = registry.register(result, binding=binding)
    with pytest.raises(TypeError, match="TEMPORARY_RESULT_NOT_PERSISTABLE"):
        pickle.dumps(registry)
    assert "synthetic" not in repr(registry)
    with pytest.raises(RuntimeError), registry:
        raise RuntimeError("simulated run fault")
    assert registry._root is None
    with pytest.raises(ValueError, match="CITATION_UNAVAILABLE"):
        registry.resolve("c1", binding=binding, document_id=view["document_id"])
    text = "对方出生资料与解释〔c1〕〔r1〕"
    assert seal_generated_text(text, generated_for_temporary_synastry=True) == NOTICE
    with pytest.raises(ValueError, match="TEMPORARY_GENERATED_TEXT_REQUIRED"):
        seal_generated_text(text, generated_for_temporary_synastry=False)


def test_revocation_between_checks_cannot_return_data(setup):
    result, binding, _, state, build = setup
    registry = build()
    view = registry.register(result, binding=binding)
    calls = 0

    def revalidate(current):
        nonlocal calls
        calls += 1
        return replace(state["grant"], revoked=calls >= 2)

    registry._revalidate = revalidate
    with pytest.raises(ValueError, match="CITATION_UNAVAILABLE"):
        registry.resolve("c1", binding=binding, document_id=view["document_id"])
    assert registry._root is None


def test_same_operation_cannot_silently_replace_computed_content(setup):
    result, binding, _, _, build = setup
    registry = build()
    registry.register(result, binding=binding)
    data = deepcopy(result["data"])
    data["as_of_date"] = "2026-10-28"
    changed = evidence_result(
        result["version"], data, result["rule_hits"], result["sources"], result["scope"]
    )
    with pytest.raises(ValueError, match="TEMPORARY_OPERATION_CONFLICT"):
        registry.register(changed, binding=binding)


@pytest.mark.parametrize(
    "alias", ["c0", "c01", "c999999", "tmp1", "s1", "〔c1〕", "r-1"]
)
def test_non_registered_and_alternate_prefixes_refused(setup, alias):
    result, binding, _, _, build = setup
    registry = build()
    view = registry.register(result, binding=binding)
    with pytest.raises(ValueError, match="CITATION_UNAVAILABLE"):
        registry.resolve(alias, binding=binding, document_id=view["document_id"])


def test_returned_value_and_alias_projection_cannot_mutate_registry(setup):
    result, binding, _, _, build = setup
    registry = build()
    view = registry.register(result, binding=binding)
    view["aliases"]["c"][0]["path"] = "/data/private"
    value = registry.resolve("r1", binding=binding, document_id=view["document_id"])
    value["met"] = False
    assert (
        registry.resolve("r1", binding=binding, document_id=view["document_id"])["met"]
        is True
    )


def test_grant_lifetime_over_24h_or_callback_failure_fails_closed(setup):
    result, binding, clock, state, build = setup
    state["grant"] = replace(
        state["grant"], expires_at=clock.now() + timedelta(hours=25)
    )
    with pytest.raises(ValueError, match="CITATION_UNAVAILABLE"):
        build().register(result, binding=binding)

    def unavailable(current):
        raise RuntimeError("private grant data")

    with pytest.raises(ValueError, match="^CITATION_UNAVAILABLE$"):
        build(revalidate=unavailable).register(result, binding=binding)


def test_boolean_revision_cannot_match_integer_binding(setup):
    result, binding, _, _, build = setup
    scope = deepcopy(result["scope"])
    scope["revisions"][0] = True
    changed = evidence_result(
        result["version"], result["data"], result["rule_hits"], result["sources"], scope
    )
    with pytest.raises(ValueError, match="TEMPORARY_RESULT_INVALID"):
        build().register(changed, binding=binding)


def test_expiry_during_final_grant_read_cannot_return_value(setup):
    result, binding, clock, state, build = setup
    registry = build()
    view = registry.register(result, binding=binding)
    calls = 0

    def slow_revalidate(current):
        nonlocal calls
        calls += 1
        if calls == 2:
            clock.advance(timedelta(minutes=5))
        return state["grant"]

    registry._revalidate = slow_revalidate
    with pytest.raises(ValueError, match="CITATION_EXPIRED"):
        registry.resolve("c1", binding=binding, document_id=view["document_id"])
    assert registry._root is None
