"""R51: split the reviewed production runbook into step scripts without changing its content.

Every piece of every runbook bash block lands in exactly one step, in order; the only additions are
the shared header (same lines as D0/stage), the start_step/check_step helpers and the read-only
prechecks listed in ADDED. Generating never connects to the server.
"""

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUNBOOK = ROOT / "docs/v4/release/first_release_prod_runbook.md"
RUNBOOK_SHA256 = "17ef7a87b44493801ee8f45308ef368a2bf6d0cf8956e4fd1166028786bb6f3c"
OUT = ROOT / "private/fr-prod-1a131275da9dc8d6"
GIT_BASH = "C:/Program Files/Git/bin/bash.exe"
OLD_DEPLOY_CORE_SHA256 = "e5b98588968301cd89e61a54433efe62e8cbb3f57ac2803b6211e2f7f8e65bd8"

raw = RUNBOOK.read_bytes()
assert hashlib.sha256(raw).hexdigest() == RUNBOOK_SHA256, "runbook changed; re-review before regenerating"
assert b"\r" not in raw
blocks = re.findall(r"```bash\n(.*?)```", raw.decode("utf-8"), re.S)
assert len(blocks) == 17


def between(text, start, end):
    """Exact slice from the line starting with start through the line starting with end."""
    lines = text.splitlines(keepends=True)
    first = next(i for i, line in enumerate(lines) if line.startswith(start))
    last = next(i for i, line in enumerate(lines) if i >= first and line.startswith(end))
    return "".join(lines[first : last + 1])


one = blocks[0]
HEADER = (
    between(one, "set -euo pipefail", 'test "$(id -u)" = 0')
    + between(one, "# v49:", "done\n")
    + """FR_STAGE_PY=/root/zhiming-core-fr-stage/venvs/$FR_SHA/core/bin/python
FR_PY=$FR_RELEASE/venv/core/bin/python
FR_TOKENIZER=/root/zhiming-core-fr-stage/tokenizer/$FR_SHA
start_step() {
  local name="$1"; shift
  [[ "$name" =~ ^[a-z0-9-]+$ ]]
  for ext in log pid exit; do ! test -e "$FR_OP/$name.$ext"; done
  nohup /bin/bash -c 'set -C; out=$1; shift; "$@"; rc=$?; printf "%s\\n" "$rc" > "$out"; exit "$rc"' \
fr-step "$FR_OP/$name.exit" "$@" > "$FR_OP/$name.log" 2>&1 < /dev/null &
  printf '%s\\n' "$!" > "$FR_OP/$name.pid"
}
check_step() {
  local name="$1"
  test -f "$FR_OP/$name.exit"
  test "$(cat "$FR_OP/$name.exit")" = 0
}
step_status() {
  local name="$1"
  if test -f "$FR_OP/$name.exit"; then cat "$FR_OP/$name.log"; check_step "$name"; echo STEP_OK; else echo STEP_RUNNING; fi
}
"""
)
assert HEADER.startswith("set -euo pipefail\n") and "test -d" not in HEADER and "awk" not in HEADER

three = blocks[2]
extract = three[: three.index('python3.11 -m venv "$FR_RELEASE/venv/core"')]
install = three[len(extract) : three.index("FR_PY=$FR_RELEASE/venv/core/bin/python")]
verify = three[len(extract) + len(install) :]
assert extract + install + verify == three


def background(name, block):
    match = re.fullmatch(r"\"\$FR_PY\" -I - \"\$FR_OP\" <<'PY'\n(.*)\nPY\n", block, re.S)
    assert match, name
    return (
        f"cat > \"$FR_OP/{name}.py\" <<'PY'\n{match.group(1)}\nPY\n"
        f'chmod 600 "$FR_OP/{name}.py"\n'
        f'start_step {name} "$FR_PY" -I "$FR_OP/{name}.py" "$FR_OP"\n'
    )


PRECHECK = f"""test "$(systemctl show -p WorkingDirectory --value mingjingtai.service)" = "$FR_OLD_RELEASE"
systemctl show -p ExecStart --value mingjingtai.service | grep -Fq "$FR_OLD_RELEASE"
grep -Fq "$FR_OLD" /root/.hermes/skills/zhiming/core_consultation.py
grep -Fq 'from tools.deploy_core import execute_hermes_core' /root/.hermes/skills/zhiming/core_consultation.py
test "$(sha256sum "$FR_OLD_RELEASE/tools/deploy_core.py" | cut -d ' ' -f 1)" = {OLD_DEPLOY_CORE_SHA256}
echo 'live is 7dbc951; old Hermes wrapper verified read-only'
"""
GATE_503 = """for path in / /api/health /api/state; do
  code="$(curl -sk -o /dev/null -w '%{http_code}' --resolve p.jerrymeng.asia:443:127.0.0.1 "https://p.jerrymeng.asia$path")"
  echo "$path $code"
  test "$code" = 503
done
echo "old release processes: $(pgrep -f -- "$FR_OLD_RELEASE" | wc -l)"
"""
FINAL = """for unit in mingjingtai.service zhiming-core-feishu.service zhiming-core-reports.service zhiming-core-reports.timer; do
  systemctl show "$unit" -p ActiveState -p UnitFileState -p MainPID -p ExecStart -p WorkingDirectory -p NeedDaemonReload
done
sha256sum /root/.hermes/skills/zhiming/core_consultation.py
"""

