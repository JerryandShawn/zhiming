"""M2 two-key transport fence never redefines the historical C0 request."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from mingjing_core.adapters.charts.benchmarks.night28_controls import no_chart_input
from mingjing_core.adapters.charts.benchmarks.records import BirthMetadata, Question

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "docs/v4/contracts/e2_m2_no_chart_input.schema.json"


def _payload() -> dict:
    row = Question(
        id="synthetic-scoring-only-id",
        case_id="synthetic-scoring-only-case",
        text="合成问题：2025年会发生哪个练习事件？",
        options=tuple((key, "合成选项" + key) for key in "ABCD"),
        answer="B",
        birth=BirthMetadata(1994, 3, 12, 8, 20, "男", "合成地点", "solar"),
        source="synthetic",
        competition_year=2025,
    )
    return no_chart_input(row)


def _validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_bytes())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def test_real_no_chart_constructor_satisfies_strict_model_input_contract():
    payload = _payload()
    before = deepcopy(payload)
    _validator().validate(payload)
    assert payload == before
    assert set(payload) == {"question", "options"}
    assert sorted(payload["options"].values()) == ["合成选项" + key for key in "ABCD"]
    assert "synthetic-scoring-only" not in json.dumps(payload)


@pytest.mark.parametrize(
    "key",
    [
        "birth",
        "question_id",
        "case_id",
        "answer",
        "gold",
        "chart_bundle",
        "chart_text",
        "history",
        "target_year",
        "seed",
        "configuration",
        "aliases",
        "scoring_fingerprint",
    ],
)
def test_scoring_and_chart_metadata_cannot_enter_model_object(key: str):
    payload = _payload()
    payload[key] = "synthetic-private-metadata"
    assert list(_validator().iter_errors(payload))


@pytest.mark.parametrize("field", ["question", "A", "B", "C", "D"])
@pytest.mark.parametrize("bad", [None, True, 2025, {}, [], "", " \n\t"])
def test_question_and_each_option_require_nonblank_text(field: str, bad: object):
    payload = _payload()
    target = payload if field == "question" else payload["options"]
    target[field] = bad
    assert list(_validator().iter_errors(payload))


@pytest.mark.parametrize("key", list("ABCD"))
def test_every_display_label_is_required(key: str):
    payload = _payload()
    payload["options"].pop(key)
    assert list(_validator().iter_errors(payload))


@pytest.mark.parametrize("key", ["E", "a", "answer", "birth", "mapping"])
def test_options_cannot_hide_metadata_or_extra_labels(key: str):
    payload = _payload()
    payload["options"][key] = "合成额外字段"
    assert list(_validator().iter_errors(payload))


def test_schema_does_not_claim_to_detect_semantic_hints_in_source_text():
    payload = _payload()
    payload["question"] = "合成反例：题面自己写着出生资料或答案暗示，结构校验无法判断。"
    _validator().validate(payload)
    assert "题面自己" in payload["question"]
