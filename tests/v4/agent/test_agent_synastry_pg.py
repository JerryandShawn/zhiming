"""Registered native comparison, real isolated worker, no durable profile artifacts."""

from dataclasses import replace
import json
from subprocess import TimeoutExpired

import pytest

from mingjing_core.adapters.charts.p8_adapter import P8ChartAdapter
from mingjing_core.agent.loop_codec import tool_message, verified_versions
from mingjing_core.agent.tools.p8_parameters import Synastry
from mingjing_core.application.agent_synastry import cache_id
from mingjing_core.application.agent_tools_contracts import ToolContext
from mingjing_core.application.synastry_consent import SynastryConsentService
from mingjing_core.domain.contracts import CoreError
from mingjing_core.repositories.privacy_foundation import invalidate_foundation

from .test_synastry_consent_pg import consent as consent_fixture
from .test_toolkit_pg import setup


@pytest.fixture
def consent(p2_repo):
    return consent_fixture.__wrapped__(p2_repo)


def begin(fixture, kind="friendship", grant=True):
    h = setup(fixture.repo, "请合盘，讨论相处方式")
    service = SynastryConsentService(h.repo, clock=h.service.clock)
    if grant:
        card = service.request("alice", "self", "other", kind, h.source["id"], h.run["id"] + ":request")
        service.confirm("alice", card["id"], confirmed=True, expected_revision=1, request_id=h.run["id"] + ":click")
    args = {"other_subject_id": "other", "kind": kind}
    step = h.journal.next_or_replay(
        h.run, kind="tool", name="synastry", input_fp=h.registry.fingerprint("synastry", args)
    )
    ctx = ToolContext.from_step(step, thread_id="life:self", source_ids=(h.source["id"],))
    return h, args, ctx, step, service


@pytest.mark.parametrize("kind", ["romantic", "friendship", "collaboration"])
def test_actual_registered_comparison_temporary_result_and_completed_proof(consent, kind, monkeypatch):
    h, args, ctx, step, _ = begin(consent, kind)
    before = len(h.repo.list("alice", "fact"))
    original = P8ChartAdapter.synastry
    calls = []

    def observe(adapter, request):
        assert getattr(h.repo._local, "connection", None) is None
        assert request["consent"] == "user_confirmed"
        calls.append(1)
        return original(adapter, request)

    monkeypatch.setattr(P8ChartAdapter, "synastry", observe)
    result = h.registry.execute("synastry", args, ctx)
    assert result.ok, result.model_dump()
    assert result.data["calculation"]["version"] == "p8-synastry-v1"
    if kind == "friendship":
        from copy import deepcopy

        from mingjing_core.application.synastry_result import verify_synastry

        native = result.data["calculation"]
        snapshots = h.repo.get("alice", "runtime_step", cache_id(ctx))["snapshots"]
        for field, value in (("scope", {}), ("document_id", "forged"), ("effects", {"writes": 1, "model_calls": 0})):
            altered = deepcopy(native)
            altered[field] = value
            with pytest.raises(CoreError):
                verify_synastry(altered, "alice", snapshots, ctx.operation_id, kind)
    with pytest.raises(CoreError):
        verified_versions(h.service, h.run, "synastry", result)
    h.journal.complete(step, result.model_dump())
    versions, records = verified_versions(h.service, h.run, "synastry", result)
    assert records == [] and h.repo.verify_versions("alice", versions)
    public = json.loads(tool_message("comparison", result, "cycle").content)["data"]
    assert "time_basis" not in public and "natal_at_utc" not in public["comparison"]["astro"]
    assert "rule_hits" not in public and "aliases" not in public
    assert public["record_policy"] == {"memory": False, "profile": False, "reflection": False, "forward": False}
    assert h.registry.execute("synastry", args, ctx) == result and calls == [1]
    assert len(h.repo.list("alice", "fact")) == before
    for name in ("chart", "note", "profile_doc", "artifact", "interpretive_claim"):
        assert h.repo.list("alice", name) == []
    forged = result.model_copy(deep=True)
    forged.data["calculation"]["data"]["kind"] = "forged"
    with pytest.raises(CoreError):
        verified_versions(h.service, h.run, "synastry", forged)
    h.finish()


