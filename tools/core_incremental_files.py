"""Pinned file checks and manifest-last Hermes retargeting under the writer fence."""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import Any

from tools.core_incremental_contracts import (
    EXPECTED_MANIFEST,
    MIGRATIONS,
    PREVIOUS,
    RELEASE_ROOT,
    TARGET,
    Request,
    digest,
    require,
)

ENV_FILES = ("/root/.hermes/.env", "/root/zhiming-core-secrets/live-runtime.env")
SKILL = "/root/.hermes/skills/zhiming"
PREVIOUS_MANIFEST = "22edb794d44ab45e2b234edd3f5ed886879fe88d23392977fee63e1085a3859c"


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def traversal_error(error: OSError) -> None:
    require(False, "RELEASE_TRAVERSAL_FAILED")


def regular(path: Path, *, private: bool = False) -> None:
    require(path.is_file() and not any(item.is_symlink() for item in (path, *path.parents)), "UNSAFE_FILE")
    require(not private or path.stat().st_mode & 0o077 == 0, "PRIVATE_FILE_MODE")


def private_write(path: Path, data: bytes, *, replace: bool = False) -> None:
    require(not any(item.is_symlink() for item in (path, *path.parents)), "UNSAFE_FILE")
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    temporary = path.with_name(path.name + ".incremental-new")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        require(replace or not path.exists(), "OUTPUT_ALREADY_EXISTS")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class HostFiles:
    """root is only injectable via Python tests; production CLI always uses '/'."""

    def __init__(
        self,
        root: Path = Path("/"),
        *,
        approved_manifest: str = EXPECTED_MANIFEST,
        previous_manifest: str = PREVIOUS_MANIFEST,
    ) -> None:
        self.root = root
        self.approved_manifest = approved_manifest
        self.previous_manifest = previous_manifest

    def path(self, name: str) -> Path:
        value = PurePosixPath(name)
        require(value.is_absolute() and ".." not in value.parts, "ABSOLUTE_SAFE_PATH")
        return self.root.joinpath(*value.parts[1:])

    def release(self, request: Request) -> dict[str, Any]:
        root = self.path(request.release)
        path = root / "__release_manifest__.json"
        regular(path, private=True)
        require(request.manifest_sha256 == self.approved_manifest, "PINNED_RELEASE_MANIFEST")
        require(file_sha(path) == request.manifest_sha256, "RELEASE_MANIFEST")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        require(manifest.get("schema") == "core3-release-v1" and manifest.get("commit") == TARGET, "RELEASE_SOURCE")
        rows = manifest.get("files")
        require(isinstance(rows, dict) and rows, "RELEASE_FILES")
        for name, row in rows.items():
            relative = PurePosixPath(name)
            require(not relative.is_absolute() and ".." not in relative.parts and "\\" not in name, "RELEASE_MEMBER")
            item = root.joinpath(*relative.parts)
            regular(item)
            require(file_sha(item) == row.get("sha256"), "RELEASE_FILE_CHANGED")
        allowed = {*rows, "__release_manifest__.json", "calculator-validation.json"}
        for directory, names, filenames in os.walk(root, followlinks=False, onerror=traversal_error):
            current = Path(directory)
            for name in names[:]:
                item = current / name
                require(not item.is_symlink(), "RELEASE_SYMLINK")
                if name == "__pycache__" or item == root / "venv":
                    names.remove(name)
            for name in filenames:
                item = current / name
                require(not item.is_symlink(), "RELEASE_SYMLINK")
                require(item.relative_to(root).as_posix() in allowed, "UNEXPECTED_RELEASE_FILE")
        actual = {}
        for path in sorted((root / "mingjing_core/repositories/migrations").glob("[0-9][0-9][0-9][0-9]_*.sql")):
            actual[str(int(path.name[:4]))] = hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        require(actual == MIGRATIONS, "PACKAGE_MIGRATIONS")
        return manifest

    def verify_units(self, request: Request) -> None:
        old = f"{RELEASE_ROOT}/{PREVIOUS}"
        for name, expected in request.unit_sha256.items():
            path = self.path("/etc/systemd/system/" + name)
            if expected == "absent":
                require(request.scope == "stage" and not path.exists(), "UNEXPECTED_STAGE_UNIT")
                continue
            regular(path)
            require(file_sha(path) == expected, "UNIT_CHANGED")
            content = path.read_text(encoding="utf-8")
            if name.endswith(".service"):
                require(old in content and "hermes.service" not in content, "UNIT_FIXED_SOURCE")

    def retarget_units(self, request: Request, backup: Path) -> dict[str, str]:
        self.verify_units(request)
        hashes = {}
        for name, expected in request.unit_sha256.items():
            if expected == "absent":
                continue
            path = self.path("/etc/systemd/system/" + name)
            original = path.read_bytes()
            private_write(backup / name, original)
            updated = original.replace(f"{RELEASE_ROOT}/{PREVIOUS}".encode(), request.release.encode())
            private_write(path, updated, replace=True)
            path.chmod(0o644)
            hashes[name] = file_sha(path)
        return hashes

    def verify_previous_fence(self, request: Request) -> None:
        old = self.path(f"{RELEASE_ROOT}/{PREVIOUS}")
        manifest_path = old / "__release_manifest__.json"
        regular(manifest_path, private=True)
        require(file_sha(manifest_path) == self.previous_manifest, "PREVIOUS_RELEASE_MANIFEST")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        require(manifest.get("commit") == PREVIOUS, "PREVIOUS_RELEASE_SOURCE")
        name = "tools/deploy_core.py"
        regular(old / name)
        require(file_sha(old / name) == manifest.get("files", {}).get(name, {}).get("sha256"), "PREVIOUS_FENCE_CHANGED")
        expected = ast.parse(self.path(request.release).joinpath(name).read_bytes())
        actual = ast.parse((old / name).read_bytes())
        names = {"execute_hermes_core", "skill_writer_lock"}

        def selected(tree: ast.Module) -> dict[str, str]:
            return {
                node.name: ast.dump(node, include_attributes=False)
                for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name in names
            }

        require(set(selected(actual)) == names and selected(actual) == selected(expected), "UNREVIEWED_PREVIOUS_FENCE")
        for tree in (actual, expected):
            constants = {
                node.targets[0].id: ast.literal_eval(node.value)
                for node in tree.body
                if isinstance(node, ast.Assign)
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in {"MAINTENANCE", "SKILL_WRITER_LOCK"}
            }
            require(
                constants
                == {
                    "MAINTENANCE": "/www/wwwroot/p-acme/core-maintenance.flag",
                    "SKILL_WRITER_LOCK": "/root/zhiming-core-secrets/core-skill-writer.lock",
                },
                "FENCE_PATHS",
            )


