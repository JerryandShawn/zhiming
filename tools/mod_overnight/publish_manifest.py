"""Verify committed additive-only publication objects without reading credentials."""

import argparse
import base64
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "b9a89b6f84f7bebb640de080548010859aae630c"


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def metadata(base: str, commit: str) -> dict:
    additive = git("diff", "--name-status", "--no-renames", BASELINE, commit).decode().splitlines()
    if any(not line.startswith("A\t") for line in additive):
        raise ValueError("原有基底文件发生变化，禁止发布")
    entries = []
    for line in git("diff", "--raw", "--full-index", "--no-abbrev", "--no-renames", base, commit).decode().splitlines():
        header, path = line.split("\t", 1)
        parts = header.split()
        mode, sha, status = parts[1], parts[3], parts[4]
        if mode != "100644" or status not in {"A", "M"}:
            raise ValueError("发布范围含删除或不允许的文件类型")
        if not path.startswith(
            (
                "mingjing_core/organize/",
                "mingjing_core/validation/",
                "mingjing_core/application/",
                "mingjing_core/adapters/channels/",
                "tests/v4/",
                "docs/v4/",
                "tools/mod_overnight/",
            )
        ):
            raise ValueError("发布范围越界")
        if path.startswith("private/") or ".env" in Path(path).name:
            raise ValueError("不能发布本机配置")
        entries.append({"path": path, "mode": mode, "type": "blob", "sha": sha, "status": status})
    return {
        "base": base,
        "commit": commit,
        "base_tree": git("rev-parse", base + "^{tree}").decode().strip(),
        "tree": git("rev-parse", commit + "^{tree}").decode().strip(),
        "entries": entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--blob")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=16000)
    args = parser.parse_args()
    value = metadata(args.base, args.commit)
    if args.blob:
        if args.blob not in {entry["sha"] for entry in value["entries"]}:
            raise ValueError("对象不属于本次提交")
        raw = git("cat-file", "blob", args.blob)
        try:
            content, encoding = raw.decode("utf-8"), "utf-8"
        except UnicodeDecodeError:
            content, encoding = base64.b64encode(raw).decode(), "base64"
        end = min(len(content), args.offset + args.limit)
        value = {
            "sha": args.blob,
            "encoding": encoding,
            "content": content[args.offset : end],
            "next_offset": end,
            "total": len(content),
        }
    print(json.dumps(value, ensure_ascii=False))


if __name__ == "__main__":
    main()
