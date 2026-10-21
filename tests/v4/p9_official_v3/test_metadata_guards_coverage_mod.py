"""Public restore must reject tampered projections rather than convert them to delivery authority."""

import copy

import pytest

from mingjing_core.adapters.channels.cardkit_official_v3 import restore_state, state_metadata

from .isolated_coverage_mod import isolated_p9 as isolated_p9
from .support_mod import TEXT, environment, open_stream, prepare, run_step


def _corrupt(raw: dict, change: str, later_operation: dict | None) -> None:
    fields = {
        "scope": ("scope_fingerprint", "f" * 64),
        "stage": ("stage", "silently_resend"),
        "revision_bool": ("revision", True),
        "counter_order": ("last_acked_sequence", raw["last_reserved_sequence"] + 1),
        "retry_limit": ("close_retries", 2),
        "truthy_ack": ("finalize_acked", 1),
        "close_without_finalize": ("close_acked", True),
        "closed_without_ack": ("stage", "closed"),
        "naive_time": ("last_attempt_at", "2026-10-21T03:00:00"),
        "bad_remote": ("card_id", "not-a-numeric-card"),
        "message_without_card": ("card_id", None),
        "history_not_array": ("history", {"operation": "not-a-list"}),
        "missing_lease": ("lease_state", None),
        "missing_operation": ("operation", None),
        "bad_artifact": ("artifact_fingerprint", "not-a-digest"),
        "extra_secret": ("raw_token", "SYNTHETIC_SECRET_MUST_NOT_BE_ACCEPTED"),
        "acked_wrong_stage": ("stage", "needs_host_decision"),
    }
    if change in fields:
        key, value = fields[change]
        raw[key] = value
    elif change == "history_duplicate":
        raw["history"].append(copy.deepcopy(raw["history"][0]))
    elif change == "operation_in_history":
        raw["history"].append(copy.deepcopy(raw["operation"]))
    elif change == "retry_mismatch":
        raw.update(retry_kind="finalize", retry_reason="synthetic-refusal")
    elif change == "remote_mismatch":
        raw["lease_state"]["card_id"] = "67890"
    else:
        raw["history"].append(later_operation)


@pytest.mark.parametrize(
    "change",
    [
        "scope",
        "stage",
        "revision_bool",
        "counter_order",
        "retry_limit",
        "truthy_ack",
        "close_without_finalize",
        "closed_without_ack",
        "naive_time",
        "bad_remote",
        "message_without_card",
        "history_not_array",
        "history_duplicate",
        "operation_in_history",
        "missing_lease",
        "missing_operation",
        "retry_mismatch",
        "remote_mismatch",
        "bad_artifact",
        "extra_secret",
        "acked_wrong_stage",
        "history_future_sequence",
    ],
)
def test_invalid_persisted_state_cannot_restore_into_a_delivery_capability(change: str) -> None:
    env = environment()
    state = run_step(open_stream(env), env, "update", TEXT[:3])
    raw = state_metadata(state)
    later_operation = None
    if change == "history_future_sequence":
        later_operation = state_metadata(run_step(state, env, "update", TEXT[:4]))["operation"]
    _corrupt(raw, change, later_operation)
    original = copy.deepcopy(raw)
    with pytest.raises(ValueError) as caught:
        restore_state(raw, scope=env.scope)
    assert raw == original
    assert TEXT not in str(caught.value) and "SYNTHETIC_SECRET" not in str(caught.value)


def test_finalization_cannot_claim_a_valid_close_without_the_finalize_history() -> None:
    env = environment()
    finalized = run_step(open_stream(env), env, "finalize", env.artifact.final_card)
    closing = prepare(finalized, env, "close_streaming").state
    raw = state_metadata(closing)
    raw["history"] = [row for row in raw["history"] if row["kind"] != "finalize"]
    with pytest.raises(ValueError):
        restore_state(raw, scope=env.scope)


@pytest.mark.parametrize("change", ["missing_finalize_ack", "closed_without_close_operation", "unconfirmed_finalized"])
def test_close_flags_and_stage_are_not_substitutes_for_bound_remote_acknowledgements(change: str) -> None:
    env = environment()
    old = open_stream(env)
    pending = prepare(old, env, "finalize", env.artifact.final_card)
    if change == "unconfirmed_finalized":
        raw = state_metadata(pending.state)
        raw.update(stage="finalized", finalize_acked=True)
    else:
        finalized = run_step(old, env, "finalize", env.artifact.final_card)
        raw = state_metadata(finalized)
        if change == "missing_finalize_ack":
            raw["finalize_acked"] = False
        else:
            raw.update(stage="closed", close_acked=True)
    with pytest.raises(ValueError):
        restore_state(raw, scope=env.scope)