def wrapper(request: Request) -> bytes:
    config = {
        "commit": TARGET,
        "release_dir": request.release,
        "env_file": list(ENV_FILES),
    }
    text = '''"""Pinned Core wrapper; no legacy fallback or process-wide Hermes restart."""
import json,sys
from types import SimpleNamespace
def main():
    config=json.loads(CONFIG)
    sys.path.insert(0,config['release_dir'])
    from tools.deploy_core import execute_hermes_core
    execute_hermes_core(SimpleNamespace(**config),sys.argv[1:])
if __name__=='__main__':
    try: main()
    except Exception: sys.stderr.write('CORE_INCREMENTAL_CONFIGURATION_ERROR\\n'); raise SystemExit(78)
'''
    return text.replace("CONFIG", repr(json.dumps(config, sort_keys=True)), 1).encode()


def retired_stub() -> bytes:
    return (
        "import sys\nsys.stderr.write('LEGACY_SKILL_RETIRED: 旧入口已退役，请使用本目录 core_consultation.py；"
        "禁止旧事实写入或第二次解释。\\n')\nraise SystemExit(64)\n"
    ).encode()


def previous_wrapper() -> bytes:
    config = {
        "commit": PREVIOUS,
        "release_dir": f"{RELEASE_ROOT}/{PREVIOUS}",
        "env_file": list(ENV_FILES),
    }
    text = '''"""Fixed Core entrypoint; runtime secrets stay in protected env files."""
import json,os,sys
from types import SimpleNamespace
def main():
 try:
  config=json.loads(CONFIG_JSON)
  sys.path.insert(0,config['release_dir'])
  from tools.deploy_core import execute_hermes_core
  args=SimpleNamespace(**config)
  execute_hermes_core(args,sys.argv[1:])
 except Exception:
  sys.stderr.write(ERROR_MESSAGE)
  raise SystemExit(78)
if __name__=='__main__':main()
'''
    text = text.replace(
        "ERROR_MESSAGE",
        repr("CORE_SKILL_CONFIGURATION_ERROR: protected configuration or fixed release failed; no legacy fallback.\n"),
    )
    return text.replace("CONFIG_JSON", repr(json.dumps(config, sort_keys=True))).encode()


