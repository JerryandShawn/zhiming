"""Consent and ownership precede native calculation; actual cross-chart evidence."""

from __future__ import annotations

import json
import os
import subprocess
from copy import deepcopy
from importlib.resources import files
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from mingjing_core.adapters.charts.benchmarks.handoff_build import BIRTH
from mingjing_core.adapters.charts.p8_adapter import P8ChartAdapter
from mingjing_core.adapters.charts.synastry import _astro, synastry
from mingjing_core.adapters.charts.tool_evidence import content_hash, pointer

ROOT = Path(__file__).resolve().parents[2]


def natal(subject: str = "ayuan") -> dict:
    return {
        "owner_user_id": "synthetic-owner-ayuan",
        "subject_id": "synthetic-" + subject,
        "operation_id": "synthetic-compare-" + subject,
        "revision": 1,
        "birth": deepcopy(BIRTH),
    }


@pytest.mark.parametrize(
    "consent", [None, "", "yes", "true", True, False, "pending", 1]
)
def test_without_explicit_consent_even_malformed_births_are_not_read(consent) -> None:
    with pytest.raises(ValueError, match="CONSENT_REQUIRED"):
        synastry(None, None, "romantic", consent=consent, as_of_date="bad")


@pytest.mark.parametrize("mutation", ["foreign", "missing_owner", "kind", "list"])
def test_preflight_rejects_scope_and_unknown_kind_before_engine(mutation: str) -> None:
    a, b, kind = natal(), natal("xiaohe"), "romantic"
    if mutation == "foreign":
        b["owner_user_id"] = "foreign"
    elif mutation == "missing_owner":
        a.pop("owner_user_id")
    elif mutation == "kind":
        kind = "compatibility_percentage"
    else:
        b = []
    with pytest.raises(ValueError):
        synastry(a, b, kind, consent="user_confirmed", as_of_date="2026-10-21")


@pytest.mark.parametrize("orb", [0, 2, 6, 10])
def test_interchart_geometry_uses_declared_inclusive_orb(orb: float) -> None:
    a, b = {"太阳": {"longitude": 10.0}}, {"月亮": {"longitude": 70.0 + orb}}
    data, hits = _astro(a, b, orb)
    assert data["aspects"][0]["aspect"] == "六合"
    assert data["aspects"][0]["orb_degrees"] == orb
    assert hits[0]["evidence_paths"][-1] == "/data/astro/positions_b/月亮"
    assert _astro(a, {"月亮": {"longitude": 70.00001 + orb}}, orb)[0]["aspects"] == []


def test_adapter_does_not_launch_worker_when_consent_or_owner_is_wrong(
    monkeypatch,
) -> None:
    adapter = P8ChartAdapter("synthetic-owner-ayuan", python="synthetic-python")
    calls = []
    monkeypatch.setattr(adapter, "_request", lambda *args: calls.append(args))
    req = {
        "chart_a": natal(),
        "chart_b": natal("xiaohe"),
        "kind": "romantic",
        "as_of_date": "2026-10-21",
    }
    with pytest.raises(ValueError, match="CONSENT_REQUIRED"):
        adapter.synastry(req)
    req["consent"] = "user_confirmed"
    req["chart_b"]["owner_user_id"] = "foreign"
    with pytest.raises(ValueError, match="AUTH_SCOPE_ERROR"):
        adapter.synastry(req)
    assert calls == []


def test_adapter_routes_readonly_tools_with_explicit_owner_and_copy(
    monkeypatch,
) -> None:
    adapter = P8ChartAdapter("synthetic-owner-ayuan", python="synthetic-python")
    monkeypatch.setattr(
        adapter, "_request", lambda system, args: {"system": system, "args": args}
    )
    source = natal()
    old = deepcopy(source)
    assert adapter.daily_transit(source, "2026-10-21")["system"] == "daily_transit"
    dates = {"start_date": "2026-10-21", "end_date": "2026-10-27"}
    assert adapter.window_search(source, dates, "面试")["args"]["range"] == dates
    assert adapter.almanac("2026-10-21")["args"] == {"date": "2026-10-21"}
    assert source == old


