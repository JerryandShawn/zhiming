"""Fail closed on unsupported almanac libraries, before calendar computation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from mingjing_core.adapters.charts import almanac as subject

ROOT = Path(__file__).resolve().parents[2]
DAY = "2026-10-21"
VERSION_ERROR = "almanac_library_version_unsupported"


@pytest.fixture(autouse=True)
def isolated_package_cache():
    subject._package_identity.cache_clear()
    try:
        yield
    finally:
        subject._package_identity.cache_clear()


def lunar_modules() -> set[str]:
    return {
        name
        for name in sys.modules
        if name == "lunar_python" or name.startswith("lunar_python.")
    }


@pytest.mark.parametrize("entrypoint", ["identity", "public"])
@pytest.mark.parametrize(
    "version",
    [
        "1.4.7",
        "1.4.9",
        "2.0.0",
        "1.4.8+local",
        "v1.4.8",
        "",
        None,
        True,
        148,
        "SYNTHETIC_PRIVATE_VERSION_MARKER\n1.4.9",
    ],
    ids=[
        "old",
        "new",
        "major",
        "local",
        "prefix",
        "empty",
        "null",
        "bool",
        "int",
        "private",
    ],
)
def test_unsupported_version_is_refused_without_importing_lunar(
    entrypoint: str, version
) -> None:
    before = lunar_modules()
    with patch.object(
        subject.importlib.metadata, "version", return_value=version
    ) as lookup:
        with pytest.raises(ValueError) as error:
            if entrypoint == "identity":
                subject._package_identity()
            else:
                subject.almanac(DAY)
        assert str(error.value) == VERSION_ERROR
        lookup.assert_called_once_with("lunar-python")
    assert lunar_modules() == before
    assert subject._package_identity.cache_info().currsize == 0


@pytest.mark.parametrize(
    ("day", "error_code"),
    [
        (None, "almanac_date_invalid"),
        (True, "almanac_date_invalid"),
        ("２０２６-10-21", "almanac_date_invalid"),
        ("2026-02-29", "almanac_date_invalid"),
        ("1900-12-31", "almanac_date_out_of_range"),
        ("2100-01-01", "almanac_date_out_of_range"),
    ],
)
def test_invalid_date_precedes_distribution_metadata(day, error_code: str) -> None:
    before = lunar_modules()
    with patch.object(
        subject.importlib.metadata,
        "version",
        side_effect=AssertionError("invalid date reached package lookup"),
    ) as lookup:
        with pytest.raises(ValueError, match="^" + error_code):
            subject.almanac(day)
        lookup.assert_not_called()
    assert lunar_modules() == before
    assert subject._package_identity.cache_info().currsize == 0


def test_rejected_metadata_is_not_cached_between_attempts() -> None:
    before = lunar_modules()
    with patch.object(
        subject.importlib.metadata,
        "version",
        side_effect=["SYNTHETIC_UNSUPPORTED_A", "SYNTHETIC_UNSUPPORTED_B"],
    ) as lookup:
        for _attempt in range(2):
            with pytest.raises(ValueError) as error:
                subject._package_identity()
            assert str(error.value) == VERSION_ERROR
            assert subject._package_identity.cache_info().currsize == 0
        assert lookup.call_count == 2
    assert subject._package_identity.cache_info().misses == 2
    assert lunar_modules() == before


NATIVE_SCRIPT = r"""
import json, platform
from pathlib import Path
from unittest.mock import patch
from lunar_python import Solar
from mingjing_core.adapters.charts import almanac as subject
from mingjing_core.adapters.charts.benchmarks.handoff_offline import offline_runtime
from mingjing_core.adapters.charts.tool_evidence import content_hash, pointer

platform.system()
sample_path = Path('docs/v4/contracts/samples/almanac-20261021.json')
sample = json.loads(sample_path.read_text('utf8'))
with offline_runtime():
    subject._package_identity.cache_clear()
    baseline = subject.almanac('2026-10-21')
    subject._package_identity.cache_clear()
    with (
        patch.object(subject.importlib.metadata, 'version',
                     return_value='SYNTHETIC_PRIVATE_UNAPPROVED_VERSION') as lookup,
        patch.object(Solar, 'fromYmdHms',
                     side_effect=AssertionError('calendar entered before version gate')) as calendar,
    ):
        try:
            subject.almanac('2026-10-21')
        except ValueError as error:
            assert str(error) == 'almanac_library_version_unsupported'
        else:
            raise AssertionError('unsupported version returned a calendar')
        lookup.assert_called_once_with('lunar-python')
        assert calendar.call_count == 0
        assert subject._package_identity.cache_info().currsize == 0
    subject._package_identity.cache_clear()
    restored = subject.almanac('2026-10-21')
    assert restored == baseline
    fields = ('date', 'calendar', 'timezone', 'sample_at', 'lunar', 'ganzhi',
              'yi', 'ji', 'chong_sha', 'duty', 'mansion', 'pengzu')
    for field in fields:
        assert restored['data'][field] == sample['data'][field]
    identity_fields = {'library_source_sha256', 'source_files_sha256'}
    for key, value in restored['data']['method'].items():
        if key not in identity_fields:
            assert value == sample['data']['method'][key]
    for group in ('c', 'r'):
        def alias_shape(row):
            keys = ('alias', 'path', 'rule_id', 'evidence_aliases')
            return {key: row[key] for key in keys if key in row}
        assert list(map(alias_shape, restored['aliases'][group])) == list(
            map(alias_shape, sample['aliases'][group]))
    for value in (sample, baseline, restored):
        fields_for_id = ('version', 'scope', 'data', 'rule_hits', 'sources')
        core = {key: value[key] for key in fields_for_id}
        assert value['document_id'] == 'tool-' + content_hash(core)
        for rows in value['aliases'].values():
            for row in rows:
                assert row['value_sha256'] == content_hash(pointer(value, row['path']))
                assert row['claim_id'] == 'claim-' + content_hash(
                    [value['document_id'], row['path'], row['value_sha256']])
    same_identity = restored['data']['method'] == sample['data']['method']
    if same_identity:
        assert restored == sample
    subject._package_identity.cache_clear()
print(json.dumps(dict(version_rejected=True, calendar_calls=0,
                     restored_equals_baseline=True, business_fields=len(fields),
                     alias_structure_equal=True, checked_results=3,
                     sample_identity_equal=same_identity)))
"""


def test_real_library_recovers_after_metadata_refusal_without_calendar_calls() -> None:
    python = os.environ.get("CHART_PYTHON")
    assert python and Path(python).is_file(), "requires explicit CHART_PYTHON"
    env = {
        key: value
        for key, value in os.environ.items()
        if "API_KEY" not in key.upper()
        and not key.upper().startswith(("LANGCHAIN", "LANGSMITH"))
    }
    env.update(PYTHONUTF8="1", LANGCHAIN_TRACING_V2="false", LANGSMITH_TRACING="false")
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
    summary = json.loads(process.stdout)
    assert summary["version_rejected"] is True
    assert summary["calendar_calls"] == 0
    assert summary["restored_equals_baseline"] is True
    assert summary["business_fields"] == 12
    assert summary["alias_structure_equal"] is True
    assert summary["checked_results"] == 3
    assert type(summary["sample_identity_equal"]) is bool
