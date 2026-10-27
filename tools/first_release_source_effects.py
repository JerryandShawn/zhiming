"""Source replay observations; all mutations remain verified candidate native callables."""

from __future__ import annotations

import hashlib
import json
from typing import Any

CENTRAL = ("core_model_accounts", "core_model_batches", "core_model_authorizations", "core_model_usage")
COUNT_FIELDS = frozenset(
    {
        "owners",
        "deleted_draws",
        "tarot_tombstones",
        "draw_tombstones_added",
        "protected_receipts",
        "external_sends",
        "model_calls",
    }
)


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def state(repo: Any, projection: Any) -> dict[str, Any]:
    with repo.transaction() as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        connection.execute("SET LOCAL search_path=pg_catalog")
        return projection(connection)


def central(repo: Any, observed: dict[str, Any], require: Any) -> dict[str, Any]:
    with repo.transaction() as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        for name in CENTRAL:
            require(
                connection.execute("SELECT count(*) AS n FROM mingjing_core." + name).fetchone()["n"] == 0,
                "SOURCE_REPLAY_CENTRAL_CHANGED",
            )
    tables = {"mingjing_core." + name: observed["tables"]["mingjing_core." + name] for name in CENTRAL}
    sequence = observed["sequences"]["mingjing_core.core_model_usage_id_seq"]
    require(sequence == {"last_value": 1, "log_cnt": 0, "is_called": False}, "SOURCE_REPLAY_CENTRAL_CHANGED")
    return dict(tables=tables, sequence=sequence)


def counts(value: Any, require: Any) -> dict[str, int]:
    require(
        type(value) is dict
        and set(value) == COUNT_FIELDS
        and all(type(item) is int and 0 <= item < 2**63 for item in value.values())
        and value["model_calls"] == value["external_sends"] == 0,
        "SOURCE_REPLAY_NATIVE_COUNTS",
    )
    return value


def replay_source(
    value: Any,
    repo: Any,
    deployment: Any,
    monotone: Any,
    original: Any,
    projection: Any,
    audit: Any,
    phase: Any,
    require: Any,
    expected_initial: str,
) -> dict[str, Any]:
    """Do not add an enclosing transaction: native apply commits before checkpoint purge."""
    document = original["ledger"](value, require)
    call = original["native"]
    prior = call(deployment.export_withdrawals, "SOURCE_REPLAY_EXPORT_FAILED", require, repo)
    call(monotone, "SOURCE_REPLAY_STALE_LEDGER", require, prior, document)
    before = state(repo, projection)
    require(digest(before) == expected_initial, "SOURCE_REPLAY_INITIAL_STATE_CHANGED")
    quota = central(repo, before, require)
    legacy = original["legacy_observations"](repo, document, require)
    spans = original["span_observations"](repo, document, require)
    audit()
    phase("first_apply_started")
    first = counts(
        call(deployment.apply_withdrawals, "SOURCE_REPLAY_FIRST_APPLY_FAILED", require, repo, document), require
    )
    phase("first_native_completed")
    audit()
    exported = call(deployment.export_withdrawals, "SOURCE_REPLAY_EXPORT_FAILED", require, repo)
    call(monotone, "SOURCE_REPLAY_STALE_LEDGER", require, document, exported)
    checked = original["erased"](repo, document, require, legacy, spans)
    first_state = state(repo, projection)
    require(central(repo, first_state, require) == quota, "SOURCE_REPLAY_CENTRAL_CHANGED")
    require(original["ledger"](value, require) == document, "REPLAY_LEDGER_CHANGED")
    audit()
    phase("first_verified")
    phase("second_apply_started")
    second = counts(
        call(deployment.apply_withdrawals, "SOURCE_REPLAY_SECOND_APPLY_FAILED", require, repo, document), require
    )
    phase("second_native_completed")
    audit()
    repeated = call(deployment.export_withdrawals, "SOURCE_REPLAY_EXPORT_FAILED", require, repo)
    original["erased"](repo, document, require, legacy, spans)
    second_state = state(repo, projection)
    require(central(repo, second_state, require) == quota, "SOURCE_REPLAY_CENTRAL_CHANGED")
    require(first_state == second_state, "SOURCE_REPLAY_SECOND_STATE_CHANGED")
    require(exported == repeated, "SOURCE_REPLAY_SECOND_EXPORT_CHANGED")
    require(original["ledger"](value, require) == document, "REPLAY_LEDGER_CHANGED")
    audit()
    phase("second_verified")
    return _receipt(before, first_state, second_state, exported, repeated, first, second, checked)


def _receipt(
    before: Any,
    first_state: Any,
    second_state: Any,
    exported: Any,
    repeated: Any,
    first: Any,
    second: Any,
    checked: Any,
) -> dict[str, Any]:
    return {
        "state_before_sha256": digest(before),
        "state_first_sha256": digest(first_state),
        "state_second_sha256": digest(second_state),
        "export_first_sha256": digest(exported),
        "export_second_sha256": digest(repeated),
        "first_counts": first,
        "second_counts": second,
        "checks": checked,
        "second_apply_unchanged": True,
        "central_unchanged": True,
    }
