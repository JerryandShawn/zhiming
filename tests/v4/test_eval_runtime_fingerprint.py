"""Resume identities must include the actual repository-owned loop limits."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.eval import runner


def test_runtime_config_bytes_invalidate_resume_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    path = tmp_path / "config/runtime.yaml"
    path.parent.mkdir()
    path.write_text("version: 1\ninteractive: {max_iterations: 40}\n", encoding="utf-8")
    before = runner._source_digest()
    assert before == runner._source_digest()
    path.write_text("version: 1\ninteractive: {max_iterations: 39}\n", encoding="utf-8")
    assert before != runner._source_digest()


def test_runtime_config_addition_or_loss_also_changes_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    original = runner._source_digest()
    path = tmp_path / "config/runtime.yaml"
    path.parent.mkdir()
    path.write_bytes(b"version: 1\n")
    assert runner._source_digest() != original
    path.unlink()
    assert runner._source_digest() == original


def test_fingerprint_does_not_expand_to_private_config_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    directory = tmp_path / "config"
    directory.mkdir()
    before = runner._source_digest()
    (directory / "credentials.env").write_text("synthetic-private-sentinel", encoding="utf-8")
    (directory / "unrelated.yaml").write_text("synthetic: true", encoding="utf-8")
    assert before == runner._source_digest()
