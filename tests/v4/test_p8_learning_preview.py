"""Tracked Core replay preserves old evidence and validates before writing."""

from __future__ import annotations

import hashlib
import json
import socket
import subprocess
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from jsonschema.exceptions import ValidationError

from mingjing_core.adapters.charts.benchmarks import learning_preview
from mingjing_core.timekit.clock import FrozenClock

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "docs/v4/contracts"


def templates() -> dict[str, Any]:
    return {
        system: json.loads(
            (CONTRACTS / "samples" / f"learning-ayuan-{system}.json").read_text("utf8")
        )
        for system in learning_preview.SYSTEMS
    }


def scripted(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    outputs = templates()
    calls = []

    def answer(original: dict) -> dict:
        system = original["request"]["system"]
        calls.append(system)
        return deepcopy(outputs[system])

    monkeypatch.setattr(learning_preview, "learning_outline", answer)
    return calls


def test_real_core_replay_validates_three_inputs_without_modifying_originals(
    tmp_path: Path,
) -> None:
    protected = [CONTRACTS / "learning_outline.schema.json"] + [
        CONTRACTS / "samples" / f"ayuan_{system}.json"
        for system in learning_preview.SYSTEMS
    ]
    old_performance = ROOT / "docs/v4/evidence/P8/night28-learning-performance.json"
    protected.append(old_performance)
    before = {path: path.read_bytes() for path in protected}
    report = learning_preview.generate_previews(
        CONTRACTS, tmp_path / "samples", tmp_path / "new-performance.json"
    )
    assert all(path.read_bytes() == raw for path, raw in before.items())
    assert len(list((tmp_path / "samples").glob("*.json"))) == 3
    for system, row in report["measurements"].items():
        assert row["warmups"] == 1 and row["observations"] == 10
        assert len(row["milliseconds"]) == 10 and all(
            value >= 0 for value in row["milliseconds"]
        )
        result = json.loads(
            (tmp_path / "samples" / f"learning-ayuan-{system}.json").read_text("utf8")
        )
        assert result["scope"]["subject_id"] == "synthetic-subject-ayuan"
        assert row["points"] == len(result["points"])
        source = report["provenance"]["chart_inputs"][system]
        assert (
            source["file_sha256"]
            == hashlib.sha256(
                before[CONTRACTS / "samples" / source["file"]]
            ).hexdigest()
        )
    assert (
        report["model_calls"]
        == report["chart_processes"]
        == report["profile_writes"]
        == 0
    )
    assert report["recorded_at_beijing"].endswith("+08:00")


def test_replay_is_offline_clears_credentials_and_launches_no_child_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = templates()
    calls = []
    monkeypatch.setenv("KIMI_API_KEY", "synthetic-test-only-not-a-secret")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")

    def answer(original: dict) -> dict:
        import os

        assert not any("API_KEY" in name.upper() for name in os.environ)
        assert os.environ["LANGSMITH_TRACING"] == "false"
        assert os.environ["LANGCHAIN_TRACING_V2"] == "false"
        if not calls:
            with pytest.raises(RuntimeError, match="disabled"):
                socket.create_connection(("127.0.0.1", 1))
            with pytest.raises(RuntimeError, match="disabled"):
                subprocess.run(["must-not-start"], check=False)
            with pytest.raises(RuntimeError, match="disabled"):
                subprocess.Popen(["must-not-start"])
        system = original["request"]["system"]
        calls.append(system)
        return deepcopy(outputs[system])

    monkeypatch.setattr(learning_preview, "learning_outline", answer)
    learning_preview.generate_previews(
        CONTRACTS, tmp_path / "samples", tmp_path / "performance.json"
    )
    assert calls == [system for system in learning_preview.SYSTEMS for _ in range(11)]


def test_existing_performance_is_never_replaced_and_no_samples_are_written(
    tmp_path: Path,
) -> None:
    performance = tmp_path / "prior.json"
    performance.write_text('{"historical":true}', encoding="utf8")
    output = tmp_path / "samples"
    with pytest.raises(ValueError, match="performance_output_exists"):
        learning_preview.generate_previews(CONTRACTS, output, performance)
    assert performance.read_text("utf8") == '{"historical":true}'
    assert not output.exists()


@pytest.mark.parametrize("keyword", ["$ref", "$dynamicRef"])
def test_static_schema_cannot_request_an_external_reference(
    tmp_path: Path,
    keyword: str,
) -> None:
    contract = tmp_path / "contracts"
    contract.mkdir()
    (contract / "learning_outline.schema.json").write_text(
        json.dumps({keyword: "https://invalid.example/schema.json"}), encoding="utf8"
    )
    with pytest.raises(ValueError, match="external_schema_ref_forbidden"):
        learning_preview.generate_previews(
            contract, tmp_path / "samples", tmp_path / "performance.json"
        )
    assert not (tmp_path / "samples").exists()
    assert not (tmp_path / "performance.json").exists()


def test_third_invalid_learning_result_cannot_partially_replace_samples(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = templates()

    def answer(original: dict) -> dict:
        result = deepcopy(outputs[original["request"]["system"]])
        if original["request"]["system"] == "astro":
            result["effects"]["model_calls"] = 1
        return result

    monkeypatch.setattr(learning_preview, "learning_outline", answer)
    with pytest.raises(ValidationError):
        learning_preview.generate_previews(
            CONTRACTS, tmp_path / "samples", tmp_path / "performance.json"
        )
    assert not (tmp_path / "samples").exists()
    assert not (tmp_path / "performance.json").exists()


@pytest.mark.parametrize("arguments", [[], ["--mode", "live"]])
def test_cli_requires_scripted_mode(arguments: list[str]) -> None:
    with pytest.raises(SystemExit) as error:
        learning_preview.main(arguments)
    assert error.value.code == 2


def test_cli_paths_do_not_depend_on_cwd_and_time_is_explicit_beijing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scripted(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(learning_preview, "EVIDENCE", tmp_path / "evidence")
    monkeypatch.setattr(
        learning_preview,
        "get_clock",
        lambda: FrozenClock(datetime(2026, 10, 20, 16, 12, tzinfo=UTC)),
    )
    assert (
        learning_preview.main(
            ["--mode", "scripted", "--output-dir", str(tmp_path / "samples")]
        )
        == 0
    )
    reports = list((tmp_path / "evidence").glob("*.json"))
    assert len(reports) == 1
    assert reports[0].name.startswith("learning-preview-20261021T001200")
    report = json.loads(reports[0].read_text("utf8"))
    assert report["recorded_at_beijing"] == "2026-10-21T00:12:00+08:00"
    assert report["started_at_beijing"] == report["recorded_at_beijing"]
