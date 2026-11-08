"""R45/R48 sender for production steps: explicit key path, raw UTF-8/LF bytes, no retries."""

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "private/fr-prod-501d95670be144a3"
KEY = "C:/Users/Administrator/.ssh/gto_deploy_key"
BEIJING = timezone(timedelta(hours=8))
CANDIDATE = "bf6e0bbc720b85510d757b17d4ccd74ff60687bb"
OPERATION = "501d95670be144a3"

# Order gate: before sending a step, every requirement must be met by at least one of its alternatives.
# An alternative is met by a local receipt <name>.json or <name>.<attempt>.json with exit_code 0
# (for a -status step the saved log must also end with STEP_OK). Alternatives follow the R67
# continuation table, so a reviewed continuation can stand in for the step it continues.
PREREQUISITES = {
    "p02-admin": [("p01-readonly",)],
    "p03a-extract": [("p01-readonly",), ("p02-admin",)],
    "p03b-install-start": [("p03a-extract",)],
    "p03c-install-status": [("p03b-install-start",)],
    "p03d-tokenizer": [("p03c-install-status",)],
    "p04b-d1-maintenance": [
        ("p01-readonly",), ("p02-admin",), ("p03a-extract",), ("p03d-tokenizer",),
        ("p04a-precheck",), ("p04a-readonly",),
    ],
    "p04c-gate-503": [("p04b-d1-maintenance",)],
    "p05-context": [("p04c-gate-503",)],
    "p06a-d2-start": [("p05-context",)],
    "p06b-d2-status": [("p06a-d2-start",)],
    "p07a-d3-start": [("p06b-d2-status", "c-d2-mid-status", "c-d2-tail-status")],
    "p07b-d3-status": [("p07a-d3-start",)],
    "p08a-d4-start": [("p07b-d3-status", "c-d3-tail-status")],
    "p08b-d4-status": [("p08a-d4-start",)],
    # D4 tail collision: the receipt is written, then c-wait-zero closes the gap (R67 table).
    "p09-d5-exchange": [("p08a-d4-start",), ("p08b-d4-status", "c-wait-zero")],
    "p09c-writer-harden": [("p09-d5-exchange", "c-d5-tail-status")],
    "p10-d5-assets": [("p09c-writer-harden",)],
    "p11-d6-preopen": [("p10-d5-assets",)],
    "p12-d6-writer": [("p11-d6-preopen",)],
    # D6 tail collision: writer-preopen.json is written, then c-wait-zero closes the gap (R67 table).
    "p13-d7-open": [("p11-d6-preopen",), ("p12-d6-writer", "c-wait-zero")],
    "p14-d7-timer-state": [("p13-d7-open",)],
    "p14b-d7-timer-start": [("p13-d7-open",), ("p14-d7-timer-state",)],
    "p15-final-readonly": [("p13-d7-open",)],
    "r02b-writer-restore": [("r02-rollback-files",)],
    "r03-rollback-verify": [("r02b-writer-restore",)],
    "r04-reopen-after-rollback": [("r03-rollback-verify",)],
    "r04-reopen-timer-held": [("r03-rollback-verify",)],
}
# Steps outside the time window check: rollback, continuation, post-open stop-loss and the read-only probe.
WINDOW_EXEMPT_PREFIXES = ("r0", "c-")
WINDOW_EXEMPT = {"p16-postopen-close", "p04a-readonly"}
# Once p13 has opened the site, the follow-up steps must still be sendable after the window ends.
AFTER_OPEN_EXEMPT = {"p14-d7-timer-state", "p14b-d7-timer-start", "p15-final-readonly"}


def readonly_report(log):
    """The JSON report p04a-readonly prints after the ssh banner; None when it cannot be found."""
    text = log.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines(keepends=True)
    offset = 0
    for line in lines:
        if line.rstrip("\r\n") == "{":
            try:
                value, _ = json.JSONDecoder().raw_decode(text[offset:])
            except ValueError:
                return None
            return value if isinstance(value, dict) else None
        offset += len(line)
    return None


