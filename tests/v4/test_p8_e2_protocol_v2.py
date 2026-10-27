"""C0-C4 visibility, option scoring and independent BaziQA conversation checks."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from typing import Any

import pytest

from mingjing_core.adapters.charts.benchmarks.protocol_v2 import (
    RequestV2,
    run_configuration_v2,
)
from mingjing_core.adapters.charts.benchmarks.scripted_v2 import fixtures
from mingjing_core.adapters.charts.benchmarks.statistics_v2 import paired_comparison


def chart(_: Any) -> dict[str, Any]:
    return {
        "artifacts": {
            "b": {
                "id": "b",
                "system": "bazi",
                "data": {
                    "pillars": {"hour": {"zhi": "辰"}},
                    "p8": {
                        "rule_hits": ["SECRET_MET_HIT"],
                        "rule_assessments": ["SECRET_FALSE_ASSESSMENT"],
                        "rule_evaluations": ["SECRET_RULES"],
                    },
                },
            },
            "z": {"id": "z", "system": "ziwei", "data": {"palaces": []}},
        }
    }


def skill(system: str) -> dict[str, Any]:
    return {"system": system, "context": f"synthetic skill {system}"}


def hits(_: Any) -> list[dict[str, Any]]:
    return [
        {"rule_id": "synthetic-rule", "system": "bazi", "artifact_id": "b", "met": True}
    ]


def choose(request: RequestV2) -> str:
    return next(
        letter for letter, text in request.question["options"].items() if text == "辰"
    )


def test_c0_never_computes_chart_loads_skills_or_evaluates_rules() -> None:
    def unavailable(_: Any) -> Any:
        raise AssertionError("forbidden provider called")

    def answer(request: RequestV2) -> str:
        assert request.chart_bundle == {} and request.chart_text is None
        assert request.skills == request.rule_hits == ()
        return choose(request)

    result = run_configuration_v2(
        fixtures()[:1],
        "C0",
        unavailable,
        unavailable,
        answer,
        seed=3,
        rule_provider=unavailable,
    )
    assert result["summary"]["accuracy"] == 1


@pytest.mark.parametrize("configuration", ["C1", "C2", "C3"])
def test_chart_skills_and_rule_ablations_do_not_leak(configuration: str) -> None:
    def answer(request: RequestV2) -> str:
        assert "answer" not in request.question
        visible = json.dumps([request.chart_bundle, request.chart_text])
        assert "SECRET" not in visible
        if configuration == "C1":
            assert request.chart_text is not None and request.chart_bundle == {}
            assert request.skills == request.rule_hits == ()
        else:
            assert request.chart_text is None and request.chart_bundle
            assert {row["system"] for row in request.skills} == {"bazi", "ziwei"}
            assert bool(request.rule_hits) is (configuration == "C3")
        return choose(request)

    result = run_configuration_v2(
        fixtures()[:1], configuration, chart, skill, answer, seed=17, rule_provider=hits
    )
    assert result["outcomes"][0]["correct"]


@pytest.mark.parametrize("configuration,ordered", [("C4a", True), ("C4b", False)])
def test_specialists_have_one_system_no_sibling_outputs_and_srp_switch(
    configuration: str, ordered: bool
) -> None:
    requests: list[RequestV2] = []

    def answer(request: RequestV2) -> str:
        requests.append(request)
        if request.stage == "specialist":
            assert {
                row["system"] for row in request.chart_bundle["artifacts"].values()
            } == {request.system}
            assert all(
                row["system"] == request.system
                for row in request.skills + request.rule_hits
            )
            assert request.specialist_outputs == request.history == ()
            assert request.ordered_time_layers is ordered
            assert ("必须按程序给定顺序" in request.instructions) is ordered
            return '{"claims":[],"gaps":["synthetic"]}'
        assert request.stage == "synthesis"
        assert {row["system"] for row in request.specialist_outputs} == {
            "bazi",
            "ziwei",
        }
        return choose(request)

    result = run_configuration_v2(
        fixtures()[:1], configuration, chart, skill, answer, seed=23, rule_provider=hits
    )
    assert result["protocol_stage_calls"] == len(requests) == 3
    assert result["outcomes"][0]["correct"]


@pytest.mark.parametrize(
    "bad",
    [
        {"rule_id": "not-met", "artifact_id": "b", "system": "bazi", "met": False},
        {
            "rule_id": "wrong-chart",
            "artifact_id": "other",
            "system": "bazi",
            "met": True,
        },
        {"rule_id": "wrong-system", "artifact_id": "b", "system": "ziwei", "met": True},
    ],
)
def test_unbound_or_false_hits_cannot_enter_c3(bad: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="not_bound"):
        run_configuration_v2(
            fixtures()[:1],
            "C3",
            chart,
            skill,
            choose,
            seed=3,
            rule_provider=lambda _: [bad],
        )


def test_relabeling_is_inverted_for_scoring_and_reproducible_across_configs() -> None:
    first = run_configuration_v2(fixtures()[:1], "C0", chart, skill, choose, seed=12)
    second = run_configuration_v2(fixtures()[:1], "C1", chart, skill, choose, seed=12)
    a, b = first["outcomes"][0]["trials"][0], second["outcomes"][0]["trials"][0]
    assert a["option_mapping"] == b["option_mapping"]
    assert a["canonical_selection"] == b["canonical_selection"] == "A"
    assert first["outcomes"][0]["correct"] and second["outcomes"][0]["correct"]


def test_five_independent_trials_require_three_correct_not_a_plurity() -> None:
    def answer(request: RequestV2) -> str:
        if request.trial < 2:
            return choose(request)
        return next(
            letter
            for letter, text in request.question["options"].items()
            if text != "辰"
        )

    result = run_configuration_v2(
        fixtures()[:1], "C0", chart, skill, answer, seed=5, repeats=5
    )
    assert result["scoring"] == "at_least_3_correct_trials"
    assert sum(row["correct"] for row in result["outcomes"][0]["trials"]) == 2
    assert result["outcomes"][0]["correct"] is False


def test_baziqa_five_question_history_has_no_key_or_grading_and_resets_per_case() -> (
    None
):
    records = [
        replace(
            fixtures()[0],
            id=f"q-{case}-{index}",
            case_id=f"case-{case}",
            source="BaziQA",
        )
        for case in range(2)
        for index in range(5)
    ]
    histories: list[int] = []

    def answer(request: RequestV2) -> str:
        histories.append(len(request.history))
        for message in request.history:
            assert "correct" not in message and "answer" not in message
            if message["role"] == "user":
                assert "answer" not in message["question"]
        return choose(request)

    run_configuration_v2(records, "C0", chart, skill, answer, seed=8, repeats=5)
    assert histories == [0, 2, 4, 6, 8] * 10


def test_mingli_questions_remain_independent_even_when_case_is_shared() -> None:
    records = [
        replace(fixtures()[0], id=f"q-{index}", source="MingLi-Bench")
        for index in range(5)
    ]

    def answer(request: RequestV2) -> str:
        assert request.history == ()
        return choose(request)

    run_configuration_v2(records, "C0", chart, skill, answer, seed=1)


def test_mutating_request_cannot_change_input_charts_or_next_trial() -> None:
    bundle = chart(None)
    original = deepcopy(bundle)

    def answer(request: RequestV2) -> str:
        assert (
            request.chart_bundle["artifacts"]["b"]["data"]["pillars"]["hour"]["zhi"]
            == "辰"
        )
        selected = choose(request)
        request.chart_bundle["artifacts"]["b"]["data"]["pillars"]["hour"]["zhi"] = (
            "篡改"
        )
        return selected

    run_configuration_v2(
        fixtures()[:1], "C2", lambda _: bundle, skill, answer, seed=1, repeats=5
    )
    assert bundle == original


@pytest.mark.parametrize("configuration,repeats", [("C5", 1), ("C0", 3), ("C0", True)])
def test_invalid_configuration_or_repeat_count_is_rejected(
    configuration: str, repeats: int
) -> None:
    with pytest.raises(ValueError):
        run_configuration_v2(
            fixtures()[:1], configuration, chart, skill, choose, seed=1, repeats=repeats
        )


@pytest.mark.parametrize("field", ["text", "options", "answer"])
def test_same_id_with_changed_scoring_content_is_not_the_same_paired_question(
    field: str,
) -> None:
    original = fixtures()[0]
    changes = {
        "text": "changed synthetic text",
        "options": tuple(
            (letter, text + "changed") for letter, text in original.options
        ),
        "answer": "B",
    }
    changed = replace(original, **{field: changes[field]})
    first = run_configuration_v2([original], "C0", chart, skill, lambda _: "A", seed=1)
    second = run_configuration_v2([changed], "C0", chart, skill, lambda _: "A", seed=1)
    with pytest.raises(ValueError, match="same_unique_question_set"):
        paired_comparison(first["outcomes"], second["outcomes"])
    assert (
        original.scoring_fingerprint()
        == replace(original, birth=fixtures()[1].birth).scoring_fingerprint()
    )
