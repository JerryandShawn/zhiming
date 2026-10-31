"""Read one immutable teaching delivery; never run a calculator, model or HTTP client."""

from __future__ import annotations

import hashlib
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

from learning_samples.common import parse

COMMIT = "f8d9536a44db67a84db9315c208e2a66893214c9"
MANIFEST = "docs/v4/contracts/study_delivery_manifest.json"
MANIFEST_SHA = "1491b7ce765e2b4317c309fcceb05288b87222a40e40a284a375c22533781a6c"
PREFIX = "mingjing_core/knowledge/p8_learning_lessons/"
ROOT = Path(__file__).resolve().parents[2]
ERROR = "course_bundle_invalid"


def need(condition: bool) -> None:
    if not condition:
        raise ValueError(ERROR)


def normalized(raw: bytes) -> bytes:
    need(type(raw) is bytes and 0 < len(raw) <= 2 * 1024 * 1024)
    return raw.decode("utf8", errors="strict").replace("\r\n", "\n").encode("utf8")


def digest(raw: bytes) -> str:
    return hashlib.sha256(normalized(raw)).hexdigest()


def git_read(path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{COMMIT}:{path}"], cwd=ROOT, check=True, capture_output=True
    ).stdout


def load_bundle(
    reader: Callable[[str], bytes] = git_read,
) -> tuple[dict[str, dict], dict[str, str]]:
    try:
        raw = reader(MANIFEST)
        need(digest(raw) == MANIFEST_SHA)
        manifest = parse(raw)
        need(
            manifest["version"] == "p8-study-delivery-v1"
            and manifest["hash_normalization"] == "utf8_lf"
        )
        need(manifest["counts"] == {"terms": 212, "lessons": 20, "quizzes": 40})
        need(len(manifest["assets"]) == 32)
        values, hashes = {}, {}
        for item in manifest["assets"]:
            path = item["path"]
            need(
                type(path) is str
                and re.fullmatch(r"[A-Za-z0-9_./-]+", path) is not None
            )
            need(
                not path.startswith("/")
                and all(part not in {"", ".", ".."} for part in path.split("/"))
            )
            need(path not in values and path.endswith(".json"))
            body = reader(path)
            need(digest(body) == item["sha256_lf_utf8"])
            values[path], hashes[path] = parse(body), digest(body)
        return values, hashes
    except (
        KeyError,
        TypeError,
        UnicodeError,
        OSError,
        subprocess.CalledProcessError,
        ValueError,
    ):
        raise ValueError(ERROR) from None
