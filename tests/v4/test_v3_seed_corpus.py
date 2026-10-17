"""Exercise corpus preparation and one real service turn; do not grade model prose."""

import os
from datetime import datetime

import pytest

from mingjing_core.timekit import FrozenClock, get_clock, set_clock
from tests.test_core_pg_channels import FixtureModel
from tests.test_core_runtime import ProgrammableProvider
from tools.eval.schema import load_scenarios
from tools.eval.targets.v3_target import V3Target

V3_SCENARIOS = [scenario for scenario in load_scenarios() if "v3" in scenario.targets]


@pytest.fixture
def corpus_target(monkeypatch):
    dsn = os.getenv("CORE_TEST_DSN")
    if not dsn:
        pytest.skip("requires disposable loopback PostgreSQL 15")
    for name in (
        "KIMI_API_KEY",
        "MOONSHOT_API_KEY",
        "FEISHU_APP_ID",
        "FEISHU_APP_SECRET",
    ):
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    original = get_clock()
    provider = FixtureModel()
    instance = V3Target(dsn=dsn, provider=provider)
    try:
        yield instance, provider
    finally:
        instance.close()
        set_clock(original)


def assert_original_seed_sources(instance, scenario):
    for original in scenario.seed.thread:
        source = instance.repo.get(instance.owner, "message", instance.seeder.ids[original.id])
        assert source["content"] == original.content
        assert source["role"] == original.role
        assert source["channel"] == original.channel
        assert source["at"] == original.at
    for fact in scenario.seed.facts:
        stored = instance.repo.get(instance.owner, "fact", instance.seeder.ids[fact.id], include_deleted=True)
        references = stored["source_refs"]
        assert any(
            ref["message_id"] == instance.seeder.ids[fact.source_message_id] and ref["quote"] == fact.quote
            for ref in references
        ), f"{scenario.id}: seed fact must reference its original history source"


@pytest.mark.parametrize("scenario", V3_SCENARIOS, ids=lambda scenario: scenario.id)
def test_v3_corpus_seed_and_first_turn_use_real_service(corpus_target, scenario):
    instance, provider = corpus_target
    set_clock(FrozenClock(datetime.fromisoformat(scenario.clock)))
    seed = scenario.seed.model_dump(mode="json")
    instance.reset({**seed, "_scenario_id": scenario.id, "_clock": scenario.clock})
    turn = scenario.turns[0]
    if turn.at:
        set_clock(FrozenClock(datetime.fromisoformat(turn.at)))
    payload = turn.model_dump(mode="json", exclude={"expect"}, exclude_none=True)
    result = instance.send({**payload, "_index": 1})
    assert result.error is None, f"{scenario.id}: service error {result.error}"
    assert result.metadata["run_status"] == "succeeded", scenario.id
    assert result.model_calls == len(provider.requests) > 0
    assert instance.repo.fetch_run(instance.owner, result.metadata["run_id"])["status"] == "succeeded"
    assert_original_seed_sources(instance, scenario)


@pytest.mark.parametrize("include_existing_fact", [False, True])
def test_profile_normalization_preserves_existing_and_new_runtime_facts(corpus_target, include_existing_fact):
    instance, _ = corpus_target
    set_clock(FrozenClock(datetime.fromisoformat("2026-10-17T10:30:00+08:00")))
    quote = "我喜欢午后散步"
    instance.provider = ProgrammableProvider(proposal={"quote": quote, "category": "偏好"})
    seed = {"profile": "default_synthetic", "_scenario_id": "normalization"}
    if include_existing_fact:
        seed.update(
            thread=[
                {
                    "id": "old-source",
                    "role": "user",
                    "content": "我不能上夜班。",
                    "at": "2026-10-16T15:00:00+08:00",
                    "channel": "web",
                }
            ],
            facts=[
                {
                    "id": "old-fact",
                    "kind": "constraint",
                    "quote": "我不能上夜班。",
                    "source_message_id": "old-source",
                }
            ],
        )
    instance.reset(seed)
    before = instance.inspect_db()
    normalized_before = [entity for entity in before["entities"] if entity["kind"] == "fact"]
    assert len(before["fact"]) > len(normalized_before)
    assert len(normalized_before) == int(include_existing_fact)
    if include_existing_fact:
        assert normalized_before[0]["id"] == "old-fact"
    result = instance.send({"user": quote, "channel": "web", "_index": 1})
    assert result.error is None
    assert any(receipt["write_status"] == "saved" for receipt in result.receipts)
    after = instance.inspect_db()
    normalized_after = [entity for entity in after["entities"] if entity["kind"] == "fact"]
    assert len(normalized_after) == len(normalized_before) + 1
    assert len(after["fact"]) == len(before["fact"]) + 1
    assert any(entity["data"]["content"] == quote for entity in normalized_after)


def test_initial_profile_remains_effective_when_scenario_clock_is_in_the_future(
    corpus_target,
):
    instance, _ = corpus_target
    set_clock(FrozenClock(datetime.fromisoformat("2099-10-17T23:40:00+08:00")))
    instance.reset({"profile": "default_synthetic", "_scenario_id": "future-profile"})
    snapshot = instance.service.memory.snapshot(instance.owner)
    assert snapshot["profile"]["birth.solar_datetime"] == "1994-03-12 08:20"
    assert snapshot["profile"]["gender"] == "男"
    assert snapshot["facts"]
