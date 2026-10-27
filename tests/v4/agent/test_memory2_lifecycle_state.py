"""Memory observation recovery preserves original evidence without replaying writes."""

import json
from types import SimpleNamespace

import pytest

from tools.eval.lifecycle_identity import LifecycleError
from tools.eval.targets.v4_memory_actions import MemoryActionDriver
from tools.eval.targets.v4_memory_lifecycle_state import restore_memory, snapshot_memory
from tools.eval.targets.v4_memory_privacy_seed import MemoryPrivacySeeder
from tools.eval.targets.v4_memory_withdraw_driver import MemoryWithdrawDriver


def test_restored_memory_evidence_preserves_order_baseline_and_selected_revision():
    target = SimpleNamespace(repo=None, seed={}, seeder=SimpleNamespace(privacy_layers=[]))
    target.privacy_seed = MemoryPrivacySeeder(target)
    target.memory_actions = MemoryActionDriver(target)
    target.memory_withdrawals = MemoryWithdrawDriver(target)
    target.privacy_seed.query_tokens = ("z", "a")
    target.privacy_seed.source_ids = {"source-2", "source-1"}
    target.privacy_seed.embedding_targets = {("fact", "fact-1")}
    target.privacy_seed.baseline = {"embedding": 3}
    target.memory_withdrawals.original_revisions[("fact", "fact-1")] = 7
    state = json.loads(json.dumps({"memory_observers": snapshot_memory(target)}))
    target.privacy_seed.baseline["embedding"] = 0
    restore_memory(target, state)
    assert target.privacy_seed.query_tokens == ("z", "a")
    assert target.privacy_seed.source_ids == {"source-1", "source-2"}
    assert target.privacy_seed.embedding_targets == {("fact", "fact-1")}
    assert target.privacy_seed.baseline == {"embedding": 3}
    assert target.memory_withdrawals.original_revisions == {("fact", "fact-1"): 7}
    assert target.repo is None  # Attach did not access a DB or reseed business effects.


def test_old_privacy_checkpoint_cannot_invent_a_historical_baseline():
    target = SimpleNamespace(repo=None, seed={}, seeder=SimpleNamespace(privacy_layers=[{"id": "original"}]))
    with pytest.raises(LifecycleError, match="旧断点"):
        restore_memory(target, {})
