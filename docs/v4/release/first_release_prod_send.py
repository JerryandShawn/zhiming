"""R45/R48 sender for production steps: explicit key path, raw UTF-8/LF bytes, no retries."""

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "private/fr-prod-1a131275da9dc8d6"
KEY = "C:/Users/Administrator/.ssh/gto_deploy_key"
BEIJING = timezone(timedelta(hours=8))

name, attempt = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ""
# The gate file is written only after a fresh 31号 window and the user's "开始首发生产".
if not (ROOT / "window-go.json").is_file():
    raise SystemExit("No window-go.json: production steps are closed")
raw = (ROOT / (name + ".sh")).read_bytes()
assert hashlib.sha256(raw).hexdigest() == json.loads((ROOT / "steps.json").read_text())[name]["sha256"]
assert b"\r" not in raw and raw.startswith(b"set -euo pipefail\n")
stem = name + ("." + attempt if attempt else "")
assert not (ROOT / (stem + ".json")).exists()
started = datetime.now(BEIJING).isoformat()
result = subprocess.run(
    ["ssh", "-i", KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=30", "-o", "ServerAliveInterval=15",
     "-o", "ServerAliveCountMax=4", "root@1.14.59.242", "bash -s"],
    input=raw, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
)
(ROOT / (stem + ".log")).write_bytes(result.stdout)
record = dict(step=name, attempt=attempt, started_at=started, finished_at=datetime.now(BEIJING).isoformat(),
              exit_code=result.returncode, script_sha256=hashlib.sha256(raw).hexdigest(),
              stdin="raw UTF8 LF bytes; no text mode; CR absent",
              candidate="e578e2d5d83dcf3b63c74af6e1b9f1a4c86453bd", operation="1a131275da9dc8d6", key_path_only=KEY)
(ROOT / (stem + ".json")).write_text(json.dumps(record, indent=2), encoding="utf-8")
print(json.dumps(record))
raise SystemExit(result.returncode)
