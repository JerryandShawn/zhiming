"""The full evaluation cannot silently substitute P3's smaller passing subset."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.eval.contracts import scenario_contract_hash
from tools.eval.schema import load_scenarios
from tools.eval.targets.v4_corpus import split_recovery_contract
from tools.eval.targets.v4_full_corpus import write_full_corpus

SOURCE = Path(__file__).resolve().parents[3] / "tools/eval/scenarios"


def test_full_corpus_keeps_79_contracts_and_the_two_approved_recovery_variants(tmp_path: Path) -> None:
    destination = tmp_path / "full"
    assert write_full_corpus(SOURCE, destination) == {
        "questions": 80,
        "execution_cases": 81,
        "approved_channel_splits": 1,
    }
    originals = {case.id: case for case in load_scenarios(SOURCE)}
    full = {case.id: case for case in load_scenarios(destination)}
    assert set(full) == set(originals).difference({"X03"}) | {"X03a", "X03b"}
    for identity, case in originals.items():
        if identity != "X03":
            assert scenario_contract_hash(full[identity]) == scenario_contract_hash(case)
    for case in split_recovery_contract(originals["X03"]):
        assert scenario_contract_hash(full[case.id]) == scenario_contract_hash(case)


def test_full_corpus_rejects_partial_inputs_and_preserves_existing_outputs(tmp_path: Path) -> None:
    partial = tmp_path / "partial"
    partial.mkdir()
    (partial / "T05.yaml").write_bytes((SOURCE / "T05.yaml").read_bytes())
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="原80题"):
        write_full_corpus(partial, output)
    assert not output.exists()
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("synthetic existing file", encoding="utf-8")
    with pytest.raises(ValueError, match="空输出目录"):
        write_full_corpus(SOURCE, output)
    assert marker.read_text(encoding="utf-8") == "synthetic existing file"
