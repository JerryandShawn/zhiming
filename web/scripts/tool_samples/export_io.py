"""Export only after all four immutable Git blobs pass projection checks."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path

from .common import FILES, PREFIX, SOURCE_REF, WEB, need, unique_object
from .synastry import project_synastry
from .window import project_window

GitReader = Callable[..., bytes]


def projected_blob(filename: str, commit: str, read_git: GitReader) -> tuple[bytes, dict, dict]:
    raw = read_git("show", f"{commit}:{PREFIX}{filename}")
    root = json.loads(raw, object_pairs_hook=unique_object)
    projection = project_window(root) if filename.startswith("window-") else project_synastry(root)
    projection["provenance"] = {
        "source_ref": SOURCE_REF,
        "source_commit": commit,
        "source_path": PREFIX + filename,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "mode": "published-synthetic-engine",
        "integrity": "root-document-pointer-alias-and-fact-digests-verified",
    }
    body = (json.dumps(projection, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf8")
    entry = {
        "file": filename,
        "tool": projection["tool"],
        "document_id": root["document_id"],
        "sha256": hashlib.sha256(body).hexdigest(),
    }
    return body, entry, projection


def check_same_window_query(windows: list[dict]) -> None:
    need(bool(windows) and len({row["query_sha256"] for row in windows}) == 1)
    need(all(row["ranking_summary"] == windows[0]["ranking_summary"] for row in windows))
    need(all(all(row[key] == windows[0][key] for key in ("purpose", "range", "weights")) for row in windows))


def export_samples(output: Path, read_git: GitReader) -> dict:
    output = output.resolve()
    need(WEB in output.parents)
    commit = read_git("rev-parse", SOURCE_REF).decode("ascii").strip()
    need(re.fullmatch(r"[0-9a-f]{40}", commit) is not None)
    exported, entries, windows = {}, [], []
    for filename in FILES:
        body, entry, projection = projected_blob(filename, commit, read_git)
        exported[filename] = body
        entries.append(entry)
        if projection["tool"] == "window_search":
            windows.append(projection["data"])
    check_same_window_query(windows)
    manifest = {
        "schema": "frontend-tools-export-v1",
        "source_ref": SOURCE_REF,
        "source_commit": commit,
        "synthetic_only": True,
        "model_calls": 0,
        "entries": entries,
    }
    output.mkdir(parents=True, exist_ok=False)
    for filename, body in exported.items():
        with (output / filename).open("xb") as stream:
            stream.write(body)
    with (output / "manifest.json").open("x", encoding="utf8", newline="\n") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return manifest
