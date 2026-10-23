"""A changing source cache cannot receive a false stable-content manifest."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from mingjing_core.adapters.charts.benchmarks import night24_sources


def test_mid_audit_source_change_is_rejected_without_echoing_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "synthetic"
    path = root / "data/data.json"
    path.parent.mkdir(parents=True)
    original = {"questions": []}
    path.write_text(json.dumps(original), encoding="utf-8")
    monkeypatch.setattr(
        night24_sources.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="b" * 40),
    )
    loader = night24_sources.load_corpus_v2
    calls = 0

    def changed(source: Path, source_kind: str, **kwargs: Any) -> Any:
        nonlocal calls
        result = loader(source, source_kind, **kwargs)
        calls += 1
        if calls == 1:
            source.write_text(
                json.dumps(original | {"private_marker": "synthetic-private-marker"}),
                encoding="utf-8",
            )
        return result

    monkeypatch.setattr(night24_sources, "load_corpus_v2", changed)
    with pytest.raises(ValueError) as error:
        night24_sources.audit_source(root, "mingli")
    assert str(error.value) == "e2_local_source_audit_failed"
    assert "synthetic-private-marker" not in str(error.value)
