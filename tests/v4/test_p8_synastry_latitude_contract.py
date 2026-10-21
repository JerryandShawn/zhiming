"""Optional geographic latitude must agree with the native geocentric contract."""

from __future__ import annotations

import json
import os
import subprocess
from copy import deepcopy
from importlib.resources import files
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from mingjing_core.adapters.charts import daily_transit_natal as natal_module
from mingjing_core.adapters.charts.synastry import synastry
from mingjing_core.adapters.charts.tool_evidence import content_hash, pointer
from mingjing_core.domain.json_values import ensure_finite_json

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "docs/v4/contracts"
INPUT = CONTRACTS / "samples/synastry-ayuan-xiaohe-input.json"
SCHEMA = json.loads((CONTRACTS / "synastry.schema.json").read_text("utf8"))
REQUEST_SCHEMA = {"$ref": "#/$defs/Request", "$defs": SCHEMA["$defs"]}
REQUEST_VALIDATOR = Draft202012Validator(REQUEST_SCHEMA, format_checker=FormatChecker())


@pytest.fixture(autouse=True)
def pinned_timezone_source(monkeypatch) -> None:
    monkeypatch.setenv("PYTHONTZPATH", str(files("tzdata.zoneinfo")))


def request() -> dict:
    return json.loads(INPUT.read_text("utf8"))


def validate_request_and_native_preflight(value: dict) -> None:
    ensure_finite_json(value)
    REQUEST_VALIDATOR.validate(value)
    for side in ("chart_a", "chart_b"):
        validated = natal_module.validate_natal(value[side], value["as_of_date"])
        assert validated["birth"] == value[side]["birth"]
        assert validated["as_of_date"] == value["as_of_date"]


@pytest.mark.parametrize("sides", [("chart_a",), ("chart_b",), ("chart_a", "chart_b")])
def test_latitude_is_optional_for_each_side_without_other_input_changes(
    sides: tuple[str, ...],
) -> None:
    value = request()
    validate_request_and_native_preflight(value)
    for side in sides:
        del value[side]["birth"]["place"]["lat"]
    before = deepcopy(value)
    validate_request_and_native_preflight(value)
    assert value == before


def forbid_preparation(*args, **kwargs):
    raise AssertionError("invalid latitude reached natal preparation")


@pytest.mark.parametrize("side", ["chart_a", "chart_b"])
@pytest.mark.parametrize(
    "latitude",
    [None, True, False, "30.67", [], {}, -90.0001, 90.0001, 10**400],
    ids=["null", "true", "false", "string", "list", "object", "low", "high", "huge"],
)
def test_provided_invalid_latitude_is_the_schema_and_native_rejection_cause(
    side: str, latitude, monkeypatch
) -> None:
    value = request()
    validate_request_and_native_preflight(value)
    value[side]["birth"]["place"]["lat"] = latitude
    errors = list(REQUEST_VALIDATOR.iter_errors(value))
    assert errors
    assert all(
        tuple(error.absolute_path) == (side, "birth", "place", "lat")
        for error in errors
    )
    monkeypatch.setattr(natal_module, "prepare_natal", forbid_preparation)
    with pytest.raises(ValueError, match="^daily_transit_natal_invalid$"):
        synastry(**value)


@pytest.mark.parametrize("side", ["chart_a", "chart_b"])
@pytest.mark.parametrize(
    "latitude", [float("nan"), float("inf"), -float("inf")], ids=["nan", "inf", "-inf"]
)
def test_nonfinite_latitude_is_rejected_at_finite_json_and_native_boundaries(
    side: str, latitude: float, monkeypatch
) -> None:
    value = request()
    validate_request_and_native_preflight(value)
    value[side]["birth"]["place"]["lat"] = latitude
    # JSON Schema comparisons alone do not promise to reject Python's NaN.
    with pytest.raises(ValueError) as error:
        ensure_finite_json(value)
    assert str(error.value) == f"non-finite number at $/{side}/birth/place/lat"
    monkeypatch.setattr(natal_module, "prepare_natal", forbid_preparation)
    with pytest.raises(ValueError, match="^daily_transit_natal_invalid$"):
        synastry(**value)


@pytest.mark.parametrize("latitude", [-90, 0, 90])
def test_provided_latitude_keeps_inclusive_numeric_range(latitude: int) -> None:
    value = request()
    for side in ("chart_a", "chart_b"):
        value[side]["birth"]["place"]["lat"] = latitude
    validate_request_and_native_preflight(value)


NATIVE_SCRIPT = r"""
import json, platform
from copy import deepcopy
from pathlib import Path
from mingjing_core.adapters.charts.synastry import synastry
from mingjing_core.adapters.charts.benchmarks.handoff_offline import offline_runtime

platform.system()
value = json.loads(Path('docs/v4/contracts/samples/synastry-ayuan-xiaohe-input.json').read_text('utf8'))
before = deepcopy(value)
without = deepcopy(value)
for side in ('chart_a', 'chart_b'):
    del without[side]['birth']['place']['lat']
without_before = deepcopy(without)
with offline_runtime():
    baseline = synastry(**value)
    no_latitude = synastry(**without)
assert value == before and without == without_before
print(json.dumps(dict(baseline=baseline, no_latitude=no_latitude), ensure_ascii=False, allow_nan=False))
"""


def assert_result_evidence(result: dict) -> None:
    Draft202012Validator(SCHEMA, format_checker=FormatChecker()).validate(result)
    fields = ("version", "scope", "data", "rule_hits", "sources")
    assert result["document_id"] == "tool-" + content_hash(
        {key: result[key] for key in fields}
    )
    for rows in result["aliases"].values():
        for row in rows:
            assert row["value_sha256"] == content_hash(pointer(result, row["path"]))
            assert row["claim_id"] == "claim-" + content_hash(
                [result["document_id"], row["path"], row["value_sha256"]]
            )
    for row in result["aliases"]["r"]:
        assert pointer(result, row["path"])["met"] is True
    assert result["effects"]["model_calls"] == result["effects"]["writes"] == 0


def test_actual_three_system_results_are_unchanged_when_both_latitudes_are_absent() -> (
    None
):
    python = os.environ.get("CHART_PYTHON")
    assert python and Path(python).is_file(), (
        "requires explicitly configured CHART_PYTHON"
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if "API_KEY" not in key.upper()
        and not key.upper().startswith(("LANGCHAIN", "LANGSMITH"))
    }
    env.update(PYTHONUTF8="1", LANGSMITH_TRACING="false", LANGCHAIN_TRACING_V2="false")
    env["PYTHONTZPATH"] = str(files("tzdata.zoneinfo"))
    process = subprocess.run(
        [python, "-X", "utf8", "-c", NATIVE_SCRIPT],
        cwd=ROOT,
        env=env,
        capture_output=True,
        encoding="utf8",
        timeout=90,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    results = json.loads(process.stdout)
    assert results["baseline"] == results["no_latitude"]
    for result in results.values():
        assert_result_evidence(result)
        data = result["data"]
        assert data["bazi"]["pillars_a"] and data["bazi"]["pillars_b"]
        assert len(data["ziwei"]["cross_views"]) == 2
        assert (
            len(data["astro"]["positions_a"]) == len(data["astro"]["positions_b"]) == 10
        )
