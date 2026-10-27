"""Independent public-tool edge review: malformed inputs and actual bounded pages."""

from __future__ import annotations

import json
import os
import subprocess
from copy import deepcopy
from datetime import date
from importlib.resources import files
from pathlib import Path

import pytest

from mingjing_core.adapters.charts import daily_transit as daily_module
from mingjing_core.adapters.charts import daily_transit_natal as natal_module
from mingjing_core.adapters.charts.almanac import almanac
from mingjing_core.adapters.charts.benchmarks.handoff_build import BIRTH
from mingjing_core.adapters.charts.synastry import synastry
from mingjing_core.adapters.charts.window_search import window_search

ROOT = Path(__file__).resolve().parents[2]
DAY = "2026-10-21"
RANGE = {"start_date": DAY, "end_date": DAY}


def _natal(subject: str = "ayuan") -> dict:
    return {
        "owner_user_id": "synthetic-api-review-owner",
        "subject_id": "synthetic-" + subject,
        "operation_id": "synthetic-api-review-" + subject,
        "revision": 1,
        "birth": deepcopy(BIRTH),
    }


def _forbid_preparation(*args, **kwargs):
    raise AssertionError("invalid input reached birth calculation")


@pytest.mark.parametrize("api", ["daily", "window"])
@pytest.mark.parametrize("shape", ["missing", "null", "bool", "compact"])
def test_public_birth_date_shapes_fail_before_basis_calculation(
    api: str, shape: str, monkeypatch
) -> None:
    natal = _natal()
    if shape == "missing":
        natal["birth"].pop("date")
    else:
        natal["birth"]["date"] = {"null": None, "bool": True, "compact": "19940312"}[
            shape
        ]
    monkeypatch.setattr(natal_module, "_basis", _forbid_preparation)
    with pytest.raises(ValueError, match="^daily_transit_natal_invalid$"):
        if api == "daily":
            daily_module.daily_transit(natal, DAY)
        else:
            window_search(natal, RANGE, "面试")


@pytest.mark.parametrize(
    "mutation", ["revision_bool", "subject_null", "missing_date", "compact", "owner"]
)
def test_invalid_second_person_is_rejected_before_preparing_either_person(
    mutation: str, monkeypatch
) -> None:
    left, right = _natal(), _natal("xiaohe")
    if mutation == "revision_bool":
        right["revision"] = True
    elif mutation == "subject_null":
        right["subject_id"] = None
    elif mutation == "missing_date":
        right["birth"].pop("date")
    elif mutation == "compact":
        right["birth"]["date"] = "19940312"
    else:
        right["birth"]["owner_user_id"] = "synthetic-foreign-owner"
    monkeypatch.setattr(natal_module, "prepare_natal", _forbid_preparation)
    with pytest.raises(ValueError, match="^daily_transit_natal_invalid$"):
        synastry(left, right, "friendship", consent="user_confirmed", as_of_date=DAY)


@pytest.mark.parametrize("api", ["daily", "synastry"])
@pytest.mark.parametrize("sign", [1, -1])
def test_oversized_json_integer_orb_raises_valueerror_without_preparation(
    api: str, sign: int, monkeypatch
) -> None:
    monkeypatch.setattr(daily_module, "prepare_natal", _forbid_preparation)
    monkeypatch.setattr(natal_module, "prepare_natal", _forbid_preparation)
    orb = sign * 10**400
    with pytest.raises(ValueError, match="^西占计算参数须为有限数值$"):
        if api == "daily":
            daily_module.daily_transit(_natal(), DAY, orb_degrees=orb)
        else:
            synastry(
                _natal(),
                _natal("xiaohe"),
                "romantic",
                consent="user_confirmed",
                as_of_date=DAY,
                orb_degrees=orb,
            )


@pytest.mark.parametrize("api", ["daily", "window"])
@pytest.mark.parametrize("coordinate", ["lat", "lon"])
@pytest.mark.parametrize("value", [True, 10**400], ids=["bool", "oversized-integer"])
def test_coordinate_types_fail_before_basis_calculation(
    api: str, coordinate: str, value, monkeypatch
) -> None:
    natal = _natal()
    natal["birth"]["place"][coordinate] = value
    monkeypatch.setattr(natal_module, "_basis", _forbid_preparation)
    with pytest.raises(ValueError, match="^daily_transit_natal_invalid$"):
        if api == "daily":
            daily_module.daily_transit(natal, DAY)
        else:
            window_search(natal, RANGE, "面试")


@pytest.mark.parametrize("api", ["daily", "window"])
@pytest.mark.parametrize("value", [["clock"], {"value": "clock"}])
def test_clock_basis_container_is_not_coerced_or_sent_for_calculation(
    api: str, value, monkeypatch
) -> None:
    natal = _natal()
    natal["birth"]["clock_basis"] = value
    monkeypatch.setattr(natal_module, "_basis", _forbid_preparation)
    with pytest.raises(ValueError, match="^daily_transit_natal_invalid$"):
        if api == "daily":
            daily_module.daily_transit(natal, DAY)
        else:
            window_search(natal, RANGE, "面试")


@pytest.mark.parametrize("consent", [["user_confirmed"], {"value": "user_confirmed"}])
def test_consent_is_not_unwrapped_from_a_container(consent, monkeypatch) -> None:
    monkeypatch.setattr(natal_module, "prepare_natal", _forbid_preparation)
    with pytest.raises(ValueError, match="^CONSENT_REQUIRED"):
        synastry(None, None, [], consent=consent, as_of_date="not-a-date")


