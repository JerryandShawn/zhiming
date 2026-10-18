"""Historical deprecated E2 v1 plans; current entry is protocol_v2/scripted_v2."""

from __future__ import annotations

import json
import random
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Any, Literal

from .records import BirthMetadata, Question, fingerprint

Configuration = Literal["direct", "single", "deep"]
CONFIGURATIONS: tuple[Configuration, ...] = ("direct", "single", "deep")
ChartProvider = Callable[[BirthMetadata], dict[str, Any]]


@dataclass(frozen=True)
class InferenceRequest:
    configuration: Configuration
    stage: Literal["answer", "specialist", "synthesis"]
    question: dict[str, Any]
    birth: dict[str, Any]
    chart: dict[str, Any]
    instructions: str
    specialist_output: str | None = None


def placebo_births(records: list[Question], seed: int) -> list[Question]:
    cases: dict[str, BirthMetadata] = {}
    for row in records:
        if row.case_id in cases and cases[row.case_id] != row.birth:
            raise ValueError("placebo_case_has_inconsistent_birth_records")
        cases[row.case_id] = row.birth
    pool = list(dict.fromkeys(row.birth for row in records))
    if len(pool) < 2:
        raise ValueError("placebo_requires_at_least_two_distinct_birth_records")
    random.Random(seed).shuffle(pool)
    donors = {birth: pool[(index + 1) % len(pool)] for index, birth in enumerate(pool)}
    # A case keeps one donor birth across all its questions; the answer key never moves.
    return [replace(row, birth=donors[row.birth]) for row in records]


def parse_selection(text: str) -> str | None:
    selected = text.strip()
    if selected in tuple("ABCD"):
        return selected
    try:
        value = json.loads(selected)
    except (json.JSONDecodeError, TypeError):
        return None
    if (
        isinstance(value, dict)
        and set(value) == {"answer"}
        and value["answer"] in tuple("ABCD")
    ):
        return value["answer"]
    return None


def _request(
    record: Question,
    configuration: Configuration,
    chart: dict[str, Any],
    specialist: str | None = None,
) -> InferenceRequest:
    stage: Literal["answer", "specialist", "synthesis"] = "answer"
    instructions = "根据给定命盘和题目选择一个选项，只返回 A/B/C/D；不得自行重排盘。"
    if configuration == "single":
        instructions += "核对所需字段、时间层级和口径，再选择；缺失依据不可编造。"
    elif configuration == "deep":
        stage = "specialist" if specialist is None else "synthesis"
        instructions = (
            "只根据给定程序盘面提供与选项有关的专科证据和冲突，不补写缺失数据。"
            if specialist is None
            else "综合专科证据并核对原盘，只返回 A/B/C/D。"
        )
    return InferenceRequest(
        configuration,
        stage,
        record.public_input(),
        record.birth.public_input(),
        deepcopy(chart),
        instructions,
        specialist,
    )


def run_configuration(
    records: list[Question],
    configuration: Configuration,
    chart_provider: ChartProvider,
    answerer: Callable[[InferenceRequest], str],
    *,
    control: str,
    execution_kind: str,
) -> dict[str, Any]:
    if configuration not in CONFIGURATIONS:
        raise ValueError("unknown_configuration")
    outcomes: list[dict[str, Any]] = []
    stages = 0
    for record in records:
        chart = chart_provider(record.birth)
        specialist: str | None = None
        if configuration == "deep":
            specialist = answerer(_request(record, configuration, chart))
            stages += 1
        response = answerer(_request(record, configuration, chart, specialist))
        stages += 1
        selection = parse_selection(response)
        outcomes.append(
            {
                "question_fingerprint": fingerprint([record.source, record.id]),
                "birth_fingerprint": fingerprint(record.birth.public_input()),
                "chart_fingerprint": fingerprint(chart),
                "selected": selection,
                "correct": selection == record.answer,
                "invalid": selection is None,
            }
        )
    return {
        "configuration": configuration,
        "control": control,
        "execution_kind": execution_kind,
        "questions": len(records),
        "correct": sum(item["correct"] for item in outcomes),
        "invalid": sum(item["invalid"] for item in outcomes),
        "protocol_stage_calls": stages,
        "actual_v4_agent_runtime": False,
        "outcomes": outcomes,
    }
