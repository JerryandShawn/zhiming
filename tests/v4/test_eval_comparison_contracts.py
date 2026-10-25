"""Score improvements require identical measurement inputs and assertion semantics."""

import json
import subprocess
from argparse import Namespace
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml

from tools.eval import backfill_contracts, contracts, runner
from tools.eval.backfill_contracts import FrozenSource, backfill_report
from tools.eval.contracts import scenario_contract_hash, scoring_corpus_hash
from tools.eval.report import _comparison_reason, add_comparison, summarize
from tools.eval.schema import Scenario, load_scenarios

SCENARIOS = {scenario.id: scenario for scenario in load_scenarios()}
PROFILES = yaml.safe_load((contracts.FIXTURES / "profiles.yaml").read_text(encoding="utf-8"))


def measurement(scenario: Scenario, *, fixtures: dict[str, Any] | None = None) -> dict[str, Any]:
    reader = fixtures.__getitem__ if fixtures else contracts._fixture
    cases = [
        {
            "id": scenario.id,
            "category": scenario.category,
            "status": "failed",
            "score": 0,
            "scenario_contract_sha256": scenario_contract_hash(scenario, reader),
        }
    ]
    return {
        "metadata": {
            "mode": "live",
            "target": "v3",
            "status": "complete",
            "model": "primary-one",
            "judge_model": "fixed",
            "judge_provider": "fixed",
            "judge_schema_sha256": "schema",
            "rubric_version": "fixed",
            "rubric_sha256": "rubric",
            "source_sha256": "business-v1",
            "scoring_contract_version": contracts.SCORING_CONTRACT_VERSION,
            "scoring_corpus_sha256": scoring_corpus_hash(cases),
        },
        "cases": cases,
        "summary": summarize(cases),
    }


@pytest.mark.parametrize("changed", ["expect", "seed", "clock"])
def test_same_id_changed_inputs_cannot_claim_improvement(changed: str) -> None:
    original = SCENARIOS["C04"]
    value = original.model_dump(mode="json")
    if changed == "expect":
        value["turns"][0]["expect"]["must_not_include"].append("新增的词面禁用条件")
    elif changed == "seed":
        value["seed"]["profile_overrides"] = {"name": "另一位合成人物"}
    else:
        value["clock"] = "2026-10-18T10:30:00+08:00"
    current = measurement(Scenario.model_validate(value))
    baseline = measurement(original)
    current["cases"][0].update(score=1, status="passed")
    assert _comparison_reason(current, baseline) == "scenario_contract_changed"


@pytest.mark.parametrize("kind", ["profile", "chart_golden"])
def test_referenced_fixture_changes_invalidate_same_id_comparison(kind: str) -> None:
    scenario = SCENARIOS["C04" if kind == "profile" else "C06"]
    fixtures = {
        "profiles.yaml": deepcopy(PROFILES),
        "c06_ziwei_golden.yaml": contracts._fixture("c06_ziwei_golden.yaml"),
    }
    baseline = measurement(scenario, fixtures=fixtures)
    if kind == "profile":
        fixtures["profiles.yaml"]["default_synthetic"]["occupation"] = "合成新职业"
    else:
        fixtures["c06_ziwei_golden.yaml"]["versions"]["engine"] = "synthetic-next-version"
    assert _comparison_reason(measurement(scenario, fixtures=fixtures), baseline) == "scenario_contract_changed"


def test_business_source_and_primary_model_changes_remain_comparable() -> None:
    baseline = measurement(SCENARIOS["C04"])
    current = deepcopy(baseline)
    current["metadata"].update(source_sha256="business-v2", model="primary-two", target="v4")
    assert _comparison_reason(current, baseline) is None


def test_assertion_semantics_version_change_prevents_comparison() -> None:
    baseline = measurement(SCENARIOS["C04"])
    current = deepcopy(baseline)
    current["metadata"]["scoring_contract_version"] = "deterministic-eval-v2.0.0"
    assert _comparison_reason(current, baseline) == "scoring_contract_changed"


