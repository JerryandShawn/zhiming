"""Offline C0-C4 request plans; actual Agent/alias/model execution stays external."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .contexts_v2 import context, hit_list, specialist_context, systems
from .controls_v2 import shuffle_options
from .eligibility_v2 import YearReview, question_year, select_questions
from .experiment import parse_selection
from .records import BirthMetadata, Question, fingerprint
from .statistics_v2 import accuracy_summary

CONFIGURATIONS_V2 = ("C0", "C1", "C2", "C3", "C4a", "C4b")


def _question_chart(
    provider: Callable[[BirthMetadata], dict[str, Any]],
    record: Question,
    review: YearReview | None,
) -> dict[str, Any]:
    method = getattr(provider, "for_question", None)
    if callable(method):
        return method(record, review=review)
    if record.source in ("MingLi-Bench", "BaziQA"):
        raise ValueError("professional_question_requires_question_aware_chart_provider")
    # Synthetic request-plan callbacks retain their previous isolated unit-test API.
    return provider(record.birth)


def _chart_binding(provider: Any, configuration: str) -> str:
    if configuration == "C0":
        return "no_chart_c0"
    return (
        "question_aware_annual_view"
        if callable(getattr(provider, "for_question", None))
        else "synthetic_callback_time_layers_unverified"
    )


@dataclass(frozen=True)
class RequestV2:
    configuration: str
    stage: str
    system: str | None
    trial: int
    question: dict[str, Any]
    birth: dict[str, Any]
    chart_bundle: dict[str, Any]
    chart_text: str | None
    skills: tuple[dict[str, Any], ...]
    rule_hits: tuple[dict[str, Any], ...]
    ordered_time_layers: bool | None
    history: tuple[dict[str, Any], ...]
    specialist_outputs: tuple[dict[str, str], ...]
    instructions: str


def _request(
    record: Question,
    configuration: str,
    payload: dict[str, Any],
    inputs: dict[str, Any],
    trial: int,
    history: list[dict[str, Any]],
    outputs: list[dict[str, str]],
    system: str | None,
) -> RequestV2:
    stage = (
        "specialist"
        if system
        else "synthesis"
        if configuration in ("C4a", "C4b")
        else "answer"
    )
    instructions = "只根据本次可见信息选择一个选项，返回 A/B/C/D，不编造计算。"
    if system:
        instructions = (
            "只用本体系证据，按结构、时间、问题、反证四步给出JSON claims/gaps，"
            "不给其他体系辩护。"
        )
        if configuration == "C4a":
            instructions += "时间交互必须按程序给定顺序处理，不自行重排。"
    if configuration != "C0":
        instructions += (
            "年度采样日不是事件日；事件月日未知时，只使用原局与流年，不推测流月流日。"
        )
    return RequestV2(
        configuration,
        stage,
        system,
        trial,
        deepcopy(payload),
        record.birth.public_input(),
        deepcopy(inputs["chart_bundle"]),
        inputs["chart_text"],
        deepcopy(inputs["skills"]),
        deepcopy(inputs["rule_hits"]),
        configuration == "C4a" if system else None,
        tuple(deepcopy(history)) if not system else (),
        tuple(deepcopy(outputs)),
        instructions,
    )


def _answer(
    record: Question,
    configuration: str,
    payload: dict[str, Any],
    bundle: dict[str, Any],
    inputs: dict[str, Any],
    trial: int,
    history: list[dict[str, Any]],
    answerer: Callable[[RequestV2], str],
) -> tuple[str, int]:
    outputs, calls = [], 0
    if configuration in ("C4a", "C4b"):
        for system in systems(bundle):
            request = _request(
                record,
                configuration,
                payload,
                specialist_context(inputs, system),
                trial,
                [],
                [],
                system,
            )
            outputs.append({"system": system, "output": answerer(request)})
            calls += 1
    return answerer(
        _request(record, configuration, payload, inputs, trial, history, outputs, None)
    ), calls + 1


def _trial_rows(
    records: list[Question],
    configuration: str,
    chart_provider: Callable[[BirthMetadata], dict[str, Any]],
    skill_provider: Callable[[str], dict[str, Any]],
    answerer: Callable[[RequestV2], str],
    rule_provider: Callable[[dict[str, Any]], list[dict[str, Any]]],
    seed: int,
    trial: int,
    year_reviews: dict[str, YearReview],
) -> tuple[list[dict[str, Any]], int]:
    histories: dict[str, list[dict[str, Any]]] = {}
    results, calls = [], 0
    for record in records:
        payload, mapping = shuffle_options(record, seed, trial)
        decision = question_year(record, year_reviews.get(record.scoring_fingerprint()))
        payload |= {
            "target_year": decision.year,
            "year_basis": "question_explicit_target_year",
        }
        bundle = (
            _question_chart(
                chart_provider, record, year_reviews.get(record.scoring_fingerprint())
            )
            if configuration != "C0"
            else {}
        )
        inputs = context(configuration, bundle, skill_provider, rule_provider)
        history = (
            histories.setdefault(record.case_id, [])
            if record.source == "BaziQA"
            else []
        )
        response, count = _answer(
            record, configuration, payload, bundle, inputs, trial, history, answerer
        )
        selected = parse_selection(response)
        canonical = mapping.get(selected) if selected is not None else None
        calls += count
        results.append(
            {
                "question_fingerprint": record.scoring_fingerprint(),
                "case_fingerprint": fingerprint([record.source, record.case_id]),
                "correct": canonical == record.answer,
                "invalid": canonical is None,
                "canonical_selection": canonical,
                "displayed_selection": selected,
                "option_mapping": mapping,
                "chart_fingerprint": fingerprint(bundle) if bundle else None,
                "birth_fingerprint": fingerprint(record.birth.public_input()),
            }
        )
        if record.source == "BaziQA":
            history.extend(
                (
                    {"role": "user", "question": deepcopy(payload)},
                    {"role": "assistant", "content": response},
                )
            )
    return results, calls


def _outcomes(trials: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    outcomes = []
    for index, first in enumerate(trials[0]):
        attempts = [rows[index] for rows in trials]
        outcomes.append(
            {key: first[key] for key in ("question_fingerprint", "case_fingerprint")}
            | {
                "correct": sum(row["correct"] for row in attempts)
                >= (3 if len(trials) == 5 else 1),
                "invalid_trials": sum(row["invalid"] for row in attempts),
                "trials": attempts,
            }
        )
    return outcomes


def _excluded_configuration(
    configuration: str, control: str, eligibility: dict[str, Any]
) -> dict[str, Any]:
    return {
        "contract": "e2-protocol-v2",
        "configuration": configuration,
        "control": control,
        "status": "all_questions_excluded",
        "question_eligibility": eligibility,
        "chart_year_binding": "no_chart_all_excluded",
        "protocol_stage_calls": 0,
        "model_requests": 0,
        "outcomes": [],
        "summary": None,
        "actual_v4_runtime": False,
    }


def run_configuration_v2(
    records: list[Question],
    configuration: str,
    chart_provider: Callable[[BirthMetadata], dict[str, Any]],
    skill_provider: Callable[[str], dict[str, Any]],
    answerer: Callable[[RequestV2], str],
    *,
    seed: int,
    control: str = "original",
    repeats: int = 1,
    rule_provider: Callable[[dict[str, Any]], list[dict[str, Any]]] = hit_list,
    year_reviews: dict[str, YearReview] | None = None,
) -> dict[str, Any]:
    if (
        configuration not in CONFIGURATIONS_V2
        or type(repeats) is not int
        or repeats not in (1, 5)
        or not records
    ):
        raise ValueError("invalid_e2_configuration_repeats_or_empty_records")
    if len({(row.source, row.id) for row in records}) != len(records):
        raise ValueError("duplicate_e2_question_identity")
    records, eligibility = select_questions(records, reviews=year_reviews)
    if not records:
        return _excluded_configuration(configuration, control, eligibility)
    trials, calls = [], 0
    for trial in range(repeats):
        rows, count = _trial_rows(
            records,
            configuration,
            chart_provider,
            skill_provider,
            answerer,
            rule_provider,
            seed,
            trial,
            year_reviews or {},
        )
        trials.append(rows)
        calls += count
    outcomes = _outcomes(trials)
    return {
        "contract": "e2-protocol-v2",
        "configuration": configuration,
        "control": control,
        "repeats": repeats,
        "scoring": "at_least_3_correct_trials"
        if repeats == 5
        else "single_trial_exact_match",
        "option_shuffle_seed": seed,
        "protocol_stage_calls": calls,
        "actual_v4_runtime": False,
        "model_requests": "unmeasured_use_authorized_transport_ledger",
        "question_eligibility": eligibility,
        "chart_year_binding": _chart_binding(chart_provider, configuration),
        "outcomes": outcomes,
        "summary": accuracy_summary(outcomes),
    }
