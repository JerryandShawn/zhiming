"""Offline export of six fixed, synthetic learning/chart Git blobs. No business imports."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections.abc import Callable
from pathlib import Path

from .common import COMMIT, ERROR, PREFIX, SYSTEMS, need, parse
from .projection import project_learning

WEB = next(
    path for path in Path(__file__).resolve().parents if path.name == "web" and (path / "package.json").is_file()
)
REPOSITORY = WEB.parent
EXPECTED = {
    "learning-ayuan-bazi.json": "3f4ad34140fed9a80b2899c75fe9c736dbfb6a0a40e27bd662cd5d5f52f5b497",
    "ayuan_bazi.json": "fe11a98184a296417f927d16cc57ee3ba664d77865393b9f20b2f867b0ea313b",
    "learning-ayuan-ziwei.json": "f6ec9b9709afa2266e6caebbc306d16eb9f33c970a6b5cc85aa13693b3ec90a0",
    "ayuan_ziwei.json": "306b1f368a310b6963187b983245e7c2d492b1ef59fbf99f8c5f28c3cd19571e",
    "learning-ayuan-astro.json": "1731e7bdeb4d06b29e7bcff3c9bcab0b2c306ebdac57e9e78ee9acf0bcf847a4",
    "ayuan_astro.json": "35a0bb10dce92aac401a49905b6c0d08fb127179de92418c79166c5ad8ea7f7c",
}
GitReader = Callable[[str], bytes]


def fixed_git(filename: str) -> bytes:
    need(filename in EXPECTED)
    return subprocess.run(
        ["git", "show", f"{COMMIT}:{PREFIX}{filename}"], cwd=REPOSITORY, check=True, capture_output=True
    ).stdout


def read_sources(reader: GitReader) -> dict[str, dict]:
    values = {}
    for filename, expected in EXPECTED.items():
        raw = reader(filename)
        need(type(raw) is bytes and hashlib.sha256(raw).hexdigest() == expected)
        values[filename] = parse(raw)
    return values


def projection_body(system: str, values: dict) -> tuple[str, bytes, dict]:
    filename, chart_name = f"learning-ayuan-{system}.json", f"ayuan_{system}.json"
    learning, chart = values[filename], values[chart_name]
    projection = project_learning(learning, chart, system)
    projection["provenance"] = {
        "source_commit": COMMIT,
        "mode": "published-synthetic-snapshot",
        "source_files": [{"path": PREFIX + name, "sha256": EXPECTED[name]} for name in (filename, chart_name)],
        "integrity": "original-documents-pointer-alias-claim-branch-and-card-templates-verified",
        "source_document_ids": learning["source_document_ids"][:],
    }
    body = (json.dumps(projection, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf8")
    entry = {
        "file": filename,
        "system": system,
        "sample_id": projection["sample_id"],
        "cards": len(projection["cards"]),
        "evidence": len(projection["evidence"]),
        "sha256": hashlib.sha256(body).hexdigest(),
        "bytes": len(body),
    }
    return filename, body, entry


def export_samples(output: Path, reader: GitReader = fixed_git) -> dict:
    output = output.resolve()
    need(WEB in output.parents and not output.exists())
    values = read_sources(reader)
    exports = [projection_body(system, values) for system in SYSTEMS]
    manifest = {
        "schema": "frontend-learning-export-v1",
        "source_commit": COMMIT,
        "synthetic_only": True,
        "model_calls": 0,
        "writes": 0,
        "entries": [entry for _, _, entry in exports],
    }
    # No output directory exists until all three independent cases validate.
    output.mkdir(parents=True, exist_ok=False)
    for filename, body, _ in exports:
        with (output / filename).open("xb") as stream:
            stream.write(body)
    with (output / "manifest.json").open("x", encoding="utf8", newline="\n") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="test-results/learning-projection",
        help="New directory relative to web; existing output is never replaced",
    )
    arguments = parser.parse_args()
    try:
        manifest = export_samples(WEB / arguments.output)
    except (ValueError, OSError, subprocess.CalledProcessError):
        raise SystemExit(ERROR) from None
    print(json.dumps({"status": "exported", "cases": len(manifest["entries"]), "model_calls": 0}))


if __name__ == "__main__":
    main()
