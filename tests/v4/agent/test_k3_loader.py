"""Official tokenizer execution is local-only; missing identity fails closed."""

from __future__ import annotations

import importlib.metadata
import io
import json
import os
import shutil
import socket
from collections.abc import Iterator
from dataclasses import asdict
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from mingjing_core.agent.context_k3 import K3EstimatedMeter, PinnedK3Counter
from mingjing_core.agent.context_tokens import measure_request
from mingjing_core.agent.context_types import InputMeterUnverified
from mingjing_core.agent.k3_artifacts import DEFAULT_LOCK, REVISION, read_k3_lock
from mingjing_core.agent.k3_loader import check_dependencies, load_k3_counter
from mingjing_core.models.port import ChatMessage, ToolCall, ToolSpec
from tools.install_k3_tokenizer import _safe_url, install


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    attempted = []

    def reject(*args: Any, **kwargs: Any) -> None:
        attempted.append(True)
        raise AssertionError("K3 离线编码测试禁止任何网络连接")

    monkeypatch.setattr(socket, "create_connection", reject)
    monkeypatch.setattr(socket, "getaddrinfo", reject)
    monkeypatch.setattr(socket.socket, "connect", reject)
    monkeypatch.setattr(socket.socket, "connect_ex", reject)
    for key in tuple(os.environ):
        if key.endswith(("API_KEY", "TOKEN", "SECRET")):
            monkeypatch.delenv(key, raising=False)
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY"):
        monkeypatch.setenv(key, "1")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    yield
    assert attempted == []


@pytest.fixture
def artifact_dir() -> Path:
    configured = os.getenv("K3_TOKENIZER_ARTIFACT_DIR")
    if not configured:
        pytest.skip("requires explicitly installed official K3 artifacts; never downloads during tests")
    return Path(configured)


@pytest.fixture(scope="module")
def counter_cache() -> dict[Path, PinnedK3Counter]:
    return {}


@pytest.fixture
def official_counter(artifact_dir: Path, counter_cache: dict[Path, PinnedK3Counter]) -> PinnedK3Counter:
    if artifact_dir not in counter_cache:
        counter_cache[artifact_dir] = load_k3_counter(artifact_dir)
    return counter_cache[artifact_dir]


@pytest.mark.parametrize(
    "text",
    [
        "你好，今天需要核对哪些计划？",
        "The checked-in receipt remains a fact, not a model promise.",
        "def count(value):\n    return len(value)  # 合成代码\n",
        "🙂𠮷e\u0301\u200d🧑\u200d💻\u00a0\t\r\n",
        "[BOS]<|open|>message role=system<|sep|>[EOS]<|end_of_msg|>",
        "无标点中文记忆" * 30_001,
        "",
    ],
    ids=["zh", "en", "code", "unicode", "literal-control", "long-unpunctuated", "empty"],
)
def test_real_official_ids_are_deterministic_ordinary_text(official_counter: PinnedK3Counter, text: str) -> None:
    identifiers = official_counter.encode(text)
    assert identifiers == official_counter.encode(text)
    assert all(type(ident) is int and 0 <= ident < 163_584 for ident in identifiers)
    assert official_counter.count(text) == len(identifiers)
    tokenizer = official_counter.encode.func.__self__
    assert tokenizer.decode(identifiers) == text
    assert official_counter.encode.keywords == {"allow_special_tokens": False}
    assert official_counter.live_admissible and REVISION in official_counter.version