# (step, shell after the header, [(runbook block number, piece)]); pieces must rebuild every block.
STEPS = [
    ("p01-readonly", None, [(1, one)]),
    ("p02-admin", None, [(2, blocks[1])]),
    ("p03a-extract", None, [(3, extract)]),
    ("p03b-install-start", "install", [(3, install)]),
    ("p03c-install-status", "status:install", []),
    ("p03d-tokenizer", 'check_step install\n', [(3, verify)]),
    ("p04a-precheck", PRECHECK, []),
    ("p04b-d1-maintenance", None, [(4, blocks[3])]),
    ("p04c-gate-503", GATE_503, []),
    ("p05-context", None, [(5, blocks[4])]),
    ("p06a-d2-start", "bg:d2-backup", [(6, blocks[5])]),
    ("p06b-d2-status", "status:d2-backup", []),
    ("p07a-d3-start", "bg:d3-restore", [(7, blocks[6])]),
    ("p07b-d3-status", "status:d3-restore", []),
    ("p08a-d4-start", "bg:d4-migrate", [(8, blocks[7])]),
    ("p08b-d4-status", "status:d4-migrate", []),
    ("p09-d5-exchange", None, [(9, blocks[8])]),
    ("p10-d5-assets", None, [(10, blocks[9])]),
    ("p11-d6-preopen", None, [(11, blocks[10])]),
    ("p12-d6-writer", None, [(12, blocks[11])]),
    ("p13-d7-open", None, [(13, blocks[12])]),
    ("p14-d7-timer-state", None, [(14, blocks[13])]),
    ("p15-final-readonly", FINAL, []),
    ("r01-rollback-database", None, [(15, blocks[14])]),
    ("r02-rollback-files", None, [(16, blocks[15])]),
    ("r03-rollback-verify", None, [(17, blocks[16])]),
]
ADDED = {
    "p04a-precheck": "只读：确认线上仍是 7dbc951（v72）、旧 wrapper 符合 D1 前提",
    "p04c-gate-503": "只读：D1 的公网维护 503、遗留进程数",
    "p15-final-readonly": "只读：D8 最终核对",
}

OUT.mkdir(exist_ok=True)
rebuilt = {}
manifest = {}
for name, extra, pieces in STEPS:
    for number, piece in pieces:
        rebuilt[number] = rebuilt.get(number, "") + piece
    if name == "p01-readonly":
        body = one
    elif extra == "install":
        body = (
            "cat > \"$FR_OP/install.sh\" <<SH\nset -euo pipefail\nFR_RELEASE=$FR_RELEASE\nSH\n"
            f"cat >> \"$FR_OP/install.sh\" <<'SH'\n{install}SH\n"
            'chmod 600 "$FR_OP/install.sh"\nstart_step install /bin/bash "$FR_OP/install.sh"\n'
        )
        body = HEADER + body
    elif extra and extra.startswith("status:"):
        body = HEADER + f"step_status {extra.split(':')[1]}\n"
    elif extra and extra.startswith("bg:"):
        body = HEADER + background(extra.split(":")[1], pieces[0][1])
    else:
        body = HEADER + (extra or "") + "".join(piece for _, piece in pieces)
    data = body.encode("utf-8")
    assert b"\r" not in data and data.startswith(b"set -euo pipefail\n")
    path = OUT / (name + ".sh")
    path.write_bytes(data)
    check = subprocess.run([GIT_BASH, "-n", str(path)], capture_output=True, text=True)
    assert check.returncode == 0, (name, check.stderr)
    manifest[name] = {
        "sha256": hashlib.sha256(data).hexdigest(),
        "runbook_blocks": sorted({number for number, _ in pieces}),
    }
for number, block in enumerate(blocks, 1):
    assert rebuilt[number] == block, number
for extra, _ in ((name, 0) for name, value, _ in STEPS if value and value.startswith("bg:")):
    start = (OUT / (extra + ".sh")).read_text(encoding="utf-8")
    number = manifest[extra]["runbook_blocks"][0]
    body = re.fullmatch(r"\"\$FR_PY\" -I - \"\$FR_OP\" <<'PY'\n(.*)\nPY\n", blocks[number - 1], re.S).group(1)
    assert body in start, extra
(OUT / "steps.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")

rows = [
    "# 首发生产分步脚本（R51）",
    "",
    f"由 `first_release_prod_steps_gen.py` 从执行单（sha256 `{RUNBOOK_SHA256}`）生成，脚本在 "
    "`private/fr-prod-1a131275da9dc8d6/`。17 个 bash 块逐字节拼回与执行单一致，顺序不变；"
    "pip 和 D2–D4 用 start_step/check_step 后台跑（Python 正文逐字不变，只从 stdin 改为落盘后执行）。",
    "",
    "| 步骤 | 执行单块 | 对照 | sha256 前 12 位 |",
    "| --- | --- | --- | --- |",
]
for name, value in manifest.items():
    source = "、".join(str(n) for n in value["runbook_blocks"]) or "—"
    note = ADDED.get(name) or ("后台状态查询" if not value["runbook_blocks"] else "一致")
    rows.append(f"| {name} | {source} | {note} | `{value['sha256'][:12]}` |")
(ROOT / "docs/v4/release/first_release_prod_steps.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
print(len(manifest), "steps; all 17 runbook blocks rebuilt byte for byte")
sys.exit(0)