def receipts_ok(step):
    good = []
    for path in [ROOT / (step + ".json"), *sorted(ROOT.glob(step + ".*.json"))]:
        if not path.is_file():
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("step") != step or record.get("exit_code") != 0:
            continue
        if record.get("candidate") != CANDIDATE or record.get("operation") != OPERATION:
            continue
        log = path.with_suffix(".log")
        if step.endswith("-status"):
            if not log.is_file():
                continue
            lines = [x.strip() for x in log.read_text(encoding="utf-8", errors="replace").splitlines() if x.strip()]
            if not lines or lines[-1] != "STEP_OK":
                continue
        good.append((record.get("finished_at", ""), log))
    if not good:
        return False
    if step == "p04a-readonly":
        # exit 0 is not enough: the latest successful report must list no other problems.
        report = readonly_report(max(good)[1]) if max(good)[1].is_file() else None
        return bool(report) and "other_problems" in report and report["other_problems"] == []
    return True


def window_gate(step):
    gate = ROOT / "window-go.json"
    if not gate.is_file():
        raise SystemExit("No window-go.json: production steps are closed")
    window = json.loads(gate.read_text(encoding="utf-8"))
    if window.get("candidate") != CANDIDATE or window.get("operation") != OPERATION:
        raise SystemExit("window-go.json names another candidate or operation")
    if step.startswith(WINDOW_EXEMPT_PREFIXES) or step in WINDOW_EXEMPT:
        return
    if step in AFTER_OPEN_EXEMPT and receipts_ok("p13-d7-open"):
        return
    not_before = datetime.fromisoformat(window["not_before"])
    latest_end = datetime.fromisoformat(window["latest_end"])
    if not_before.tzinfo is None or latest_end.tzinfo is None:
        raise SystemExit("window-go.json times need an explicit +08:00 offset")
    now = datetime.now(BEIJING)
    if not not_before <= now <= latest_end:
        raise SystemExit(f"Outside the 31号 window ({window['not_before']} .. {window['latest_end']}); now {now.isoformat()}")


name, attempt = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ""
# R71: this read-only step has its own gate; the brain writes it after the user approves.
if name == "p04a-readonly":
    if not (ROOT / "readonly-order.json").is_file():
        raise SystemExit("No readonly-order.json: the read-only check is closed")
# The gate file is written only after a fresh 31号 window and the user's "开始首发生产".
else:
    window_gate(name)
# R59: reopening after a rollback is never part of the default flow.
if name.startswith("r04-") and not (ROOT / "reopen-order.json").is_file():
    raise SystemExit("No reopen-order.json: r04 needs an explicit order for this occasion")
# Report timer restore and post-open stop-loss each need their own per-occasion order.
if name == "p14b-d7-timer-start" and not (ROOT / "timer-order.json").is_file():
    raise SystemExit("No timer-order.json: the report timer stays stopped")
if name == "p16-postopen-close" and not (ROOT / "postopen-close-order.json").is_file():
    raise SystemExit("No postopen-close-order.json: post-open stop-loss needs an explicit order")
for alternatives in PREREQUISITES.get(name, []):
    if not any(receipts_ok(step) for step in alternatives):
        raise SystemExit(f"{name} needs a successful receipt of {' or '.join(alternatives)} first")
# R67: a continuation needs an order naming the script; its -status script only follows a sent order.
base = name.removesuffix("-status")
order = ROOT / "continue-order.json"
if name.startswith("c-"):
    if name.endswith("-status"):
        if not list(ROOT.glob(f"continue-order.used-{base}-*.json")):
            raise SystemExit("No used continue-order for " + base)
    elif not order.is_file() or json.loads(order.read_text(encoding="utf-8")).get("script") != name:
        raise SystemExit("No continue-order.json for " + name)
raw = (ROOT / (name + ".sh")).read_bytes()
assert hashlib.sha256(raw).hexdigest() == json.loads((ROOT / "steps.json").read_text())[name]["sha256"]
assert b"\r" not in raw and raw.startswith(b"set -euo pipefail\n")
stem = name + ("." + attempt if attempt else "")
assert not (ROOT / (stem + ".json")).exists()
if name.startswith("c-") and not name.endswith("-status"):
    stamp = datetime.now(BEIJING).strftime("%Y%m%dT%H%M%S")
    order.rename(ROOT / f"continue-order.used-{base}-{stamp}.json")
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
              candidate=CANDIDATE, operation=OPERATION, key_path_only=KEY)
(ROOT / (stem + ".json")).write_text(json.dumps(record, indent=2), encoding="utf-8")
print(json.dumps(record))
raise SystemExit(result.returncode)