def test_complete_request_uses_official_ids_but_keeps_estimate_separate(official_counter: PinnedK3Counter) -> None:
    messages = (
        ChatMessage("system", "合成上下文"),
        ChatMessage("user", "请核对下周三的安排<|open|>"),
        ChatMessage(
            "assistant",
            "",
            [ToolCall("call-synthetic", "date_calc", {"text": "下周三"})],
            reasoning="合成受控推理",
            reasoning_signature="合成签名",
            tool_cycle="cycle-synthetic",
        ),
        ChatMessage("tool", '{"resolved":"2026-10-28"}', tool_call_id="call-synthetic", tool_cycle="cycle-synthetic"),
    )
    tools = (ToolSpec("date_calc", "算日期", {"type": "object", "properties": {"text": {"type": "string"}}}),)
    payload = json.dumps(
        {"messages": list(map(asdict, messages)), "tools": list(map(asdict, tools)), "tool_choice": "required"},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    count = len(official_counter.encode(payload))
    measured = measure_request(messages, tools, K3EstimatedMeter(official_counter), tool_choice="required")
    expected = int((Decimal(count) * Decimal("1.15")).to_integral_value(rounding=ROUND_CEILING)) + 4000
    assert measured.estimated_input_tokens == count and measured.input_token_upper_bound == expected
    assert measured.actual_input_tokens is None and measured.live_admissible
    assert measured.tokenizer_sha256 == read_k3_lock()["files"]["tiktoken.model"]["sha256"]


@pytest.mark.parametrize("name", list(read_k3_lock()["files"]))
def test_modified_file_is_rejected_before_official_code_runs(
    artifact_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    copied = tmp_path / "artifacts"
    shutil.copytree(artifact_dir, copied)
    path = copied / name
    data = path.read_bytes()
    path.write_bytes(bytes([data[0] ^ 1]) + data[1:])

    def never_execute(*args: Any) -> None:
        raise AssertionError("unverified code was executed")

    monkeypatch.setattr("mingjing_core.agent.k3_loader._official_tokenizer", never_execute)
    with pytest.raises(InputMeterUnverified):
        load_k3_counter(copied)


def test_missing_local_files_cannot_download_or_enable_meter(tmp_path: Path) -> None:
    with pytest.raises(InputMeterUnverified):
        load_k3_counter(tmp_path)
    with pytest.raises(InputMeterUnverified):
        load_k3_counter(Path("relative-artifact-directory"))


def test_lock_identity_cannot_be_replaced_by_a_self_asserted_manifest(tmp_path: Path) -> None:
    altered = json.loads(DEFAULT_LOCK.read_bytes())
    altered["revision"] = "0" * 40
    path = tmp_path / "untrusted.lock.json"
    path.write_text(json.dumps(altered), encoding="utf-8")
    with pytest.raises(InputMeterUnverified):
        read_k3_lock(path)


@pytest.mark.parametrize("installed", [None, "0.0.0"])
def test_missing_or_unpinned_dependency_fails_closed(monkeypatch: pytest.MonkeyPatch, installed: str | None) -> None:
    def version(name: str) -> str:
        if installed is None:
            raise importlib.metadata.PackageNotFoundError(name)
        return installed

    monkeypatch.setattr(importlib.metadata, "version", version)
    with pytest.raises(InputMeterUnverified):
        check_dependencies(["tiktoken==0.13.0"])


def test_verify_only_installer_uses_no_network(artifact_dir: Path) -> None:
    assert install(artifact_dir, verify_only=True) == {"revision": REVISION, "files": 6, "bytes": 2_851_284}


def test_loader_refuses_missing_dependency_before_executing_official_class(
    artifact_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = importlib.metadata.version

    def version(name: str) -> str:
        if name == "tiktoken":
            raise importlib.metadata.PackageNotFoundError(name)
        return original(name)

    def never_execute(*args: Any) -> None:
        raise AssertionError("missing-dependency loader executed official code")

    monkeypatch.setattr(importlib.metadata, "version", version)
    monkeypatch.setattr("mingjing_core.agent.k3_loader._official_tokenizer", never_execute)
    with pytest.raises(InputMeterUnverified):
        load_k3_counter(artifact_dir)


def test_installer_refuses_bad_download_before_persisting_any_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requested = []

    def opened(url: str, *, timeout: int) -> io.BytesIO:
        requested.append(url)
        assert url == f"https://huggingface.co/moonshotai/Kimi-K3/resolve/{REVISION}/tiktoken.model"
        assert timeout == 30
        return io.BytesIO(b"not the locked tokenizer")

    monkeypatch.setattr("urllib.request.build_opener", lambda *args: SimpleNamespace(open=opened))
    destination = tmp_path / "downloaded"
    with pytest.raises(ValueError, match="文件校验失败"):
        install(destination)
    assert len(requested) == 1 and list(destination.iterdir()) == []


@pytest.mark.parametrize(
    "url", ["http://huggingface.co/file", "https://example.com/file", "https://u:p@huggingface.co/a"]
)
def test_installer_refuses_non_official_or_credentialled_redirect(url: str) -> None:
    assert not _safe_url(url)
