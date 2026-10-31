"""Offline glossary export from one audited immutable Git commit.

Only authoring artifacts are written. No HTTP, model, database, SDK or subprocess
other than read-only Git is reachable. Relative --output paths start at web/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

from study_glossary import project_glossary
from study_schema import StudyExportError, parse, require

WEB = next(
    path for path in Path(__file__).resolve().parents if path.name == "web" and (path / "package.json").is_file()
)
REPOSITORY = WEB.parent
SOURCE_REF = "origin/v4/p8-calc"
FROZEN_COMMIT = "0f1d6e676259b961819de4da5ea3f343d58dbe98"
TERMS = "mingjing_core/knowledge/p8_glossary/terms_v1.json"
SOURCES = "mingjing_core/knowledge/p8_glossary/sources_v1.json"
TERMS_SCHEMA = "docs/v4/contracts/glossary.schema.json"
SOURCES_SCHEMA = "docs/v4/contracts/glossary_sources.schema.json"
INPUTS = {
    TERMS: "b1005b6e1748c7cb0dc680ff0b43ea93c4e54819b3a23da49f8e5b3a0cd197b3",
    SOURCES: "a781219cbf9f364ca6fbe89e82ce5e4640a99851a29bc65988b7ddcfcf67f1f1",
    TERMS_SCHEMA: "42555c9db476bcce4f14c5e310b6bcae376c50e25c94abf01dade72cb40d5cc4",
    SOURCES_SCHEMA: "cc7a23f9fecceb51918a01b6e6145342eff63a625611634ca2cc5e93084fd084",
}
GitReader = Callable[..., bytes]


def git(*arguments: str) -> bytes:
    return subprocess.run(["git", *arguments], cwd=REPOSITORY, check=True, capture_output=True).stdout


def digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def read_inputs(read_git: GitReader) -> tuple[str, dict[str, dict], set[str], list[dict]]:
    commit = read_git("rev-parse", "--verify", FROZEN_COMMIT + "^{commit}").decode("ascii").strip()
    require(re.fullmatch(r"[a-f0-9]{40}", commit) is not None and commit == FROZEN_COMMIT)
    tree = read_git("ls-tree", "-r", "--name-only", commit, "--").decode("utf8").splitlines()
    records, values = [], {}
    for path, expected in INPUTS.items():
        raw = read_git("show", f"{commit}:{path}")
        require(0 < len(raw) <= 2 * 1024 * 1024 and digest(raw) == expected)
        value = parse(raw)
        require(isinstance(value, dict))
        values[path] = value
        records.append({"path": path, "sha256": digest(raw), "bytes": len(raw)})
    return commit, values, set(tree), records


def export_glossary(output: Path, read_git: GitReader = git) -> dict:
    output = output.resolve()
    require(WEB in output.parents and not output.exists())
    commit, values, paths, inputs = read_inputs(read_git)
    terms, sources = project_glossary(
        values[TERMS], values[SOURCES], values[TERMS_SCHEMA], values[SOURCES_SCHEMA], paths
    )
    outputs = {}
    entries = []
    for name, data in (("terms_v1.json", terms), ("sources_v1.json", sources)):
        raw = (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf8")
        outputs[name] = raw
        entries.append({"file": name, "sha256": digest(raw), "bytes": len(raw)})
    manifest = {
        "schema": "frontend-study-glossary-export-v1",
        "source_ref": SOURCE_REF,
        "source_commit": commit,
        "mode": "static-educational-only",
        "selection": "frozen-audited-commit",
        "model_calls": 0,
        "business_writes": 0,
        "inputs": inputs,
        "entries": entries,
        "entry_count": terms["entry_count"],
        "system_counts": terms["system_counts"],
        "source_count": len(sources["sources"]),
        "stage": terms["stage"],
        "review_tag": terms.get("review_tag"),
        "source_urls_fetched": 0,
        "source_paths_checked_in_git_tree": True,
        "rendering": "plain_text_only_no_html_execution_no_current_user_evidence",
    }
    # Nothing is created until every dataset and cross-reference is checked.
    output.mkdir(parents=True, exist_ok=False)
    for name, raw in outputs.items():
        with (output / name).open("xb") as stream:
            stream.write(raw)
    with (output / "manifest.json").open("x", encoding="utf8", newline="\n") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="test-results/study-glossary", help="New directory relative to web/")
    args = parser.parse_args()
    try:
        manifest = export_glossary(WEB / args.output)
    except (StudyExportError, OSError, ValueError, TypeError, KeyError, subprocess.CalledProcessError):
        raise SystemExit("Study glossary export unavailable; source values are never printed.") from None
    print(json.dumps({"status": "exported", "entry_count": manifest["entry_count"], "model_calls": 0}))


if __name__ == "__main__":
    main()
