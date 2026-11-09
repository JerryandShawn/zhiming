"""A real Linux venv reaches the production entry: linked interpreters are refused, --copies passes.

The 11-08 first release built venv/core with plain `python3.11 -m venv`, whose bin/python* are
symlinks; all four service entries then stopped with LINKED_PATH_REJECTED. Earlier tests used the
test interpreter itself, never a freshly built venv, so the gap stayed hidden. The runbook now uses
`--copies`; this test keeps the entry's link refusal and the runbook command in agreement.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest

from tools import first_release_hermes_entry as entry
from tools.first_release_contracts import RestoreRejected, ordinary

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="production venv layout is Linux-only"
)

DOCUMENT = {
    "schema": "first-release-service-assets-v1",
    "candidate": "a" * 40,
    "workspace": "/root/synthetic-service-workspace",
    "system_identifier": "12345678901234567",
    "database": "synthetic_assets",
    "database_oid": 401,
    "writer": "synthetic_assets_writer",
    "writer_oid": 403,
    "report_owner": "synthetic",
    "env_files": ["/root/synthetic-core.env", "/root/synthetic-member.env"],
    "config_path": "/root/zhiming-core-secrets/synthetic-service-config.json",
    "common_env_path": "/root/zhiming-core-secrets/synthetic-service-common.env",
    "k3_tokenizer_dir": "/root/synthetic-k3-artifacts",
}

# Runs inside the new venv. load_environment is the first step after every interpreter check, so
# reaching it proves the entry accepted the venv interpreter; nothing beyond it is executed.
PROBE = """
import json, sys
from pathlib import Path
root, workspace, extra, document = sys.argv[1], sys.argv[2], json.loads(sys.argv[3]), json.loads(sys.argv[4])
sys.path[:0] = [root]
sys.path.extend(extra)
from tools import first_release_hermes_entry as entry
from tools.first_release_contracts import RestoreRejected
from tools.first_release_service_assets import Assets, LocalProjection
class Reached(Exception):
    pass
def stop(_assets):
    raise Reached
entry.load_environment = stop
projection = LocalProjection(Path(root), Path(sys.executable), Path(workspace))
try:
    entry.run(Assets.parse(document), (), role="web", local_projection=projection)
except RestoreRejected as error:
    print("REJECTED", error)
except Reached:
    print("REACHED_ENVIRONMENT")
"""


def build_venv(target: Path, *, copies: bool) -> Path:
    command = [
        sys.executable,
        "-m",
        "venv",
        "--without-pip",
        *(["--copies"] if copies else []),
        str(target),
    ]
    subprocess.run(command, check=True, capture_output=True, timeout=120)
    return target / "bin/python"


def probe(python: Path, workspace: Path) -> str:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("PYTHON", "PG"))
    }
    extra = [
        path
        for path in {sysconfig.get_paths()["purelib"], sysconfig.get_paths()["platlib"]}
        if path
    ]
    argv = [
        str(entry.ROOT),
        str(workspace),
        json.dumps(sorted(extra)),
        json.dumps(DOCUMENT),
    ]
    result = subprocess.run(
        [str(python), "-I", "-B", "-c", PROBE, *argv],
        env=environment,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    return result.stdout.strip()


def test_runbook_venv_layout_against_real_entry(tmp_path):
    release = tmp_path / "release"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (release / "venv").mkdir(parents=True)
    linked = build_venv(release / "venv/linked", copies=False)
    copied = build_venv(release / "venv/core", copies=True)
    if not linked.is_symlink():
        pytest.skip("this platform's default venv already copies the interpreter")
    for name in ("python", "python3", "python3.11"):
        assert (
            not (copied.parent / name).is_symlink() and (copied.parent / name).is_file()
        )
    with pytest.raises(RestoreRejected, match="^LINKED_PATH_REJECTED$"):
        ordinary(linked)
    ordinary(copied)
    assert probe(linked, workspace) == "REJECTED LINKED_PATH_REJECTED"
    assert probe(copied, workspace) == "REACHED_ENVIRONMENT"
