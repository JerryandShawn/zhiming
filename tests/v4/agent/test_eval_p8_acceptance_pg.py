"""R40: the thirteen P8 acceptance scenarios on the real v4 target with ScriptedProvider only."""

from __future__ import annotations

from copy import deepcopy

import pytest

from mingjing_core.adapters.charts.benchmarks.acceptance_scenarios import P8Scenario, load_p8_scenarios
from tools.eval.engine import evaluate_scenario
from tools.eval.schema import load_scenarios
from tools.eval.targets.v4_target import V4Target

from .test_eval_v4_pg import target as target_fixture

IDS = [case.id for case in load_p8_scenarios()]


@pytest.fixture
def target(monkeypatch: pytest.MonkeyPatch):
    yield from target_fixture.__wrapped__(monkeypatch)


def case(identity: str) -> P8Scenario:
    return next(row for row in load_p8_scenarios() if row.id == identity)


def test_registered_ids_are_new_and_do_not_touch_the_legacy_eighty() -> None:
    legacy = {row.id for row in load_scenarios()}
    assert len(IDS) == 13 and len(legacy) == 80 and not legacy & set(IDS)


@pytest.mark.parametrize("identity", IDS)
def test_p8_acceptance_on_real_target(identity: str, target: V4Target) -> None:
    observed = evaluate_scenario(case(identity), target, target_name="v4")
    assert observed["status"] == "passed", observed["failed_assertions"]
    observations = target.inspect_db().get("p8_acceptance")
    assert observations is not None and set(observations["engine_calls"]) >= {"synastry", "window_search"}


def test_observations_ignore_scripted_db_declarations(target: V4Target) -> None:
    forged = deepcopy(case("P8SY01").model_dump(mode="json"))
    for action in forged["scripted"][0]["model"]:
        if "db" in action:
            action["db"]["p8_acceptance"]["engine_calls"]["synastry"] = 1
            action["db"]["p8_acceptance"]["refusal_code"] = "NONE"
    evaluate_scenario(P8Scenario.model_validate(forged), target, target_name="v4")
    actual = target.inspect_db()["p8_acceptance"]
    assert actual["engine_calls"]["synastry"] == 0 and actual["refusal_code"] == "CONSENT_REQUIRED"


def test_wrong_expected_engine_call_count_fails(target: V4Target) -> None:
    wrong = deepcopy(case("P8DT01").model_dump(mode="json"))
    wrong["turns"][0]["expect"]["db"][0]["equals"] = 2
    observed = evaluate_scenario(P8Scenario.model_validate(wrong), target, target_name="v4")
    assert observed["status"] == "failed"
