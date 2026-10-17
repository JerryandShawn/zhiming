"""The baseline exercises the real service and real PostgreSQL, replacing only the model."""

import os
from datetime import datetime

import pytest

from mingjing_core.domain.consultation import ModelUnavailable
from mingjing_core.timekit import FrozenClock, get_clock, set_clock
from tests.test_core_pg_channels import FixtureModel
from tools.eval.targets.local_db import validate_local_dsn
from tools.eval.targets.v3_target import V3Target


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://user@server.example/test",
        "postgresql://user@127.0.0.1/zhiming_core_live",
        "postgresql://user@127.0.0.1/zhiming_core_stage_test",
        "dbname=core_test",
        "host=127.0.0.1 hostaddr=192.0.2.1 dbname=core_test",
        "host=127.0.0.1 dbname=postgres",
        "host=127.0.0.1 dbname=core_test service=remote",
        "postgresql://user@localhost,remote/core_test",
    ],
)
def test_baseline_rejects_remote_or_non_test_dsn_without_connecting(dsn):
    with pytest.raises(ValueError):
        validate_local_dsn(dsn)


def test_baseline_accepts_explicit_loopback_test_database():
    validate_local_dsn("postgresql://core_test@127.0.0.1:55480/core_test")


@pytest.fixture
def target():
    dsn = os.getenv("CORE_TEST_DSN")
    if not dsn:
        pytest.skip("requires disposable PostgreSQL 15")
    original = get_clock()
    set_clock(FrozenClock(datetime.fromisoformat("2026-10-17T10:30:00+08:00")))
    provider = FixtureModel()
    instance = V3Target(dsn=dsn, provider=provider)
    try:
        yield instance, provider
    finally:
        instance.close()
        set_clock(original)


def test_v3_seeds_sources_and_runs_full_service_with_real_call_counts(target):
    instance, provider = target
    instance.reset(
        {
            "_scenario_id": "R02",
            "profile": "empty_profile",
            "facts": [{"id": "night", "kind": "constraint", "content": "我不能上夜班"}],
            "thread": [
                {
                    "role": "assistant",
                    "content": "方案B是先申请内部转岗。",
                    "at": "2026-10-15T21:05:00+08:00",
                    "channel": "feishu",
                }
            ],
        }
    )
    history = instance.inspect_db()["message"]
    assistant = next(row for row in history if row["role"] == "assistant")
    assert assistant["at"] == "2026-10-15T21:05:00+08:00"
    assert assistant["channel"] == "feishu"
    assert len(instance.inspect_db()["fact"]) == 1
    result = instance.send({"user": "那第二个方案怎么做？", "channel": "web", "_index": 1})
    assert result.error is None
    assert result.text
    assert result.metadata["run_status"] == "succeeded"
    assert result.model_calls == len(provider.requests) == 2
    assert provider.requests[0]["payload"]["reference_data"]["today"] == "2026-10-17"
    assert any(
        row["role"] == "assistant" for row in provider.requests[0]["payload"]["reference_data"]["recent_history"]
    )
    assert {row["content"] for row in instance.inspect_db()["fact"]} == {"我不能上夜班"}


def test_reset_replaces_only_its_own_synthetic_schema(target):
    instance, _ = target
    instance.reset({"profile": "empty_profile", "facts": [], "thread": []})
    old_schema = instance.schema
    instance.send({"user": "你好", "channel": "web", "_index": 1})
    instance.reset({"profile": "empty_profile", "facts": [], "thread": []})
    assert instance.schema != old_schema
    assert instance.inspect_db()["message"] == []
    with instance.repo.transaction() as connection:
        assert connection.execute("SELECT to_regnamespace(%s) AS name", (old_schema,)).fetchone()["name"] is None


def test_synthetic_profile_maps_to_existing_confirmed_v3_fields(target):
    instance, _ = target
    instance.reset({"profile": "default_synthetic"})
    profile = instance.service.memory.snapshot(instance.owner)["profile"]
    assert profile["name"] == "阿远"
    assert profile["gender"] == "男"
    assert profile["birth.solar_datetime"] == "1994-03-12 08:20"
    assert profile["birth.timezone_offset"] == 8
    assert profile["birth.location.lng"] == 104.07


def test_unknown_birth_time_retains_date_without_inventing_a_confirmed_time(target):
    instance, _ = target
    instance.reset(
        {
            "profile": "default_synthetic",
            "profile_overrides": {"birth": {"precision": "unknown", "time": None}},
        }
    )
    profile = instance.service.memory.snapshot(instance.owner)["profile"]
    assert profile["birth.precision"] == "unknown"
    assert profile["birth.time_unknown"] is True
    assert profile["birth.solar_datetime"] == "1994-03-12"


def test_brief_uses_one_real_report_source_without_inventing_assistant_history(target):
    instance, provider = target
    instance.reset({"profile": "empty_profile", "_scenario_id": "T13"})
    result = instance.send({"user": "生成今天晨报", "kind": "brief", "channel": "web", "_index": 1})
    assert result.error is None
    messages = instance.inspect_db()["message"]
    assert len(messages) == 1
    assert messages[0]["channel"] == "scheduled_report"
    assert messages[0]["policy"]["origin"] == "system"
    history = provider.requests[0]["payload"]["reference_data"]["recent_history"]
    assert not any(row["role"] == "assistant" for row in history)


@pytest.mark.parametrize("reason,category", [("http", "provider"), ("network", "provider"), ("tool_count", "business")])
def test_v3_distinguishes_provider_outage_from_model_contract_failure(target, monkeypatch, reason, category):
    instance, provider = target

    def fail(**kwargs):
        raise ModelUnavailable("Synthetic provider failure", reason=reason)

    monkeypatch.setattr(provider, "generate", fail)
    instance.reset({"profile": "empty_profile", "_scenario_id": "T01"})
    result = instance.send({"user": "今天几号？", "channel": "web", "_index": 1})
    assert result.error == "ModelUnavailable"
    assert result.metadata["error_category"] == category
    assert result.model_calls == 1
