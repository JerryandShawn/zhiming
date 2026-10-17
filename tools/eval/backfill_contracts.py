"""Add contract provenance to the frozen P0 run without re-executing or re-scoring it."""

import argparse
import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path, PureWindowsPath
from typing import Any

import yaml

from tools.eval.contracts import SCORING_CONTRACT_VERSION, scenario_contract_hash, scoring_corpus_hash
from tools.eval.report import markdown
from tools.eval.schema import Scenario

SUPPORTED_TREE = "c26619f7c85a8032d815e83a545314a14b276106"
LEGACY_FINGERPRINT_KEYS = (
    "mode",
    "target",
    "model",
    "judge_model",
    "judge_provider",
    "judge_schema_sha256",
    "rubric_version",
    "rubric_sha256",
    "config_version",
    "config_sha256",
    "source_sha256",
    "provider_endpoint_sha256",
)


class FrozenSource:
    def __init__(self, repository: Path, ref: str, execution_snapshot: Path | None = None) -> None:
        self.repository = repository
        self.execution_snapshot = execution_snapshot
        self.commit = self.git("rev-parse", "--verify", ref + "^{commit}").decode().strip()
        self.tree = self.git("rev-parse", self.commit + "^{tree}").decode().strip()
        self._cache: dict[str, bytes] = {}
        if self.tree != SUPPORTED_TREE or SCORING_CONTRACT_VERSION != "deterministic-eval-v1.0.0":
            raise ValueError("Backfill supports only the reviewed frozen P0 tree and scoring contract v1")

    def git(self, *arguments: str) -> bytes:
        result = subprocess.run(["git", "-C", str(self.repository), *arguments], capture_output=True, check=False)
        if result.returncode:
            raise ValueError("Frozen Git source is unavailable")
        return result.stdout

    def read(self, name: str) -> bytes:
        if name not in self._cache:
            data = self.git("show", self.commit + ":" + name)
            if self.execution_snapshot:
                actual = (self.execution_snapshot / name).read_bytes()
                if actual.replace(b"\r\n", b"\n") != data.replace(b"\r\n", b"\n"):
                    raise ValueError("Execution snapshot differs from frozen source beyond line endings")
            self._cache[name] = data
        return self._cache[name]

    def read_yaml(self, name: str) -> Any:
        return yaml.safe_load(self.read(name).decode("utf-8"))

    def fixture(self, name: str) -> Any:
        return self.read_yaml("tools/eval/fixtures/" + name)

    def scenario(self, identity: str) -> Scenario:
        return Scenario.model_validate(self.read_yaml("tools/eval/scenarios/" + identity + ".yaml"))

    def source_digest(self) -> str:
        names = self.git("ls-tree", "-r", "--name-only", "-z", self.commit).decode("utf-8").split("\0")
        paths = [name for name in names if _is_source(name)]
        if self.execution_snapshot:
            actual = {
                path.relative_to(self.execution_snapshot).as_posix() for path in self.execution_snapshot.rglob("*")
            }
            if {name for name in actual if _is_source(name)} != set(paths):
                raise ValueError("Execution snapshot contains missing or additional evaluation source files")
        digest = hashlib.sha256()
        for name in sorted(paths, key=PureWindowsPath):
            data = self.read(name)
            if self.execution_snapshot:
                data = (self.execution_snapshot / name).read_bytes()
            digest.update(name.encode("utf-8") + b"\x00" + data)
        return digest.hexdigest()


def _is_source(name: str) -> bool:
    path = Path(name)
    return (
        name.startswith("tools/eval/")
        and path.suffix == ".py"
        or name.startswith("tools/eval/fixtures/")
        and path.suffix == ".yaml"
        or name.startswith("mingjing_core/")
        and path.suffix in {".py", ".md", ".json", ".sql"}
        or path.parent == Path(".")
        and path.match("requirements*.lock")
    )


