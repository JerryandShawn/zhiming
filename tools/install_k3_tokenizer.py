"""Fetch six hash-pinned official tokenizer artifacts; never model weights."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mingjing_core.agent.k3_artifacts import read_k3_lock, regular_path, verify_artifacts  # noqa: E402


def _safe_url(url: str) -> bool:
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    return (
        parsed.scheme == "https"
        and parsed.port in {None, 443}
        and parsed.username is None
        and parsed.password is None
        and (host == "huggingface.co" or host.endswith((".huggingface.co", ".hf.co")))
    )


class PinnedRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Any:
        if not _safe_url(newurl):
            raise ValueError("官方分词器下载跳转无效")
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def install(destination: Path, *, verify_only: bool = False) -> dict[str, Any]:
    lock = read_k3_lock()
    regular_path(destination, allow_missing=not verify_only)
    if not verify_only:
        destination.mkdir(parents=True, exist_ok=True)
        regular_path(destination)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), PinnedRedirects())
        for name, expected in lock["files"].items():
            path = destination / name
            regular_path(path, allow_missing=True)
            if path.exists():
                if (
                    path.stat().st_size != expected["size"]
                    or hashlib.sha256(path.read_bytes()).hexdigest() != expected["sha256"]
                ):
                    raise ValueError("已有分词器文件校验失败，未覆盖")
                continue
            url = f"https://huggingface.co/{lock['repository']}/resolve/{lock['revision']}/{name}"
            with opener.open(url, timeout=30) as response:
                data = response.read(expected["size"] + 1)
            if len(data) != expected["size"] or hashlib.sha256(data).hexdigest() != expected["sha256"]:
                raise ValueError("官方分词器文件校验失败")
            with path.open("xb") as target:
                target.write(data)
    verified = verify_artifacts(destination, lock)
    return {"revision": lock["revision"], "files": len(verified), "bytes": sum(map(len, verified.values()))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(install(args.destination.absolute(), verify_only=args.verify_only)))
    except Exception:
        print("官方 K3 分词器未安装或未通过固定身份校验；未启用计量。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
