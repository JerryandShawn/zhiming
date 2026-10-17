"""Date scope and chart structures must match reviewed contracts and real engines."""

import os
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from tools.eval.build_chart_goldens import calculate_golden
from tools.eval.chart_goldens import ChartGolden, load_golden, stability_checks, structure_checks
from tools.eval.judges import check_assertions
from tools.eval.schema import load_scenario
from tools.eval.targets.base import TurnResult

ROOT = Path(__file__).resolve().parents[2]


def test_t14_uses_reviewed_week_boundary_and_rejects_the_old_weekday_scope() -> None:
    scenario = load_scenario(ROOT / "tools/eval/scenarios/T14.yaml")
    assert scenario.turns[0].user == "我这周还有什么安排吗？"
    expected = scenario.turns[0].expect.model_dump(exclude_unset=True)
    good = check_assertions(expected, TurnResult(text="本周没有已知安排，面试在下周三21号。"))
    bad = check_assertions(expected, TurnResult(text="这周三10月21日有面试，下周再看。"))
    assert all(check.passed for check in good)
    assert not all(check.passed for check in bad)


@pytest.mark.parametrize("candidate", ["木火", "金水", "土", "暂以调候用水为候选"])
def test_c03_has_no_fixed_favorable_element_answer(candidate: str) -> None:
    text = f"按子平旺衰口径，结合日主与月令盘面，候选方向为{candidate}〔c1〕，这里只作参考。"
    assert all(structure_checks(text).values())


@pytest.mark.parametrize(
    ("text", "failure"),
    [
        ("按子平旺衰口径参考月令，你的方向需结合盘面。", "citation"),
        ("根据盘面月令，候选方向是木〔c1〕。", "school"),
        ("按子平派，方向是木〔c1〕。", "basis"),
        ("按子平旺衰口径和月令，一定会成功〔c1〕。", "no_absolutes"),
        ("按调候派结合盘面，你注定发财〔c1〕。", "no_absolutes"),
        ("按子平旺衰口径和月令，喜用神规则尚未实现〔c1〕。", "no_rule_gap"),
    ],
)
def test_c03_structure_rejects_missing_basis_absolute_claims_and_rule_gaps(text: str, failure: str) -> None:
    assert structure_checks(text)[failure] is False


def test_c03_does_not_turn_a_negated_absolute_into_a_positive_prediction() -> None:
    text = "按调候派结合日主盘面，可考虑候选方向〔c1〕，并非注定成功，也不是一定发财。"
    assert structure_checks(text)["no_absolutes"] is True


@pytest.mark.parametrize("claim", ["不是不一定", "并非不注定", "不代表不必然"])
def test_c03_double_negation_does_not_bypass_absolute_claim_check(claim: str) -> None:
    assert structure_checks("按子平派结合日主盘面〔c1〕，" + claim + "成功。")["no_absolutes"] is False


def test_c06_fixture_contains_computed_branches_and_honest_coverage() -> None:
    golden = load_golden()
    assert golden.sampled_stable is False
    assert len(golden.samples) == 5
    assert len(golden.boundary_probes) == 2
    assert [(branch.label, branch.major_stars) for branch in golden.branches] == [
        ("寅时", ["紫微", "破军"]),
        ("卯时", ["天机"]),
    ]
    assert golden.sampling["coverage"] == "sampled_not_continuous"
    assert golden.external_cross_check == "deferred_to_P8"


@pytest.mark.parametrize(
    "answer",
    [
        "五个采样点主星稳定。寅时为紫微、破军；卯时为天机。",
        "五个采样点不稳定。寅时为天机；卯时为紫微、破军。",
        "五个采样点不稳定。卯时为紫微、破军；辰时为天机。",
        "五个采样点不稳定，不列任何分支。",
    ],
)
def test_c06_rejects_wrong_stability_swapped_stars_and_the_old_civil_hour_assumption(answer: str) -> None:
    assert not all(stability_checks(answer, load_golden()).values())


def test_c06_correct_calculated_branches_pass() -> None:
    answer = "五个采样点的主星不一致。寅时分支为紫微、破军；卯时分支为天机。采样不稳定。"
    assert all(stability_checks(answer, load_golden()).values())


@pytest.mark.parametrize("mutation", ["stability", "stars", "label"])
def test_golden_summary_cannot_disagree_with_its_engine_samples(mutation: str) -> None:
    value = deepcopy(load_golden().model_dump())
    if mutation == "stability":
        value["sampled_stable"] = True
    elif mutation == "stars":
        value["branches"][0]["major_stars"] = ["天机"]
    else:
        value["branches"][0]["label"] = "辰时"
    with pytest.raises(ValidationError):
        ChartGolden.model_validate(value)


def test_recorded_c06_golden_matches_the_real_isolated_chart_engine() -> None:
    python = os.getenv("CHART_PYTHON")
    if not python:
        candidates = [ROOT / ".venv-charts/Scripts/python.exe", ROOT / ".venv-charts/bin/python"]
        python = next((str(path) for path in candidates if path.is_file()), None)
    assert python, "Configure the isolated Charts interpreter before claiming C06 calculation verification"
    actual = calculate_golden(python)
    assert actual == load_golden()
