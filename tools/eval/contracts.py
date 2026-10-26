"""Version the measurement contract independently from the system being measured."""

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from tools.eval.schema import Scenario

# Bump when deterministic assertion semantics change; business fixes do not change this version.
SCORING_CONTRACT_VERSION = "deterministic-eval-v1.1.0-board39"
FIXTURES = Path(__file__).parent / "fixtures"


def canonical_hash(value: Any) -> str:
    normalized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _fixture(name: str) -> Any:
    return yaml.safe_load((FIXTURES / name).read_text(encoding="utf-8"))


def scenario_contract_hash(scenario: Scenario, read_fixture: Callable[[str], Any] = _fixture) -> str:
    data = scenario.model_dump(mode="json", exclude={"title", "notes", "scripted"})
    fixtures = {"profile": read_fixture("profiles.yaml")[scenario.seed.profile]}
    if any(turn.expect.chart_stability is not None for turn in scenario.turns):
        fixtures["chart_stability"] = read_fixture("c06_ziwei_golden.yaml")
    return canonical_hash({"version": SCORING_CONTRACT_VERSION, "scenario": data, "fixtures": fixtures})


def scoring_corpus_hash(cases: list[dict[str, Any]]) -> str:
    contract = {case["id"]: case["scenario_contract_sha256"] for case in cases if case["status"] != "n/a on v3"}
    return canonical_hash(contract)


def stamp_contracts(report: dict[str, Any], scenarios: dict[str, Scenario]) -> None:
    for case in report["cases"]:
        case["scenario_contract_sha256"] = scenario_contract_hash(scenarios[case["id"]])
    report["metadata"].update(
        scoring_contract_version=SCORING_CONTRACT_VERSION,
        scoring_corpus_sha256=scoring_corpus_hash(report["cases"]),
    )