def test_missing_consent_creates_real_card_without_calculation_and_completed_pending_replays(consent, monkeypatch):
    h, args, ctx, step, service = begin(consent, grant=False)
    monkeypatch.setattr(P8ChartAdapter, "synastry", lambda *a: pytest.fail("No consent means no calculation"))
    result = h.registry.execute("synastry", args, ctx)
    assert not result.ok and result.data["code"] == "CONSENT_REQUIRED"
    assert "1992" not in json.dumps(result.model_dump())
    card = service.card("alice", result.data["confirmation_id"])
    assert card["state"] == "pending_confirmation"
    h.journal.complete(step, result.model_dump())
    service.confirm("alice", card["id"], confirmed=True, expected_revision=1, request_id="actual-click")
    assert h.registry.execute("synastry", args, ctx) == result
    h.finish()


@pytest.mark.parametrize("private,crisis", [(True, False), (False, True)])
def test_private_or_crisis_hides_tool_before_consuming(consent, private, crisis):
    h, args, ctx, _, _ = begin(consent)
    ctx = replace(ctx, incognito=private, crisis=crisis)
    result = h.registry.execute("synastry", args, ctx)
    assert not result.ok and result.data["code"] == "tool_unavailable"
    assert h.repo.list("alice", "synastry_consent")[-1]["uses_left"] == 1
    h.finish()


def test_timeout_does_not_repeat_an_uncertain_local_calculation_or_restore_consent(consent, monkeypatch):
    h, args, ctx, _, _ = begin(consent)
    calls = []

    def timeout(*a):
        calls.append(1)
        raise TimeoutExpired("private-path", 45, stderr="private-detail")

    monkeypatch.setattr(P8ChartAdapter, "synastry", timeout)
    for _ in range(2):
        result = h.registry.execute("synastry", args, ctx)
        assert not result.ok and "private" not in json.dumps(result.model_dump())
    assert calls == [1]
    assert h.repo.list("alice", "synastry_consent")[-1]["uses_left"] == 0
    h.finish()


def test_other_person_withdrawal_clears_temporary_cache_and_native_step_output(consent):
    h, args, ctx, step, _ = begin(consent)
    result = h.registry.execute("synastry", args, ctx)
    assert result.ok
    h.journal.complete(step, result.model_dump())
    fact = h.repo.list("alice", "fact", subject="other")[0]
    invalidate_foundation(h.repo, "alice", [fact["id"]], [])
    assert h.repo.get("alice", "runtime_step", cache_id(ctx), include_deleted=True)["status"] == "deleted"
    with pytest.raises(CoreError):
        verified_versions(h.service, h.run, "synastry", result)
    with h.repo.transaction("alice") as connection:
        from psycopg import sql

        row = connection.execute(
            sql.SQL("SELECT output,error_code FROM {} WHERE owner=%s AND run_id=%s AND seq=%s").format(
                h.repo.table("core_run_steps")
            ),
            (ctx.owner, ctx.run_id, ctx.seq),
        ).fetchone()
    assert row["output"] is None and row["error_code"] == "SOURCE_REVOKED"
    h.finish()


@pytest.mark.parametrize("extra", [{"consent": "user_confirmed"}, {"birth": {}}, {"owner": "bob"}])
def test_model_schema_never_grants_scope_or_consent(extra):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Synastry(other_subject_id="other", kind="friendship", **extra)


def test_non_web_entry_returns_go_to_web_without_computation_or_card(consent, monkeypatch):
    repo = consent.repo
    repo.bind_channel("alice", "feishu", "synthetic-person")
    h = setup(repo, "请合盘", channel="feishu", external_id="synthetic-person")
    monkeypatch.setattr(P8ChartAdapter, "synastry", lambda *a: pytest.fail("Web confirmation only"))
    result, _ = h.call("synastry", {"other_subject_id": "other", "kind": "friendship"})
    assert not result.ok and result.data["code"] == "CONSENT_REQUIRED" and "去网页" in result.summary
    assert repo.list("alice", "synastry_consent") == []
    h.finish()


@pytest.mark.parametrize("mode", ["cancelled", "profile_changed"])
def test_actual_calculation_finishing_after_authority_change_is_not_published(consent, monkeypatch, mode):
    h, args, ctx, _, _ = begin(consent)
    original = P8ChartAdapter.synastry

    def changed(adapter, request):
        result = original(adapter, request)
        if mode == "cancelled":
            h.repo.fail_run("alice", h.run["id"], "synthetic-stop", h.run["lease_token"], status="cancelled")
        else:
            fact = h.repo.list("alice", "fact", subject="other")[0]
            h.repo.update("alice", "fact", fact["id"], {"value": "changed"}, expected_revision=fact["revision"])
        return result

    monkeypatch.setattr(P8ChartAdapter, "synastry", changed)
    result = h.registry.execute("synastry", args, ctx)
    assert not result.ok
    cache = h.repo.get("alice", "runtime_step", cache_id(ctx))
    assert "tool_output" not in cache
    assert h.repo.list("alice", "artifact") == h.repo.list("alice", "chart") == []
    if mode != "cancelled":
        h.finish()