def test_missing_legacy_contract_is_not_assumed_comparable(tmp_path: Path) -> None:
    baseline = measurement(SCENARIOS["C04"])
    del baseline["cases"][0]["scenario_contract_sha256"]
    path = tmp_path / "baseline-v3.json"
    path.write_text(json.dumps(baseline), encoding="utf-8")
    current = measurement(SCENARIOS["C04"])
    add_comparison(current, path)
    assert current["comparison"]["reason"] == "scenario_contract_missing"
    assert "score_delta" not in current["comparison"]


def test_declared_corpus_digest_must_match_case_contracts() -> None:
    baseline = measurement(SCENARIOS["C04"])
    current = deepcopy(baseline)
    current["cases"][0]["scenario_contract_sha256"] = "replaced"
    assert _comparison_reason(current, baseline) == "scenario_contract_changed"


def test_yaml_format_and_unrelated_profile_do_not_change_live_contract() -> None:
    scenario = SCENARIOS["C04"]
    normalized = Scenario.model_validate(
        yaml.safe_load(yaml.safe_dump(scenario.model_dump(mode="json"), sort_keys=True))
    )
    fixtures = {"profiles.yaml": deepcopy(PROFILES)}
    fixtures["profiles.yaml"]["empty_profile"]["note"] = "Unrelated synthetic fixture"
    assert scenario_contract_hash(normalized, fixtures.__getitem__) == scenario_contract_hash(scenario)


def _git(repository: Path, *args: str, input_bytes: bytes | None = None) -> str:
    result = subprocess.run(["git", "-C", str(repository), *args], input=input_bytes, capture_output=True, check=True)
    return result.stdout.decode("utf-8").strip()


@pytest.fixture
def frozen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[FrozenSource, dict[str, Any], Path]:
    repository, execution = tmp_path / "git-source", tmp_path / "execution-bytes"
    repository.mkdir()
    files = {
        "tools/eval/judges.py": b"contract = 1\n",
        "requirements-core.lock": b"synthetic-dependency==1\n",
        "tools/eval/fixtures/profiles.yaml": yaml.safe_dump(PROFILES, allow_unicode=True).encode("utf-8"),
    }
    for identity in ("C04", "F01"):
        files[f"tools/eval/scenarios/{identity}.yaml"] = yaml.safe_dump(
            SCENARIOS[identity].model_dump(mode="json"), allow_unicode=True
        ).encode("utf-8")
    for name, content in files.items():
        path = repository / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        copied = execution / name
        copied.parent.mkdir(parents=True, exist_ok=True)
        copied.write_bytes(content.replace(b"\n", b"\r\n"))
    _git(repository, "init", "--quiet")
    _git(repository, "-c", "core.autocrlf=false", "add", ".")
    tree = _git(repository, "write-tree")
    commit = _git(
        repository,
        "-c",
        "user.name=Synthetic",
        "-c",
        "user.email=synthetic@example.invalid",
        "commit-tree",
        tree,
        input_bytes=b"Synthetic frozen provenance\n",
    )
    # Board v39 versions current scoring; this synthetic archive explicitly represents legacy v1.
    # Keep the production frozen-tree/version gate intact.
    monkeypatch.setattr(contracts, "SCORING_CONTRACT_VERSION", "deterministic-eval-v1.0.0")
    monkeypatch.setattr(backfill_contracts, "SCORING_CONTRACT_VERSION", "deterministic-eval-v1.0.0")
    monkeypatch.setattr(backfill_contracts, "SUPPORTED_TREE", tree)
    source = FrozenSource(repository, commit, execution)
    report = measurement(SCENARIOS["C04"])
    report["metadata"].update(
        source_sha256=source.source_digest(), config_sha256="fixed", provider_endpoint_sha256="fixed"
    )
    report["metadata"].pop("scoring_contract_version")
    report["metadata"].pop("scoring_corpus_sha256")
    report["cases"][0].pop("scenario_contract_sha256")
    report["cases"][0].update(
        fingerprint=backfill_contracts._legacy_fingerprint(source.scenario("C04"), report["metadata"]),
        model_calls=7,
        target_model_calls=5,
        judge_model_calls=2,
        error_category="business",
        score=0,
    )
    report["cases"].append({"id": "F01", "status": "n/a on v3", "score": None, "model_calls": 0})
    return source, report, execution


