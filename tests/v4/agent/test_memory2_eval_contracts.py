"""P5 execution overlays cannot change scoring or claim absent contracts were tested."""

from pathlib import Path

import pytest

from tools.eval.contracts import scenario_contract_hash
from tools.eval.schema import load_scenarios
from tools.eval.targets.v4_memory2_corpus import (
    REQUIRED_MEMORY2_IDS,
    SUPPORTED_MEMORY2_IDS,
    write_memory2_corpus,
)

ROOT = Path(__file__).resolve().parents[3]


def test_memory_corpus_preserves_all_original_scoring_and_records_incomplete_coverage(tmp_path: Path) -> None:
    destination = tmp_path / "memory-runtime"
    manifest = write_memory2_corpus(ROOT / "tools/eval/scenarios", destination)
    originals = {case.id: case for case in load_scenarios(ROOT / "tools/eval/scenarios")}
    executable = load_scenarios(destination)
    assert len(REQUIRED_MEMORY2_IDS) == 37 and len(SUPPORTED_MEMORY2_IDS) == 27
    assert {case.id for case in executable} == SUPPORTED_MEMORY2_IDS
    assert manifest["complete_acceptance"] is False
    assert manifest["executable_does_not_imply_passed"] is True
    assert set(manifest["pending_action_drivers"]) == set()
    assert len(manifest["missing_contract_files"]) == 10
    for case in executable:
        assert scenario_contract_hash(case) == scenario_contract_hash(originals[case.id])
        for step in case.scripted:
            for action in step.model:
                assert action.db is None and action.receipt is None and action.event is None


def test_memory_corpus_refuses_to_overwrite_any_existing_output(tmp_path: Path) -> None:
    with pytest.raises(FileExistsError):
        write_memory2_corpus(ROOT / "tools/eval/scenarios", tmp_path)
