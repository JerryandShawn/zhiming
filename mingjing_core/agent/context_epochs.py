"""Canonical cache-prefix metadata; no conversation bytes are persisted here."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any

from .context_types import BudgetResult, ContextEpoch, ContextInputError

PREFIX_LAYERS = {"L0", "L2", "L3_STABLE", "L5"}


def _encoded(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _hash(value: Any) -> str:
    return hashlib.sha256(_encoded(value)).hexdigest()


def layer_bytes(budget: BudgetResult, names: set[str]) -> bytes:
    """Canonical message fragments retain their exact bytes when later fragments append."""
    return b"".join(
        _encoded(asdict(message)) + b"\n"
        for layer in budget.layers
        if layer.name in names
        for item in layer.items
        for message in item.messages
    )


def epoch_plan(
    budget: BudgetResult,
    versions: dict[str, int],
    snapshot_revision: int,
    previous: dict[str, Any],
    *,
    invalidated: bool,
) -> ContextEpoch:
    history, window = [], []
    for layer in budget.layers:
        if layer.name not in PREFIX_LAYERS:
            continue
        for item in layer.items:
            for message in item.messages:
                value = asdict(message)
                if layer.name == "L5":
                    history.append(value)
                if layer.name == "L5" and item.key == "history-window":
                    window.append(value)
    hashes = tuple(_hash(value) for value in history)
    generation, epoch = previous.get("generation", 0), previous.get("epoch", 0)
    if any(type(value) is not int or value < 0 for value in (generation, epoch)):
        raise ContextInputError("context_cache_state_invalid")
    old = tuple(previous.get("l5_hashes", ()))
    append_only = hashes[: len(old)] == old
    compressed = any(row.get("action") == "L5_drop" for row in budget.compression_trace)
    window_changed = bool(previous) and previous.get("window_sha256") != _hash(window)
    rewrite = compressed and not append_only or window_changed
    reason = "sources_changed" if invalidated else "compression" if rewrite else None
    if not append_only and reason is None:
        raise ContextInputError("context_l5_append_only_violation")
    if previous and reason is not None:
        epoch += 1
    return ContextEpoch(
        generation,
        epoch,
        hashes,
        hashlib.sha256(layer_bytes(budget, PREFIX_LAYERS - {"L5"})).hexdigest(),
        hashlib.sha256(layer_bytes(budget, PREFIX_LAYERS)).hexdigest(),
        _hash(window),
        dict(versions),
        snapshot_revision,
        reason,
    )
