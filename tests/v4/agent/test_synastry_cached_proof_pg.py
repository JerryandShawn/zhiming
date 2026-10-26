"""Native cache replay is revalidated before a temporary result gains lineage."""

from copy import deepcopy
from datetime import datetime, timedelta

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.adapters.charts.p8_adapter import P8ChartAdapter
from mingjing_core.agent.loop_codec import verified_versions
from mingjing_core.application.agent_synastry import cache_id, cached
from mingjing_core.application.agent_tools_contracts import ToolResult
from mingjing_core.domain.contracts import CoreError

from .test_agent_synastry_pg import begin
from .test_synastry_consent_pg import consent as consent_fixture


@pytest.fixture
def consent(p2_repo):
    return consent_fixture.__wrapped__(p2_repo)


@pytest.mark.parametrize(
    "mutation",
    [
        "document",
        "scope",
        "effects",
        "policy",
        "kind",
        "snapshot",
        "epoch_bool",
        "marker",
        "receipt",
        "end",
        "structure",
    ],
)
def test_matching_completed_journal_and_cache_do_not_bypass_native_result_proof(consent, monkeypatch, mutation):
    h, args, ctx, step, _ = begin(consent)
    result = h.registry.execute("synastry", args, ctx)
    assert result.ok
    h.journal.complete(step, result.model_dump())
    row = h.repo.get("alice", "runtime_step", cache_id(ctx))
    data = deepcopy(row["tool_output"])
    changes = {"tool_output": data}
    if mutation == "document":
        data["data"]["calculation"]["document_id"] = "forged-document"
    elif mutation == "scope":
        data["data"]["calculation"]["scope"]["owner_user_id"] = "bob"
    elif mutation == "effects":
        data["data"]["calculation"]["effects"]["writes"] = True
    elif mutation == "policy":
        data["data"]["record_policy"]["memory"] = True
    elif mutation == "kind":
        changes["arguments"] = dict(args, kind="romantic")
    elif mutation == "snapshot":
        snapshots = deepcopy(row["snapshots"])
        snapshots.reverse()
        changes["snapshots"] = snapshots
    elif mutation == "epoch_bool":
        changes["epoch"] = False
    elif mutation == "marker":
        changes["ephemeral_synastry"] = False
    elif mutation == "receipt":
        data["receipt"] = {"write_status": "saved", "kind": "fact", "id": "invented-fact", "revision": 1}
    elif mutation == "end":
        data["ends_turn"] = True
    else:
        del data["data"]["calculation"]["scope"]
    h.repo.update(
        "alice", "runtime_step", row["id"], changes, expected_revision=row["revision"], operation_id="corrupt-cache"
    )
    # Simulate matching corruption on both native private rows; equality alone must not attest it.
    with h.repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET output=%s WHERE owner=%s AND run_id=%s AND epoch=%s AND seq=%s").format(
                h.repo.table("core_run_steps")
            ),
            (Jsonb(data), "alice", h.run["id"], ctx.epoch, step.seq),
        )
    monkeypatch.setattr(P8ChartAdapter, "synastry", lambda *a: pytest.fail("Corrupt replay must not recalculate"))
    with pytest.raises(CoreError):
        cached(h.service, ctx)
    with pytest.raises(CoreError):
        verified_versions(h.service, h.run, "synastry", ToolResult.model_validate(data))
    assert h.repo.list("alice", "synastry_consent")[-1]["uses_left"] == 0
    assert h.repo.list("alice", "artifact") == h.repo.list("alice", "interpretive_claim") == []
    h.finish()


def test_successful_replay_after_grant_expiry_does_not_reconsume_or_extend_consent(consent, monkeypatch):
    h, args, ctx, step, service = begin(consent)
    result = h.registry.execute("synastry", args, ctx)
    assert result.ok
    h.journal.complete(step, result.model_dump())
    original = h.repo.list("alice", "synastry_consent")[-1]
    h.service.clock.advance(timedelta(hours=25))
    assert h.service.clock.now() > datetime.fromisoformat(original["expires_at"])
    # The replay remains a read of an already consumed result, not another grant use.
    monkeypatch.setattr(P8ChartAdapter, "synastry", lambda *a: pytest.fail("Completed replay must not recalculate"))
    assert cached(h.service, ctx) == result
    versions, records = verified_versions(h.service, h.run, "synastry", result)
    assert records == [] and h.repo.verify_versions("alice", versions)
    current = h.repo.get("alice", "synastry_consent", original["id"])
    assert current == original and current["uses_left"] == 0
    h.finish()