def _legacy_fingerprint(scenario: Scenario, metadata: dict[str, Any]) -> str:
    fixed = {key: metadata.get(key) for key in LEGACY_FINGERPRINT_KEYS}
    payload = {"scenario": scenario.model_dump(mode="json"), "metadata": fixed}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _verify_observation(case: dict[str, Any], scenario: Scenario, metadata: dict[str, Any]) -> None:
    if case["status"] == "n/a on v3":
        count_keys = (
            "model_calls",
            "target_model_calls",
            "judge_model_calls",
            "elapsed_seconds",
            "target_model_elapsed_seconds",
            "judge_model_elapsed_seconds",
        )
        observed_keys = (
            "assertions",
            "previews",
            "failed_assertions",
            "target_error_code",
            "judge_error_code",
            "stop_reason",
        )
        if "v3" in scenario.targets or any(case.get(key, 0) != 0 for key in count_keys):
            raise ValueError("Unfingerprinted n/a must be a truly inapplicable zero-call scenario")
        if case.get("score") is not None or any(case.get(key) for key in observed_keys):
            raise ValueError("An n/a case cannot contain real observations")
        if not case.get("fingerprint"):
            return
    if case.get("fingerprint") != _legacy_fingerprint(scenario, metadata):
        raise ValueError("Observed case does not match the frozen scenario and original execution fingerprint")


def backfill_report(report: dict[str, Any], source: FrozenSource) -> dict[str, Any]:
    metadata = report["metadata"]
    if metadata.get("scoring_contract_version", SCORING_CONTRACT_VERSION) != SCORING_CONTRACT_VERSION:
        raise ValueError("Existing scoring contract version cannot be reinterpreted")
    if source.source_digest() != metadata.get("source_sha256"):
        raise ValueError("Execution source bytes do not match the report; provide the exact preserved working snapshot")
    if metadata.get("mode") != "live" or metadata.get("target") != "v3":
        raise ValueError("Backfill is limited to the actual frozen P0 live/v3 report")
    result = deepcopy(report)
    for case in result["cases"]:
        scenario = source.scenario(case["id"])
        _verify_observation(case, scenario, metadata)
        digest = scenario_contract_hash(scenario, source.fixture)
        if case.get("scenario_contract_sha256", digest) != digest:
            raise ValueError("Existing scenario contract conflicts with frozen provenance")
        case["scenario_contract_sha256"] = digest
    result["metadata"].update(
        scoring_contract_version=SCORING_CONTRACT_VERSION,
        scoring_corpus_sha256=scoring_corpus_hash(result["cases"]),
        contract_backfill={
            "frozen_commit": source.commit,
            "frozen_tree": source.tree,
            "method": "verified-frozen-inputs-v1",
            "original_source_sha256": metadata["source_sha256"],
            "reexecuted": False,
            "rescored": False,
        },
    )
    if (
        metadata.get("scoring_corpus_sha256", result["metadata"]["scoring_corpus_sha256"])
        != result["metadata"]["scoring_corpus_sha256"]
    ):
        raise ValueError("Existing scoring corpus conflicts with frozen provenance")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--frozen-ref", required=True)
    parser.add_argument("--execution-snapshot", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args(argv)
    if args.report.resolve() == args.output.resolve() or args.output.exists() or args.output.name == "baseline-v3.json":
        raise ValueError("Write to a new reviewable output; the original report is preserved")
    if args.markdown_output and (
        args.markdown_output.exists()
        or args.markdown_output.resolve() in {args.report.resolve(), args.output.resolve()}
    ):
        raise ValueError("Markdown must also use a new reviewable output")
    source = FrozenSource(args.repository, args.frozen_ref, args.execution_snapshot)
    result = backfill_report(json.loads(args.report.read_text(encoding="utf-8")), source)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if args.markdown_output:
        args.markdown_output.write_text(markdown(result), encoding="utf-8")
    print("Contract metadata added; original source, scores, calls and report remain unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