def verify_skill(files: HostFiles, request: Request) -> dict[str, Any]:
    root = files.path(SKILL)
    path = root / "__core_skill_manifest__.json"
    regular(path, private=True)
    require(file_sha(path) == request.skill_manifest_sha256, "HERMES_MANIFEST_CHANGED")
    old = json.loads(path.read_text(encoding="utf-8"))
    require(old.get("schema") == "core3-hermes-skill-v1" and old.get("commit") == PREVIOUS, "HERMES_PREVIOUS_SOURCE")
    require(old.get("release_dir") == f"{RELEASE_ROOT}/{PREVIOUS}", "HERMES_PREVIOUS_RELEASE")
    require(old.get("env_files") == list(ENV_FILES), "HERMES_ENV_ORDER")
    rows = old.get("files", {})
    require({"SKILL.md", "core_consultation.py"} <= set(rows), "HERMES_FILE_SET")
    require(
        {p.name for p in root.glob("*.py")} == {name for name in rows if name.endswith(".py")},
        "UNKNOWN_SKILL_CODE",
    )
    for name, record in rows.items():
        require(name == "SKILL.md" or name.endswith(".py") and Path(name).name == name, "HERMES_FILE_NAME")
        item = root / name
        regular(item, private=True)
        require(file_sha(item) == record.get("sha256"), "HERMES_FILE_CHANGED")
        if name not in {"SKILL.md", "core_consultation.py"}:
            require(item.read_bytes() == retired_stub(), "LEGACY_ENTRY_NOT_RETIRED")
    require((root / "core_consultation.py").read_bytes() == previous_wrapper(), "UNREVIEWED_HERMES_WRAPPER")
    original = old.get("backup_path", "")
    require(
        isinstance(original, str)
        and original.startswith("/root/zhiming-core-backups/")
        and PurePosixPath(original).name == "hermes-skill",
        "ORIGINAL_SKILL_BACKUP_PATH",
    )
    original_manifest = files.path(original) / "__hermes_skill_backup__.json"
    regular(original_manifest, private=True)
    require(file_sha(original_manifest) == old.get("backup_manifest_sha256"), "ORIGINAL_SKILL_BACKUP_CHANGED")
    saved = json.loads(original_manifest.read_text(encoding="utf-8"))
    require(
        saved.get("schema") == "core3-hermes-skill-backup-v1" and isinstance(saved.get("files"), dict),
        "ORIGINAL_SKILL_BACKUP_SCHEMA",
    )
    for name, record in saved["files"].items():
        require(Path(name).name == name and name not in {".", ".."}, "ORIGINAL_SKILL_BACKUP_MEMBER")
        item = original_manifest.parent / name
        regular(item, private=True)
        require(file_sha(item) == record.get("sha256"), "ORIGINAL_SKILL_BACKUP_CHANGED")
    return old


def retarget_skill(files: HostFiles, request: Request, backup: Path) -> dict[str, Any]:
    require(request.scope == "live", "HERMES_LIVE_ONLY")
    root = files.path(SKILL)
    path = root / "__core_skill_manifest__.json"
    old = verify_skill(files, request)
    rows = old["files"]
    names = set(rows)
    for name in rows:
        item = root / name
        private_write(backup / name, item.read_bytes())
    private_write(backup / "__core_skill_manifest__.json", path.read_bytes())
    new_files = {
        "core_consultation.py": wrapper(request),
        "SKILL.md": files.path(request.release).joinpath("hermes/SKILL.md").read_bytes(),
    }
    for name, content in new_files.items():
        private_write(root / name, content, replace=True)
        rows[name] = {"sha256": hashlib.sha256(content).hexdigest()}
    new = {
        "schema": "core3-hermes-skill-incremental-v1",
        "commit": TARGET,
        "previous_commit": PREVIOUS,
        "release_dir": request.release,
        "env_files": list(ENV_FILES),
        "files": rows,
        "original_retirement_backup": {key: old.get(key) for key in ("backup_path", "backup_manifest_sha256")},
        "previous_manifest_sha256": request.skill_manifest_sha256,
        "source_manifest_sha256": request.manifest_sha256,
        "retarget_backup": str(backup),
        "original_skill_manifest_preserved": True,
    }
    private_write(path, (json.dumps(new, sort_keys=True) + "\n").encode(), replace=True)
    require(all(file_sha(root / name) == record["sha256"] for name, record in rows.items()), "HERMES_POST_VERIFY")
    return {
        "previous": PREVIOUS,
        "target": TARGET,
        "manifest_sha256": file_sha(path),
        "retired_files": len(names) - 2,
        "hermes_restarted": False,
        "hermes_retired_preserved": True,
        "receipt_sha256": digest(new),
    }