@pytest.fixture(scope="module")
def actual() -> dict:
    python = os.environ.get("CHART_PYTHON")
    if not python:
        pytest.skip("requires explicit CHART_PYTHON")
    env = {
        key: value for key, value in os.environ.items() if "API_KEY" not in key.upper()
    }
    env.update(PYTHONUTF8="1", LANGSMITH_TRACING="false", LANGCHAIN_TRACING_V2="false")
    env["PYTHONTZPATH"] = str(files("tzdata.zoneinfo"))
    script = """
import json
from copy import deepcopy
from mingjing_core.adapters.charts.benchmarks.handoff_build import BIRTH
from mingjing_core.adapters.charts.synastry import synastry
a = dict(owner_user_id='synthetic-owner-ayuan',subject_id='synthetic-ayuan',revision=1,
         operation_id='synthetic-ayuan-synastry',birth=deepcopy(BIRTH))
b = dict(owner_user_id=a['owner_user_id'],subject_id='synthetic-xiaohe',revision=1,
         operation_id='synthetic-xiaohe-synastry',birth=dict(date='1995-08-27',reported_time='14:10',
         gender='女',place=dict(tz='Asia/Shanghai',lon=120.15,lat=30.28),clock_basis='clock',precision='reported'))
before = deepcopy([a,b])
result = synastry(a,b,'romantic',consent='user_confirmed',as_of_date='2026-10-21')
assert [a,b] == before
print(json.dumps(result,ensure_ascii=False))
"""
    process = subprocess.run(
        [python, "-X", "utf8", "-c", script],
        cwd=ROOT,
        env=env,
        capture_output=True,
        encoding="utf8",
        timeout=90,
    )
    assert process.returncode == 0, process.stderr
    return json.loads(process.stdout)


def test_actual_synthetic_pair_has_three_systems_without_affinity_score(
    actual: dict,
) -> None:
    data = actual["data"]
    assert data["consent"] == "user_confirmed"
    assert set(data) >= {"bazi", "astro", "ziwei", "time_basis"}
    assert data["ziwei"]["compatibility_score"] is None
    assert len(data["ziwei"]["cross_views"]) == 2
    assert data["astro"]["orb_degrees"] == 6.0
    assert data["astro"]["method"]["ephemeris"] == "Moshier"
    assert sum(data["bazi"]["visible_a"]["element_counts"].values()) == 8
    assert {row["method"] for row in data["bazi"]["useful_complement"]} == {
        "扶抑",
        "调候",
        "格局",
    }
    assert all(row["candidate_only"] for row in data["bazi"]["useful_complement"])


def test_actual_pair_aliases_resolve_to_true_sourced_values(actual: dict) -> None:
    assert actual["rule_hits"] and len(actual["rule_hits"]) == len(
        actual["aliases"]["r"]
    )
    for group in actual["aliases"].values():
        for alias in group:
            assert content_hash(pointer(actual, alias["path"])) == alias["value_sha256"]
    assert actual["effects"]["writes"] == actual["effects"]["model_calls"] == 0


def test_success_schema_and_explicit_consent_request_gate(actual: dict) -> None:
    schema = json.loads(
        (ROOT / "docs/v4/contracts/synastry.schema.json").read_text(encoding="utf8")
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    validator.validate(actual)
    request_schema = {"$ref": "#/$defs/Request", "$defs": schema["$defs"]}
    request = {
        "chart_a": natal(),
        "chart_b": natal("xiaohe"),
        "kind": "romantic",
        "as_of_date": "2026-10-21",
    }
    with pytest.raises(ValidationError):
        Draft202012Validator(request_schema).validate(request)
    request["consent"] = "user_confirmed"
    Draft202012Validator(request_schema).validate(request)
