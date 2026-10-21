"""New bridge and token inputs stay in regression provenance even when their bytes change."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.mod_week import completed_regression as regression

MATERIALS = (
    "tools/eval/fixtures/mod_20261021/legacy_bridge_calendar_synthetic.json",
    "tools/eval/fixtures/mod_20261021/legacy_scalar_independent_synthetic.json",
    "docs/v4/evidence/MOD_2026-10-21/LEGACY_BRIDGE_frozen_matrix_20261021.json",
    "docs/v4/evidence/MOD_2026-10-21/LEGACY_SCALAR_frozen_matrix_20261021.json",
    "tools/eval/fixtures/mod_20261021/k3_public_boundaries_synthetic.json",
    "docs/v4/evidence/MOD_2026-10-21/K3_public_frozen_matrix_20261021.json",
)


@pytest.mark.parametrize("name", MATERIALS)
def test_new_public_material_mutation_changes_regression_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    script = tmp_path / "tools/mod_week/completed_regression.py"
    script.parent.mkdir(parents=True)
    script.write_text("# synthetic regression identity\n", encoding="utf-8")
    monkeypatch.setattr(regression, "ROOT", tmp_path)
    monkeypatch.setattr(regression, "__file__", str(script))
    monkeypatch.setattr(regression, "SUITES", ("organize_supplement_v2", "p9_v2"))
    monkeypatch.setattr(regression.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=""))
    material = tmp_path / name
    material.parent.mkdir(parents=True, exist_ok=True)
    material.write_text('{"synthetic_version":1}\n', encoding="utf-8")
    before = regression.source_snapshot()
    material.write_text('{"synthetic_version":2}\n', encoding="utf-8")
    after = regression.source_snapshot()
    assert before.keys() == after.keys() and before[name] != after[name]
    assert {key for key in before if before[key] != after[key]} == {name}
