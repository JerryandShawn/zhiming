"""Snapshot provenance must detect input drift without ever reading blind or private material."""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.mod_week import completed_regression as regression


@pytest.fixture
def isolated_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    script = tmp_path / "tools/mod_week/completed_regression.py"
    script.parent.mkdir(parents=True)
    script.write_text("# synthetic snapshot runner\n", encoding="utf-8")
    monkeypatch.setattr(regression, "ROOT", tmp_path)
    monkeypatch.setattr(regression, "__file__", str(script))
    monkeypatch.setattr(regression, "SUITES", ("briefing_v2", "streaming", "organize_v2"))
    monkeypatch.setattr(regression.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=""))
    return tmp_path


def put(root: Path, name: str, value: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return path


def test_known_contract_byte_change_is_visible_in_source_identity(isolated_snapshot: Path) -> None:
    name = "tests/v4/briefing_v2/fixtures/acceptance_expected_mod.json"
    path = put(isolated_snapshot, name, '{"synthetic":1}\n')
    before = regression.source_snapshot()
    path.write_text('{"synthetic":2}\n', encoding="utf-8")
    after = regression.source_snapshot()
    assert before.keys() == after.keys() and before[name] != after[name]


def test_p2_calendar_table_appearing_midrun_changes_the_path_set(isolated_snapshot: Path) -> None:
    name = "config/holidays/2099.json"
    before = regression.source_snapshot()
    put(isolated_snapshot, name, '{"synthetic":true}\n')
    after = regression.source_snapshot()
    assert name not in before and name in after
    assert set(after) - set(before) == {name}


def test_blind_and_private_material_are_never_opened(isolated_snapshot: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    forbidden = {
        put(isolated_snapshot, "tests/v4/organize_v2/fixtures/blind_B.json", "synthetic sentinel\n"),
        put(isolated_snapshot, "private/calibration/v2/private_sentinel.json", "synthetic sentinel\n"),
    }
    known = "docs/v4/evidence/MOD_2026-10-21/events_v1.origin.schema.json"
    put(isolated_snapshot, known, '{"synthetic":true}\n')
    original = Path.read_bytes

    def guarded(path: Path) -> bytes:
        assert path not in forbidden, "snapshot_opened_forbidden_material"
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", guarded)
    captured = regression.source_snapshot()
    assert known in captured
    assert all("private/" not in key and "organize_v2/fixtures/" not in key for key in captured)


def test_new_public_frozen_matrix_is_explicitly_bound(isolated_snapshot: Path) -> None:
    name = "docs/v4/evidence/MOD_2026-10-21/BRIEF_public_boundaries_frozen_matrix_20261021.json"
    path = put(isolated_snapshot, name, '{"cases":["synthetic-a"]}\n')
    before = regression.source_snapshot()
    path.write_text('{"cases":["synthetic-b"]}\n', encoding="utf-8")
    after = regression.source_snapshot()
    assert before[name] != after[name]


def test_child_environment_removes_provider_credentials_without_mutating_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys = (
        "KIMI_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "LANGCHAIN_API_KEY",
        "LANGSMITH_API_KEY",
        "MOONSHOT_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "DEEPSEEK_API_KEY",
        "OPENROUTER_API_KEY",
        "DASHSCOPE_API_KEY",
        "XAI_API_KEY",
    )
    for key in keys:
        monkeypatch.setenv(key, "synthetic-never-sent")
    child = regression.environment()
    assert all(key not in child for key in keys)
    assert all(os.environ[key] == "synthetic-never-sent" for key in keys)


def test_child_environment_disables_both_tracing_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    child = regression.environment()
    assert child["LANGCHAIN_TRACING_V2"] == child["LANGSMITH_TRACING"] == "false"
    assert os.environ["LANGCHAIN_TRACING_V2"] == os.environ["LANGSMITH_TRACING"] == "true"