@pytest.mark.parametrize("day", [date(2026, 10, 21), {"date": DAY, "sect": 2}])
def test_public_almanac_does_not_infer_or_coerce_a_date_object(day) -> None:
    with pytest.raises(ValueError, match="^almanac_date_invalid"):
        almanac(day)


def test_public_window_rejects_a_range_extension_before_birth_calculation(
    monkeypatch,
) -> None:
    monkeypatch.setattr(natal_module, "prepare_natal", _forbid_preparation)
    dates = {**RANGE, "sample_time": "23:00"}
    with pytest.raises(ValueError, match="^window_range_invalid$"):
        window_search(_natal(), dates, "出行")


NATIVE_SCRIPT = r"""
import json, os, platform, time
from copy import deepcopy
from pathlib import Path
from mingjing_core.adapters.charts.almanac import almanac
from mingjing_core.adapters.charts.daily_transit import daily_transit
from mingjing_core.adapters.charts.synastry import synastry
from mingjing_core.adapters.charts.window_search import window_search
from mingjing_core.adapters.charts.tool_evidence import content_hash, pointer
from mingjing_core.adapters.charts.benchmarks.handoff_offline import offline_runtime

def verify(result):
    core = {key:result[key] for key in ('version','scope','data','rule_hits','sources')}
    assert result['document_id'] == 'tool-' + content_hash(core)
    for rows in result['aliases'].values():
        for row in rows:
            assert row['value_sha256'] == content_hash(pointer(result,row['path']))
    assert all(hit['met'] is True for hit in result['rule_hits'])
    assert result['effects']['model_calls'] == result['effects']['writes'] == 0

platform.system()
sample = Path('docs/v4/contracts/samples/synastry-ayuan-xiaohe-input.json')
request = json.loads(sample.read_text('utf8'))
left,right = request['chart_a'],request['chart_b']
before = deepcopy(request)
zones = ('UTC','Asia/Tokyo','America/New_York')
variants = []
with offline_runtime():
    for zone in zones:
        os.environ['TZ'] = zone
        if hasattr(time,'tzset'): time.tzset()
        results = [daily_transit(left,'2026-10-21'),almanac('2026-10-21'),
                   window_search(left,dict(start_date='2026-10-21',end_date='2026-10-21'),'面试'),
                   synastry(**request)]
        for result in results: verify(result)
        assert results[0]['data']['snapshot_at'] == '2026-10-21T12:00:00+08:00'
        assert results[0]['data']['snapshot_at_utc'] == '2026-10-21T04:00:00Z'
        variants.append([result['document_id'] for result in results])
    assert variants[0] == variants[1] == variants[2]
    period = dict(start_date='2028-02-01',end_date='2028-03-03')
    pages = [window_search(left,period,'面试',offset=offset,limit=31)
             for offset in (0,31,32)]
    for result in pages: verify(result)
    first,last,empty = [result['data'] for result in pages]
    assert [row['pagination']['returned'] for row in (first,last,empty)] == [31,1,0]
    states = [row['pagination'] for row in (first,last,empty)]
    assert [row['has_more'] for row in states] == [True,False,False]
    assert [row['next_offset'] for row in states] == [31,None,None]
    summary = first['ranking_summary']
    assert len(summary) == 32 and '2028-02-29' in {row['date'] for row in summary}
    assert summary == last['ranking_summary'] == empty['ranking_summary']
    combined = first['candidates'] + last['candidates']
    assert [(row['date'],row['rank'],row['score']) for row in combined] == [
        (row['date'],row['rank'],row['score']) for row in summary]
    assert [row['rank'] for row in combined] == list(range(1,33))
    for row in summary: assert row['score'] == row['positive_sum'] + row['negative_sum']
    assert empty['candidates'] == empty['observations'] == pages[2]['rule_hits'] == []
    assert pages[2]['aliases'] == dict(c=[],r=[])
    assert len({row['data']['trace']['query_sha256'] for row in pages}) == 1
    sizes = [len(json.dumps(row,ensure_ascii=False).encode('utf8')) for row in pages]
    assert max(sizes) < 8_000_000
assert request == before
print(json.dumps(dict(zones=list(zones),tzset_available=hasattr(time,'tzset'),
                     tools=4,date_count=32,returned=[31,1,0],page_bytes=sizes,
                     sources_unchanged=True,external_requests=0)))
"""


@pytest.fixture(scope="module")
def native_review() -> dict:
    python = os.environ.get("CHART_PYTHON")
    if not python or not Path(python).is_file():
        pytest.skip("requires explicitly configured CHART_PYTHON")
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
    return json.loads(process.stdout)


def test_actual_public_tools_preserve_explicit_dates_across_tz_environment(
    native_review: dict,
) -> None:
    assert native_review["tools"] == 4 and len(native_review["zones"]) == 3
    assert native_review["external_requests"] == 0


def test_actual_leap_range_last_and_empty_pages_remain_complete(
    native_review: dict,
) -> None:
    assert native_review["date_count"] == 32
    assert native_review["returned"] == [31, 1, 0]
    assert max(native_review["page_bytes"]) < 8_000_000
    assert native_review["sources_unchanged"] is True
