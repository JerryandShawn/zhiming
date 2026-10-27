"""Frozen raw source and opaque labels do not narrow host owner/subject identities."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from mingjing_core.application import streaming_kernel
from mingjing_core.application.streaming_scope import HostStreamScope
from mingjing_core.domain.contracts import EvidenceError


def test_all_twelve_original_blobs_and_manifest_remain_exact() -> None:
    root = Path(streaming_kernel.__file__).absolute().parents[1] / "integrations/streaming_candidate"
    raw = (root / "SOURCE_MANIFEST.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == streaming_kernel.MANIFEST_SHA256
    manifest = json.loads(raw)
    assert manifest["source_commit"] == "ebfa22f8f7c59e486c6632035ae6bc8307f0f438"
    assert len(manifest["files"]) == 12 and sum(row["bytes"] for row in manifest["files"].values()) == 27382
    for name, row in manifest["files"].items():
        data = (root / name).read_bytes()
        assert len(data) == row["bytes"] and hashlib.sha256(data).hexdigest() == row["sha256"]
        header = b"blob " + str(len(data)).encode() + b"\0"
        assert hashlib.sha1(header + data, usedforsecurity=False).hexdigest() == row["source_git_blob"]
    streaming_kernel.verify_kernel()


def test_manifest_mismatch_refuses_kernel_before_import(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(streaming_kernel, "MANIFEST_SHA256", "0" * 64)
    with pytest.raises(EvidenceError, match="来源核验失败"):
        streaming_kernel.verify_kernel()


def test_unicode_and_delimiter_values_are_preserved_by_domain_separated_labels() -> None:
    scope = HostStreamScope("合成schema", "用户🌙", "人物甲", "无痕:线程", "原运行")
    labels = scope.kernel_scope()
    assert labels.owner_id.isascii() and labels.run_id.isascii()
    assert labels.owner_id != labels.run_id and scope.kernel_scope() == labels
    for field in ("schema", "owner", "subject", "thread_id", "run_id"):
        assert replace(scope, **{field: getattr(scope, field) + ":异"}).kernel_scope() != labels
    left = HostStreamScope("s", "a:b", "c", "t", "r")
    right = HostStreamScope("s", "a", "b:c", "t", "r")
    assert left.kernel_scope() != right.kernel_scope()
    assert "用户" not in repr(scope) and "人物" not in repr(scope)