def test_backfill_preserves_original_execution_scores_calls_and_unfingerprinted_na(frozen: Any) -> None:
    source, report, _ = frozen
    original = deepcopy(report)
    augmented = backfill_report(report, source)
    assert report == original
    assert augmented["metadata"]["source_sha256"] == original["metadata"]["source_sha256"]
    assert augmented["summary"] == original["summary"]
    for old, new in zip(original["cases"], augmented["cases"], strict=True):
        assert {key: new[key] for key in old} == old
        assert set(new) - set(old) == {"scenario_contract_sha256"}
    assert augmented["metadata"]["contract_backfill"]["reexecuted"] is False
    assert augmented["metadata"]["contract_backfill"]["rescored"] is False


def test_lf_archive_cannot_impersonate_original_crlf_execution_source(frozen: Any) -> None:
    source, report, _ = frozen
    archive_only = FrozenSource(source.repository, source.commit)
    with pytest.raises(ValueError, match="Execution source bytes do not match"):
        backfill_report(report, archive_only)


@pytest.mark.parametrize("mutation", ["fingerprint", "observed_na", "na_calls", "applicable_na"])
def test_backfill_rejects_unproven_observations(frozen: Any, mutation: str) -> None:
    source, report, _ = frozen
    if mutation == "fingerprint":
        report["cases"][0]["fingerprint"] = "tampered"
    elif mutation == "observed_na":
        report["cases"][1]["previews"] = ["not a zero-observation case"]
    elif mutation == "na_calls":
        report["cases"][1]["model_calls"] = 1
    else:
        report["cases"][0].update(status="n/a on v3", score=None)
    with pytest.raises(ValueError):
        backfill_report(report, source)


def test_changed_execution_snapshot_is_rejected(frozen: Any) -> None:
    source, report, execution = frozen
    (execution / "tools/eval/judges.py").write_bytes(b"contract = 2\r\n")
    with pytest.raises(ValueError):
        backfill_report(report, source)


def test_partial_business_zero_cannot_be_silently_rerun_after_source_change(frozen: Any, tmp_path: Path) -> None:
    source, report, _ = frozen
    report["metadata"].update(status="incomplete", stop_reason="quota", requires_user_decision=True)
    augmented = backfill_report(report, source)
    path = tmp_path / "2026-10-17-live-v3-primary.json"
    path.write_text(json.dumps(augmented), encoding="utf-8")
    args = Namespace(resume=True, output=tmp_path)
    current_metadata = {**augmented["metadata"], "source_sha256": "new-patched-runtime"}
    with pytest.raises(SystemExit, match="preserved frozen execution snapshot"):
        runner._resume_report(args, current_metadata)
    reusable = runner._resume_cases(args, augmented["metadata"])
    assert reusable["C04"]["score"] == 0
    assert reusable["C04"]["model_calls"] == 7
    assert augmented["metadata"]["status"] == "incomplete"


@pytest.mark.parametrize("destination", ["input.json", "baseline-v3.json"])
def test_backfill_cli_cannot_overwrite_or_manufacture_a_baseline(tmp_path: Path, destination: str) -> None:
    original = tmp_path / "input.json"
    original.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="new reviewable output"):
        backfill_contracts.main(
            [
                "--repository",
                str(tmp_path),
                "--frozen-ref",
                "unused",
                "--report",
                str(original),
                "--output",
                str(tmp_path / destination),
            ]
        )
    assert original.read_text(encoding="utf-8") == "{}"
    assert not (tmp_path / "baseline-v3.json").exists()
