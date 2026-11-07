"""Additive P5 execution corpus: keep original scoring and strip scripted state injection."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from tools.eval.contracts import scenario_contract_hash
from tools.eval.schema import load_scenarios
from tools.eval.targets.v4_corpus import execution_overlay

REQUIRED_MEMORY2_IDS = frozenset(
    [f"M{i:02}" for i in range(1, 14)]
    + [f"R{i:02}" for i in range(1, 10)]
    + [f"F{i:02}" for i in range(1, 5)]
    + ["Q06", "A01", "A02", "A03", "MS01", "MS02", "MS03", "KU01", "KU02", "TM01", "TM02"]
)
SUPPORTED_MEMORY2_IDS = frozenset(
    [f"M{i:02}" for i in range(1, 14)] + [f"R{i:02}" for i in range(1, 10)] + ["Q06", "F01", "F02", "F03", "F04"]
)


def write_memory2_corpus(source: Path, destination: Path) -> dict:
    """Never change the frozen source or an existing output; gaps stay explicit."""
    originals = {case.id: case for case in load_scenarios(source) if case.id in REQUIRED_MEMORY2_IDS}
    missing_supported = SUPPORTED_MEMORY2_IDS - originals.keys()
    if missing_supported:
        raise ValueError("Required supported memory contracts are missing")
    manifest = {
        "target": "v4",
        "mode": "scripted",
        "complete_acceptance": False,
        "executable_does_not_imply_passed": True,
        "required_count": len(REQUIRED_MEMORY2_IDS),
        "executable_subset": sorted(SUPPORTED_MEMORY2_IDS),
        "missing_contract_files": sorted(REQUIRED_MEMORY2_IDS - originals.keys()),
        "pending_action_drivers": sorted(originals.keys() - SUPPORTED_MEMORY2_IDS),
        "contracts": {},
    }
    destination.mkdir(parents=True, exist_ok=False)
    for ident in sorted(SUPPORTED_MEMORY2_IDS):
        case = originals[ident]
        executable = execution_overlay(case)
        digest = scenario_contract_hash(case)
        if scenario_contract_hash(executable) != digest:
            raise ValueError("Memory execution overlay changed its scoring contract")
        manifest["contracts"][ident] = digest
        (destination / (ident + ".yaml")).write_text(
            yaml.safe_dump(executable.model_dump(mode="json", exclude_none=True), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    (destination / "p5_contract_coverage.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest
