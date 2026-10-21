"""Real PG limits survive crash/reclaim and are never authorized by client input."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.agent.journal import Journal
from mingjing_core.agent.loop_policy import RunControl
from mingjing_core.agent.runtime_config import (
    RuntimeConfigError,
    config_hash,
    load_runtime_config,
    validate_runtime_config,
)
from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.application.runtime_limits import RuntimeLimits
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict
from mingjing_core.models.port import ToolCall
from mingjing_core.timekit.clock import get_clock

from .test_agent_runtime_pg import queued
from .test_agent_runtime_pg import repository_fixture as source_fixture
from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer, modify


@pytest.fixture(name="limits_repo")
def repository(p2_repo, monkeypatch):
    yield from source_fixture.__wrapped__(p2_repo, monkeypatch)


def config(**limits):
    raw = load_runtime_config().model_dump()
    raw["interactive"].update(limits)
    return validate_runtime_config(raw)


def invoke(repo, run, port, **options):
    runtime = AgentRuntime(repo, port, SyntheticMeter(), offline=True, **options)
    return runtime.execute(SimpleNamespace(repo=repo), "alice", run["id"], run["lease_token"])


def pin(repo, run):
    return repo.fetch_run("alice", run["id"])["usage"]["agent_runtime"]["limit_epochs"]


def write_usage(repo, run, value):
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET usage=%s WHERE owner='alice' AND id=%s").format(repo.table("core_runs")),
            (Jsonb(value), run["id"]),
        )


def steps(repo, run):
    with repo.transaction("alice") as connection:
        return connection.execute(
            sql.SQL("SELECT kind,output FROM {} WHERE owner='alice' AND run_id=%s ORDER BY seq").format(
                repo.table("core_run_steps")
            ),
            (run["id"],),
        ).fetchall()


@pytest.mark.parametrize(
    "key,value,calls,expected_models,expected_tools",
    [
        ("max_iterations", 1, [ToolCall("clock", "time_context", {})], 1, 1),
        ("max_tools", 1, [ToolCall("first", "time_context", {}), ToolCall("second", "calendar_lookup", {})], 1, 0),
        ("repeat_limit", 2, [ToolCall("clock", "time_context", {})], 2, 2),
    ],
)
def test_lowered_config_actually_bounds_loop(limits_repo, key, value, calls, expected_models, expected_tools):
    repo, run = limits_repo, queued(limits_repo)
    replies = [answer("", calls), answer("", [replace(calls[0], id="repeat")]), answer("不会调用")]
    port = ScriptedPort(replies)
    invoke(repo, run, port, runtime_config=config(**{key: value}))
    rows = steps(repo, run)
    assert len(port.requests) == expected_models
    assert sum(row["kind"] == "tool" for row in rows) == expected_tools
    if key == "repeat_limit":
        assert rows[-1]["output"]["data"]["code"] == "repeated_tool"


def test_config_wall_and_lease_keys_reach_actual_pg_control(limits_repo):
    repo, run = limits_repo, queued(limits_repo)
    raw = config(max_seconds=7).model_dump()
    raw.update(lease_seconds=15, renew_seconds=3)
    configured, observed = validate_runtime_config(raw), []

    def controls(*args, **kwargs):
        observed.append(args[2])
        return RunControl(*args, **kwargs)

    invoke(repo, run, ScriptedPort([answer("完整回答")]), runtime_config=configured, control_factory=controls)
    current = repo.fetch_run("alice", run["id"])
    assert current["deadline_at"] == get_clock().now() + timedelta(seconds=7)
    assert (observed[0].lease_seconds, observed[0].renew_seconds) == (15, 3)
    assert pin(repo, run)["0"]["config_sha256"] == configured.sha256


def test_lane_is_persisted_not_user_depth_and_config_reduces_initial_lease(limits_repo):
    repo, run = limits_repo, queued(limits_repo)
    configured = load_runtime_config()
    run["request"]["depth"] = "deep"
    modify(repo, run, "request=jsonb_set(request,'{depth}','\"deep\"')")
    limits = RuntimeLimits(repo).policy(run, configured)
    assert (limits.depth, limits.lane, limits.iterations) == ("deep", "interactive", 40)
    with repo.transaction("alice") as connection:
        row = connection.execute(
            sql.SQL("SELECT lease_until-now() AS remaining FROM {} WHERE owner='alice' AND id=%s").format(
                repo.table("core_runs")
            ),
            (run["id"],),
        ).fetchone()
    assert 0 < row["remaining"].total_seconds() <= 150


def test_completed_legacy_run_does_not_need_pin_or_new_lease(limits_repo):
    repo, run = limits_repo, queued(limits_repo)
    result = invoke(repo, run, ScriptedPort([answer("原来已完成")]))
    usage = repo.fetch_run("alice", run["id"])["usage"]
    usage["agent_runtime"].pop("limit_epochs")
    write_usage(repo, run, usage)
    port = ScriptedPort([])
    repeated = AgentRuntime(repo, port, SyntheticMeter(), offline=True).execute(
        SimpleNamespace(repo=repo), "alice", run["id"], ""
    )
    assert repeated == result and port.requests == []
    assert "limit_epochs" not in repo.fetch_run("alice", run["id"])["usage"]["agent_runtime"]


def test_existing_journal_gets_one_explicit_legacy_pin_and_same_pin_is_reused(limits_repo):
    repo, run = limits_repo, queued(limits_repo)
    Journal(repo, "alice").next_or_replay(run, kind="model", name="", input_fp="a" * 64)
    old, newer = config(max_iterations=2), config(max_iterations=3)
    assert RuntimeLimits(repo).policy(run, old).iterations == 2
    first = pin(repo, run)
    assert first["0"]["origin"] == "legacy_unpinned_journal"
    assert RuntimeLimits(repo).policy(run, newer).iterations == 2
    assert pin(repo, run) == first


def test_actual_crash_reclaim_keeps_original_limits_and_deadline(limits_repo):
    class CrashPort(ScriptedPort):
        def stream(self, messages, **kwargs):
            if len(self.requests) == 1:
                raise SystemExit("synthetic crash before second request")
            yield from super().stream(messages, **kwargs)

    repo, run = limits_repo, queued(limits_repo)
    port = CrashPort([answer("", [ToolCall("clock", "time_context", {})])])
    with pytest.raises(SystemExit):
        invoke(repo, run, port, runtime_config=config(max_iterations=2))
    original = pin(repo, run)
    old_deadline = repo.fetch_run("alice", run["id"])["deadline_at"]
    modify(repo, run, "lease_until=now()-interval '1 second'")
    reclaimed = repo.claim_run("alice", run["id"], lease_seconds=150)
    result = invoke(repo, reclaimed, ScriptedPort([answer("恢复完成")]), runtime_config=config(max_iterations=3))
    assert result["text"] == "恢复完成"
    assert pin(repo, run) == original and pin(repo, run)["0"]["config"]["interactive"]["max_iterations"] == 2
    assert repo.fetch_run("alice", run["id"])["deadline_at"] == old_deadline
    assert len(steps(repo, run)) == 3


def test_background_lane_gets_background_limits_even_for_standard_depth(limits_repo):
    repo, run = limits_repo, queued(limits_repo)
    modify(repo, run, "lane='background'")
    current = repo.fetch_run("alice", run["id"])
    policy = RuntimeLimits(repo).policy(current, config())
    assert (policy.lane, policy.depth, policy.iterations, policy.seconds, policy.tools_per_step) == (
        "background",
        "standard",
        60,
        1200,
        10,
    )


def test_real_pg_renewal_uses_lowered_lease_and_interval(limits_repo):
    repo, run = limits_repo, queued(limits_repo)
    raw = config().model_dump()
    raw.update(lease_seconds=12, renew_seconds=2)
    policy = RuntimeLimits(repo).policy(run, validate_runtime_config(raw))
    elapsed, original, calls = [0.0], repo.renew_run, []

    def renew(*args, **kwargs):
        calls.append(args[-1])
        return original(*args, **kwargs)

    repo.renew_run = renew
    try:
        control = RunControl(repo, run, policy, monotonic=lambda: elapsed[0])
        elapsed[0] = 3.0
        control.poll()
    finally:
        repo.renew_run = original
    assert calls == [12]
    with repo.transaction("alice") as connection:
        row = connection.execute(
            sql.SQL("SELECT lease_until-now() AS remaining FROM {} WHERE owner='alice' AND id=%s").format(
                repo.table("core_runs")
            ),
            (run["id"],),
        ).fetchone()
    assert 0 < row["remaining"].total_seconds() <= 12


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner", "other"),
        ("run_id", "other"),
        ("subject", "other"),
        ("thread_id", "life:other"),
        ("lane", "background"),
        ("epoch", True),
        ("config_sha256", "0" * 64),
        ("pin_sha256", "0" * 64),
    ],
)
def test_tampered_pin_is_not_repaired_or_published(limits_repo, field, value):
    repo, run = limits_repo, queued(limits_repo)
    RuntimeLimits(repo).policy(run, config())
    usage = repo.fetch_run("alice", run["id"])["usage"]
    usage["agent_runtime"]["limit_epochs"]["0"][field] = value
    write_usage(repo, run, usage)
    port = ScriptedPort([])
    with pytest.raises(EvidenceError):
        invoke(repo, run, port)
    assert port.requests == [] and repo.fetch_run("alice", run["id"])["result"] is None


def test_two_trusted_workers_cannot_overwrite_the_first_epoch_config(limits_repo):
    repo, run = limits_repo, queued(limits_repo)
    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(
            pool.map(
                lambda value: RuntimeLimits(repo).policy(run, value).iterations,
                [config(max_iterations=2), config(max_iterations=3)],
            )
        )
    assert values[0] == values[1] and len(pin(repo, run)) == 1


def test_bad_repository_config_does_not_break_default_v3_constructor(limits_repo, tmp_path, monkeypatch):
    missing = tmp_path / "runtime.yaml"
    monkeypatch.setattr("mingjing_core.agent.runtime_config.CONFIG_PATH", missing)
    service = ConsultationService(limits_repo)
    assert service.runtime is service.runtime_assembly.legacy
    with pytest.raises(RuntimeConfigError):
        AgentRuntime(limits_repo, ScriptedPort([]), SyntheticMeter(), offline=True)
    with pytest.raises(RuntimeConfigError):
        AgentRuntime(limits_repo, ScriptedPort([]), SyntheticMeter(), offline=True, runtime_config={})


def test_new_epoch_retains_prior_config_instead_of_current_repository_config(limits_repo):
    repo, run = limits_repo, queued(limits_repo)
    original = config(max_iterations=2)
    RuntimeLimits(repo).policy(run, original)
    before = pin(repo, run)
    repo.fail_run("alice", run["id"], "synthetic next epoch", run["lease_token"], status="stale")
    repo.prepare_retry("alice", run["id"])
    reclaimed = repo.claim_run("alice", run["id"])
    assert reclaimed["retry_epoch"] == 1
    assert RuntimeLimits(repo).policy(reclaimed, config(max_iterations=3)).iterations == 2
    after = pin(repo, reclaimed)
    assert after["0"] == before["0"] and set(after) == {"0", "1"}
    assert after["1"]["config_sha256"] == original.sha256


@pytest.mark.parametrize("mode", ["cancel", "old_epoch", "bool_epoch", "other_subject", "old_lease"])
def test_pin_requires_current_lease_scope_epoch_and_non_cancelled_run(limits_repo, mode):
    repo, run = limits_repo, queued(limits_repo)
    changed = dict(run)
    if mode == "cancel":
        modify(repo, run, "cancel_requested_at=now()")
    elif mode == "old_epoch":
        changed["retry_epoch"] = 1
    elif mode == "bool_epoch":
        changed["retry_epoch"] = False
    elif mode == "other_subject":
        changed["subject"] = "other"
    else:
        changed["lease_token"] = "wrong"
    with pytest.raises(LeaseConflict if mode == "old_lease" else EvidenceError):
        RuntimeLimits(repo).policy(changed, config())
    assert "limit_epochs" not in repo.fetch_run("alice", run["id"])["usage"].get("agent_runtime", {})


def test_self_consistent_hash_cannot_authorize_config_above_approved_lane_cap(limits_repo):
    repo, run = limits_repo, queued(limits_repo)
    RuntimeLimits(repo).policy(run, config())
    usage = repo.fetch_run("alice", run["id"])["usage"]
    value = usage["agent_runtime"]["limit_epochs"]["0"]
    value["config"]["interactive"]["max_iterations"] = 41
    value["config_sha256"] = config_hash(value["config"])
    value["pin_sha256"] = config_hash({key: item for key, item in value.items() if key != "pin_sha256"})
    write_usage(repo, run, usage)
    with pytest.raises(RuntimeConfigError):
        RuntimeLimits(repo).policy(run, config())
