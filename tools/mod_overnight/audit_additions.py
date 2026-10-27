"""Audit the user-specified additive Git boundary and new Python size limits without reading secrets."""

import argparse
import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = "b9a89b6f84f7bebb640de080548010859aae630c"
sys.path.insert(0, str(ROOT))

from mingjing_core.timekit.clock import SystemClock  # noqa: E402


def parse_name_status(raw: bytes) -> list[dict[str, str]]:
    parts = raw.split(b"\x00")
    result, index = [], 0
    while index < len(parts) and parts[index]:
        status = parts[index].decode("ascii")
        item = {"status": status, "path": parts[index + 1].decode("utf-8")}
        index += 2
        if status.startswith(("R", "C")):
            item["new_path"] = parts[index].decode("utf-8")
            index += 1
        result.append(item)
    return result


def _git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def _python_checks(names: list[str]) -> tuple[list[dict], dict[str, str]]:
    violations, hashes = [], {}
    for name in names:
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or (ROOT / name).is_symlink():
            raise ValueError("审计发现模块工作目录外的引用")
        if path.suffix != ".py":
            continue
        raw = path.read_bytes()
        source = raw.decode("utf-8")
        hashes[name] = hashlib.sha256(raw).hexdigest()
        if len(source.splitlines()) > 400:
            violations.append({"path": name, "kind": "file_lines", "lines": len(source.splitlines())})
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.end_lineno - node.lineno + 1 > 60:
                violations.append({"path": name, "kind": "function_lines", "line": node.lineno})
    return violations, hashes


def audit() -> dict:
    branch = _git("branch", "--show-current").decode().strip()
    changes = parse_name_status(_git("diff", "--name-status", "-z", BASE, "--"))
    untracked = [
        part.decode("utf-8") for part in _git("ls-files", "--others", "--exclude-standard", "-z").split(b"\0") if part
    ]
    names = sorted({row["path"] for row in changes if row["status"] == "A"} | set(untracked))
    violations, hashes = _python_checks(names)
    forbidden = [row for row in changes if row["status"] != "A"]
    return {
        "base": BASE,
        "head": _git("rev-parse", "HEAD").decode().strip(),
        "branch": branch,
        "observed_at_utc": SystemClock().now().isoformat(),
        "new_paths": names,
        "new_path_count_including_untracked": len(names),
        "untracked_paths": untracked,
        "baseline_tracked_changes": forbidden,
        "new_python_files": len(hashes),
        "python_size_violations": violations,
        "source_sha256": hashes,
        "pass": branch.startswith("v4/mod-") and not forbidden and not violations,
        "meaning": "Git canonical content against frozen baseline; not an initial filesystem byte snapshot",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    target = args.output.resolve()
    if not target.is_relative_to(ROOT) or target.suffix != ".json":
        raise SystemExit("审计报告只能写入模块工作目录JSON文件")
    report = audit()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                key: report[key]
                for key in ("pass", "branch", "new_python_files", "baseline_tracked_changes", "python_size_violations")
            },
            ensure_ascii=False,
        )
    )
    if not report["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
