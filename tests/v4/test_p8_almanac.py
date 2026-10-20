"""Native library agreement and civil-date invariants for the almanac contract."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import date, timedelta
from pathlib import Path

import jsonschema
import pytest

from mingjing_core.adapters.charts.almanac import almanac_date
from mingjing_core.adapters.charts.tool_evidence import content_hash, pointer

ROOT = Path(__file__).resolve().parents[2]
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
SCRIPT = """
import json,os,sys,time
from lunar_python import Solar
from mingjing_core.adapters.charts.almanac import almanac
results=[]
for value in json.load(sys.stdin):
    year,month,day=map(int,value.split('-'))
    lunar=Solar.fromYmdHms(year,month,day,12,0,0).getLunar()
    expected={
      'yi':lunar.getDayYi(1),'ji':lunar.getDayJi(1),
      'chong':lunar.getDayChong(),'sha':lunar.getDaySha(),
      'deity':lunar.getDayTianShen(),'officer':lunar.getZhiXing(),
      'xiu':lunar.getXiu(),'pengzu':[lunar.getPengZuGan(),lunar.getPengZuZhi()],
      'day':lunar.getDayInGanZhi(),
    }
    results.append({'result':almanac(value),'expected':expected})
variants=[]
for zone in ('UTC','Asia/Shanghai','Asia/Tokyo','America/New_York'):
    os.environ['TZ']=zone
    if hasattr(time,'tzset'): time.tzset()
    variants.append(almanac('2026-10-21'))
print(json.dumps({'rows':results,'timezone_variants':variants},ensure_ascii=False))
"""


@pytest.fixture(scope="module")
def native() -> dict:
    python = os.environ.get("CHART_PYTHON")
    if not python or not Path(python).is_file():
        pytest.skip("需要显式CHART_PYTHON原生历法解释器")
    fixed = [
        "1901-01-01",
        "2099-12-31",
        "1986-05-04",
        "1986-09-14",
        "1988-04-17",
        "1991-04-14",
        "1991-09-15",
        "2000-02-29",
        "2023-03-22",
        "2025-07-25",
        "2026-02-04",
        "2026-10-17",
        "2026-10-21",
        "2026-12-07",
    ]
    days = sorted(
        set(
            fixed
            + [
                (date(2026, 1, 1) + timedelta(days=index * 7)).isoformat()
                for index in range(104)
            ]
        )
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.endswith("API_KEY") and "LANGSMITH" not in key
    }
    env.update(PYTHONUTF8="1", LANGCHAIN_TRACING_V2="false", LANGSMITH_TRACING="false")
    result = subprocess.run(
        [python, "-c", SCRIPT],
        input=json.dumps(days),
        text=True,
        capture_output=True,
        encoding="utf8",
        env=env,
        cwd=ROOT,
        timeout=90,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        20261021,
        "",
        "2026-1-21",
        "20261021",
        "2026-02-29",
        "2026-10-21T00:00:00+08:00",
        "2026-10-21 ",
        "２０２６-10-21",
        "2026-00-01",
        "2026-13-01",
        "2026-10-00",
        "2026-10-32",
    ],
)
def test_invalid_date_fails_before_importing_a_chart_library(value) -> None:
    with pytest.raises(ValueError, match="almanac_date_invalid"):
        almanac_date(value)


@pytest.mark.parametrize("value", ["1900-12-31", "2100-01-01", "0001-01-01"])
def test_range_is_explicit(value: str) -> None:
    with pytest.raises(ValueError, match="almanac_date_out_of_range"):
        almanac_date(value)


def test_leap_date_validation_uses_gregorian_calendar() -> None:
    assert almanac_date("2000-02-29") == date(2000, 2, 29)
    assert almanac_date("2026-10-21") == date(2026, 10, 21)


def test_each_traditional_field_agrees_with_the_native_library(native: dict) -> None:
    for row in native["rows"]:
        data, expected = row["result"]["data"], row["expected"]
        assert data["yi"] == expected["yi"] and data["ji"] == expected["ji"]
        assert data["chong_sha"]["branch"] == expected["chong"]
        assert data["chong_sha"]["sha_direction"] == expected["sha"]
        assert data["duty"]["deity"] == expected["deity"]
        assert data["duty"]["officer"] == expected["officer"]
        assert data["mansion"]["name"] == expected["xiu"]
        assert list(data["pengzu"].values()) == expected["pengzu"]
        assert data["ganzhi"]["day"] == expected["day"]


def test_opposition_and_sha_are_independent_day_branch_invariants(native: dict) -> None:
    sha = dict(zip("子丑寅卯辰巳午未申酉戌亥", "南东北西南东北西南东北西", strict=True))
    for row in native["rows"]:
        data = row["result"]["data"]
        day_branch = data["ganzhi"]["day"][1]
        assert (
            data["chong_sha"]["branch"]
            == BRANCHES[(BRANCHES.index(day_branch) + 6) % 12]
        )
        assert data["chong_sha"]["sha_direction"] == sha[day_branch]


def test_host_timezone_does_not_change_the_civil_date_result(native: dict) -> None:
    values = native["timezone_variants"]
    assert values and all(value == values[0] for value in values)
    assert values[0]["data"]["sample_at"] == "2026-10-21T12:00:00+08:00"
    assert values[0]["data"]["method"]["solar_time_applied"] is False


def test_evidence_aliases_bind_actual_values_and_true_rules(native: dict) -> None:
    for row in native["rows"]:
        result = row["result"]
        names = {alias["alias"] for alias in result["aliases"]["c"]}
        for kind in ("c", "r"):
            for alias in result["aliases"][kind]:
                assert alias["value_sha256"] == content_hash(
                    pointer(result, alias["path"])
                )
                if kind == "r":
                    assert set(alias["evidence_aliases"]) <= names
        assert all(hit["met"] is True and hit["source"] for hit in result["rule_hits"])
        assert result["effects"]["model_calls"] == result["effects"]["writes"] == 0


def test_library_fingerprint_has_no_private_paths_and_matches_its_map(
    native: dict,
) -> None:
    method = native["rows"][0]["result"]["data"]["method"]
    files = method["source_files_sha256"]
    assert "Lunar.py" in files and "util/LunarUtil.py" in files
    assert all(not key.startswith(("/", "\\")) and ":" not in key for key in files)
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf8")
    assert hashlib.sha256(encoded).hexdigest() == method["library_source_sha256"]
    assert method["library_version"] == "1.4.8" and method["yi_ji_sect"] == 1


def test_schema_validates_all_native_results_and_rejects_unknown_fields(
    native: dict,
) -> None:
    schema = json.loads(
        (ROOT / "docs/v4/contracts/almanac.schema.json").read_text(encoding="utf8")
    )
    validator = jsonschema.Draft202012Validator(schema)
    for row in native["rows"]:
        validator.validate(row["result"])
    altered = dict(native["rows"][0]["result"], unexpected=True)
    assert list(validator.iter_errors(altered))
