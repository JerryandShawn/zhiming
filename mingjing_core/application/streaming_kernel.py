"""One source-pinned import seam, replaceable after the module branch is integrated."""

from __future__ import annotations

import hashlib
import importlib
import json
from functools import lru_cache
from pathlib import Path
from types import ModuleType

from mingjing_core.domain.contracts import EvidenceError

SOURCE_COMMIT = "ebfa22f8f7c59e486c6632035ae6bc8307f0f438"
MANIFEST_SHA256 = "bb98bd12daafda15970d71ddb06c4600bad301889330531b144b03fd486bbd97"
PACKAGE = "mingjing_core.integrations.streaming_candidate"


def verify_kernel() -> None:
    root = Path(__file__).absolute().parents[1] / "integrations/streaming_candidate"
    manifest = root / "SOURCE_MANIFEST.json"
    try:
        if any(path.is_symlink() for path in (root, *root.parents, manifest)):
            raise ValueError("source link")
        raw = manifest.read_bytes()
        if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
            raise ValueError("source manifest")
        document = json.loads(raw)
        if document["source_commit"] != SOURCE_COMMIT or len(document["files"]) != 12:
            raise ValueError("source identity")
        for name, row in document["files"].items():
            if Path(name).name != name or not name.endswith(".py"):
                raise ValueError("source member")
            item = root / name
            if item.is_symlink() or hashlib.sha256(item.read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError("source changed")
    except (OSError, ValueError, KeyError, TypeError):
        raise EvidenceError("流式纯核来源核验失败") from None


@lru_cache(maxsize=1)
def load_kernel() -> ModuleType:
    verify_kernel()
    return importlib.import_module(PACKAGE + ".coalescer")