def test_native_case_source_is_eligible_without_widening_person_scope(consent):
    h = consent
    case = h.memory.create_case("alice", "self", "合成相处事项", operation_id="case-one")
    source = h.memory.receive("alice", content="请合盘", source_id="case-source", case_ids=[case["id"]])
    card = h.service.request("alice", "self", "other", "friendship", source["id"], "case-card")
    assert card["state"] == "pending_confirmation"
    foreign = h.memory.create_case("alice", "other", "另一人物事项", operation_id="case-other")
    h.repo.update("alice", "message", source["id"], {"case_ids": [foreign["id"]]}, expected_revision=source["revision"])
    with pytest.raises(CoreError):
        h.service.confirm("alice", card["id"], confirmed=True, expected_revision=1, request_id="wrong-person-case")


def test_grant_request_from_previous_turn_is_in_withdrawal_dependency_closure(consent):
    first, args, ctx, step, service = begin(consent, grant=False)
    pending = first.registry.execute("synastry", args, ctx)
    first.journal.complete(step, pending.model_dump())
    service.confirm(
        "alice", pending.data["confirmation_id"], confirmed=True, expected_revision=1, request_id="click-first"
    )
    first.finish()
    second, args, ctx, step, _ = begin(consent, grant=False)
    result = second.registry.execute("synastry", args, ctx)
    assert result.ok
    second.journal.complete(step, result.model_dump())
    versions, _ = verified_versions(second.service, second.run, "synastry", result)
    assert "message:" + first.source["id"] in versions
    assert "entity:synastry_consent:" + pending.data["confirmation_id"] in versions
    invalidate_foundation(second.repo, "alice", [], [first.source["id"]])
    assert second.repo.get("alice", "runtime_step", cache_id(ctx), include_deleted=True)["status"] == "deleted"
    assert not second.repo.verify_versions("alice", versions)
    second.finish()


def test_scripted_agent_receives_temporary_projection_and_finalizes_without_saved_claims(consent):
    from mingjing_core.application.agent_finalization import AgentFinalizer
    from mingjing_core.models.port import ToolCall

    from .test_loop_cycle_support import ScriptedPort, answer, cycle, prepare

    repo = consent.repo
    run, registry, frozen = prepare(repo, "请合盘，讨论相处方式")
    service = SynastryConsentService(repo, clock=registry.service.clock)
    card = service.request("alice", "self", "other", "friendship", run["request"]["source_message_id"], "loop-card")
    service.confirm("alice", card["id"], confirmed=True, expected_revision=1, request_id="loop-click")
    port = ScriptedPort(
        [
            answer("", [ToolCall("compare", "synastry", {"other_subject_id": "other", "kind": "friendship"})]),
            answer("本次比较仅供讨论相处方式，不保证关系结果；资料和结果没有写入长期记忆或命理档案。"),
        ]
    )
    outcome = cycle(port, registry, run, frozen).execute()
    assert outcome.stop_reason == "completed"
    message = next(message for message in port.requests[-1]["messages"] if message.role == "tool")
    data = json.loads(message.content)["data"]
    assert data["adapter_mode"] == "p8_synastry_transient" and data["comparison"]["bazi"]
    assert "calculation" not in data and "time_basis" not in data
    assert "rule_hits" not in data and data["reference_policy"] == "native_step_verified_no_reference_aliases"
    assert "registered_aliases" not in data
    assert not any(key.startswith(("c", "r")) and key[1:].isdigit() for key in outcome.alias_map)
    final = AgentFinalizer(repo).finalize(
        run,
        text=outcome.text,
        alias_map=outcome.alias_map,
        versions=outcome.versions,
        snapshot_revision=frozen.snapshot_revision,
        usage=outcome.usage,
    )
    assert final["schema"] == "core4.0" and final["used_claim_ids"] == []
    assert repo.list("alice", "chart") == repo.list("alice", "artifact") == repo.list("alice", "note") == []
