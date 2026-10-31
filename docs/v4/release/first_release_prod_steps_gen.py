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

# R59: an extra step outside the default flow; the sender needs a separate per-occasion order for it.
REOPEN = r"""test ! -e "$FR_OP/opened.json"
test -f "$FR_OP/rollback-old-runtime.json"
test -f /www/wwwroot/p-acme/core-maintenance.flag
"$FR_PY" -I - "$FR_OP" <<'PY'
import sys
sys.path.insert(0,sys.argv[1]);from context import *
v=read('rollback-old-runtime.json')
assert v['old_sha']=='7dbc951eaffebd3d812169865eaefcde16a00ed9' and v['schema_readonly_verified'] and v['closed']
with admin() as c:
 zero(c,LIVE);allow(c,LIVE,True)
print('R59: live database admission opened behind the public maintenance gate')
PY
systemctl start mingjingtai.service
systemctl is-active --quiet mingjingtai.service
"$FR_PY" -I - "$FR_OP" <<'PY'
import sys,time,urllib.error,urllib.request
sys.path.insert(0,sys.argv[1]);from context import *
env={}
for path in ('/root/.hermes/.env','/root/zhiming-core-secrets/live-runtime.env'):
 env.update(private_env(path))
request=urllib.request.Request('http://127.0.0.1:8787/api/health',headers={'X-Token':env['MINGJING_TOKEN']})
env=None;body=None
for _ in range(30):
 try:
  with urllib.request.urlopen(request,timeout=5) as response:
   assert response.status==200;body=json.load(response);break
 except (urllib.error.URLError,ConnectionError):
  time.sleep(2)
assert body and body['ok'] is True and body['database']=='postgresql' and body['context_version']=='core3.0','R59 health failed; maintenance retained'
print('R59: old web healthy behind the public maintenance gate; token output=0')
PY
"$FR_PY" -I - "$FR_OP/units-before.json" > "$FR_OP/r04-timer-state.txt" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))['zhiming-core-reports.timer']['ActiveState'])
PY
rm /www/wwwroot/p-acme/core-maintenance.flag
systemctl start zhiming-core-feishu.service
systemctl is-active --quiet zhiming-core-feishu.service
if test "$(cat "$FR_OP/r04-timer-state.txt")" = active; then systemctl start zhiming-core-reports.timer; fi
echo "R59: maintenance removed; report timer restored to $(cat "$FR_OP/r04-timer-state.txt")"
"""

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
reopen = (HEADER + REOPEN).encode("utf-8")
assert b"\r" not in reopen
(OUT / "r04-reopen-after-rollback.sh").write_bytes(reopen)
check = subprocess.run([GIT_BASH, "-n", str(OUT / "r04-reopen-after-rollback.sh")], capture_output=True, text=True)
assert check.returncode == 0, check.stderr
timer_lines = [line for line in REOPEN.splitlines(keepends=True) if line.startswith('if test "$(cat "$FR_OP/r04-timer')]
assert len(timer_lines) == 1
held = (HEADER + REOPEN.replace(timer_lines[0], "")).encode("utf-8").replace(b"report timer restored to", b"report timer held; was")
(OUT / "r04-reopen-timer-held.sh").write_bytes(held)
check = subprocess.run([GIT_BASH, "-n", str(OUT / "r04-reopen-timer-held.sh")], capture_output=True, text=True)
assert check.returncode == 0, check.stderr
# R67: continuation scripts, sent only with a per-occasion continue-order.json. The runbook stays unchanged.
RETIRE = """retire_failed() {
  local name="$1" ext stamp
  test -e "$FR_OP/$name.pid" || return 0
  test -f "$FR_OP/$name.exit"
  test "$(cat "$FR_OP/$name.exit")" != 0
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  mkdir -m 700 "$FR_OP/moved-$name-$stamp"
  for ext in py log pid exit; do mv -n "$FR_OP/$name.$ext" "$FR_OP/moved-$name-$stamp/"; done
}
"""
COMMON = r"""import os,subprocess,sys,time
from datetime import datetime,timezone
sys.path.insert(0,sys.argv[1]);from context import *
WAIT_SECONDS=300
RB='zhiming_core_rb_1a131275da9dc8d6';FAILED='zhiming_core_failed_1a131275da9dc8d6'
FLAG=Path('/www/wwwroot/p-acme/core-maintenance.flag')
def exists(c,name):return c.execute('SELECT 1 FROM pg_database WHERE datname=%s',(name,)).fetchone() is not None
def wait_zero(c,name,closed=True):
 end=time.monotonic()+WAIT_SECONDS;seen=set()
 while True:
  rows=c.execute('SELECT a.pid,a.backend_type FROM pg_stat_activity a JOIN pg_database d ON d.oid=a.datid WHERE d.datname=%s',(name,)).fetchall()
  other=[r for r in rows if r['backend_type']!='autovacuum worker']
  assert not other,f'{name}: backend other than autovacuum worker, stopped at once: {other}'
  if not rows:
   if closed:zero(c,name)
   print(f'{name}: 0 connections; autovacuum workers seen while waiting: {len(seen)}',flush=True)
   return
  seen.update(r['pid'] for r in rows)
  assert time.monotonic()<end,f'{name}: not 0 after {WAIT_SECONDS}s; maintenance kept'
  time.sleep(2)
def failed_at(step,script_sha256,tail):
 assert (OP/(step+'.exit')).read_text().strip() not in ('','0')
 assert h(OP/(step+'.py'))==script_sha256
 lines=[x for x in (OP/(step+'.log')).read_text().splitlines() if x.strip(' ^~')]
 assert lines[-len(tail):]==tail,'previous step did not stop at the expected line; stopped'
def move_aside(*names):
 target=OP/('moved-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));target.mkdir(mode=0o700)
 for name in names:os.rename(OP/name,target/name)
 print('moved aside, nothing deleted:',target.name,*names,flush=True)
"""
CONT_PY = {
    "c-wait-zero": r"""with admin() as c:
 names=[x for x in (LIVE,NEW,KEPT,RB,FAILED) if exists(c,x)]
 for name in names:wait_zero(c,name)
print('all operation databases closed with 0 connections:',*names)
""",
    "c-d2-rerun-prep": r"""failed_at('d2-backup',@@D2_SHA@@,@@D2_302@@)
assert (OP/'central-before.json').is_file()
assert not any((OP/x).exists() for x in ('database-before.json','privacy-before.json','schema-before.json','live-before.dump','backup-receipt.json'))
with admin() as c:wait_zero(c,LIVE,closed=False)
move_aside('central-before.json','d2-backup.py','d2-backup.log','d2-backup.pid','d2-backup.exit')
print('line 302 proven; send p06a-d2-start with a new attempt')
""",
    "c-d3-rerun-prep": r"""failed_at('d3-restore',@@D3_SHA@@,@@D3_335@@)
with admin() as c:
 assert not exists(c,NEW)
 wait_zero(c,LIVE)
move_aside('d3-restore.py','d3-restore.log','d3-restore.pid','d3-restore.exit')
print('line 335 proven; send p07a-d3-start with a new attempt')
""",
    "c-d4-rerun-prep": r"""failed_at('d4-migrate',@@D4_SHA@@,@@D4_368@@)
assert not (OP/'migration-receipt.json').exists()
with admin() as c:
 wait_zero(c,LIVE);wait_zero(c,NEW)
move_aside('d4-migrate.py','d4-migrate.log','d4-migrate.pid','d4-migrate.exit')
print('line 368 proven; send p08a-d4-start with a new attempt')
""",
}
CONT_BG = {
    "c-d2-mid": r"""from tools.deploy_core import skill_writer_lock
failed_at('d2-backup',@@D2_SHA@@,@@D2_312@@)
dump=OP/'live-before.dump'
with skill_writer_lock(exclusive=True),admin() as c:
 assert FLAG.is_file()
 assert all((OP/x).is_file() for x in ('central-before.json','database-before.json','privacy-before.json','schema-before.json'))
 assert not dump.exists() and not (OP/'backup-receipt.json').exists()
 snap=read('database-before.json');validate(c,snap);assert capture(c,LIVE)==snap
 wait_zero(c,LIVE)
 assert not c.execute('SELECT 1 FROM pg_database WHERE datname=ANY(%s)',([NEW,KEPT],)).fetchone()
 allow(c,LIVE,True)
 try:
  with dump.open('xb') as out:
   cmd=[pg_program('pg_dump'),'--host='+F['host'],'--port=5432','--username='+F['user'],'--dbname='+LIVE,'--no-password','--format=custom']
   result=subprocess.run(cmd,env=process_environment(DSN),stdout=out,stderr=subprocess.PIPE)
   assert result.returncode==0,'dump failed; keep private diagnostic'
 finally:allow(c,LIVE,False)
 wait_zero(c,LIVE)
 save('backup-receipt.json',{'sha256':h(dump),'source_oid':snap['oid'],'closed':True,'pg_dump_sha256':h(pg_program('pg_dump')),'pg_restore_sha256':h(pg_program('pg_restore'))})
print('D2 continued from line 312: backup captured; live closed')
""",
    "c-d2-tail": r"""from tools.deploy_core import skill_writer_lock
failed_at('d2-backup',@@D2_SHA@@,@@D2_321@@)
dump=OP/'live-before.dump'
with skill_writer_lock(exclusive=True),admin() as c:
 assert FLAG.is_file()
 assert dump.is_file() and dump.stat().st_size>0 and not (OP/'backup-receipt.json').exists()
 snap=read('database-before.json');validate(c,snap);assert capture(c,LIVE)==snap
 wait_zero(c,LIVE)
 assert not c.execute('SELECT 1 FROM pg_database WHERE datname=ANY(%s)',([NEW,KEPT],)).fetchone()
 restore=pg_program('pg_restore')
 listing=subprocess.run([restore,'--list',str(dump)],env={'PATH':'/usr/bin:/bin'},capture_output=True,text=True)
 assert listing.returncode==0
 toc=listing.stdout.splitlines()
 assert any(x.split()==[';','dbname:',LIVE] for x in toc)
 assert any(' TABLE DATA mingjing_core schema_migrations ' in x for x in toc)
 assert subprocess.run([restore,'--file=/dev/null',str(dump)],env={'PATH':'/usr/bin:/bin'},capture_output=True).returncode==0
 save('backup-receipt.json',{'sha256':h(dump),'source_oid':snap['oid'],'closed':True,'pg_dump_sha256':h(pg_program('pg_dump')),'pg_restore_sha256':h(pg_program('pg_restore'))})
print('D2 tail: line 321 proven, dump listed and read in full; live closed')
""",
    "c-d3-tail": r"""from tools.deploy_core import export_withdrawals
failed_at('d3-restore',@@D3_SHA@@,@@D3_349@@)
with admin() as c:
 assert not (OP/'restore-verified.json').exists()
 wait_zero(c,LIVE);wait_zero(c,NEW)
 snap=read('database-before.json');validate(c,snap);assert capture(c,LIVE)==snap
 assert not exists(c,KEPT)
 new=capture(c,NEW);assert new['oid']!=snap['oid'] and semantic(new)==semantic(snap)
 assert h(OP/'live-before.dump')==read('backup-receipt.json')['sha256']
 assert h(pg_program('pg_restore'))==read('backup-receipt.json')['pg_restore_sha256']
 allow(c,NEW,True)
 try:
  r=repo(NEW,True)
  try:
   check_queue(r);assert export_withdrawals(r)==read('privacy-before.json')
   with r.connection() as db:assert [dict(x) for x in db.execute('SELECT version,checksum FROM mingjing_core.schema_migrations ORDER BY version')]==read('schema-before.json')['rows']
  finally:r.close()
 finally:allow(c,NEW,False)
 time.sleep(2)  # our own closed pool connection must have left before the strict wait looks
 wait_zero(c,NEW)
 assert capture(c,NEW)['oid']==new['oid']
 save('restore-verified.json',{'oid':new['oid'],'schema_before_verified':True,'privacy_equal':True})
print('D3 tail: line 349 proven; new database re-verified and closed')
""",
    "c-d5-tail": r"""with admin() as c:
 assert not (OP/'exchange-receipt.json').exists()
 snap=read('database-before.json');validate(c,snap)
 assert read('migration-receipt.json')['privacy_equal']
 assert not exists(c,NEW)
 live=capture(c,LIVE);kept=capture(c,KEPT)
 assert live['oid']==read('restore-verified.json')['oid'] and kept['oid']==snap['oid']
 assert semantic(live)==semantic(snap) and semantic(kept)==semantic(snap)
 wait_zero(c,LIVE);wait_zero(c,KEPT)
 save('exchange-receipt.json',{'old_oid':snap['oid'],'new_oid':live['oid'],'kept_database':KEPT,'admission_opened':False})
print('D5 tail: exchange proven from database state; receipt written; nothing renamed or reapplied')
""",
    "c-r1-after-restore": r"""from tools.deploy_core import skill_writer_lock,export_withdrawals
assert not (OP/'opened.json').exists() and (OP/'exchange-receipt.json').is_file()
assert not (OP/'rollback-database.json').exists()
with skill_writer_lock(exclusive=True),admin() as c:
 snap=read('database-before.json');validate(c,snap)
 assert not exists(c,FAILED)
 live=capture(c,LIVE);rb=capture(c,RB)
 assert live['oid']==read('exchange-receipt.json')['new_oid'] and rb['oid'] not in (live['oid'],snap['oid'])
 assert semantic(rb)==semantic(snap)
 wait_zero(c,LIVE);wait_zero(c,RB)
 allow(c,RB,True)
 try:
  r=repo(RB,True)
  try:
   assert export_withdrawals(r)==read('privacy-before.json')
   with r.connection() as db:assert [dict(x) for x in db.execute('SELECT version,checksum FROM mingjing_core.schema_migrations ORDER BY version')]==read('schema-before.json')['rows']
  finally:r.close()
 finally:allow(c,RB,False)
 time.sleep(2)  # our own closed pool connection must have left before the strict wait looks
 wait_zero(c,RB);wait_zero(c,LIVE)
 with c.transaction():
  c.execute("SET LOCAL lock_timeout='2s'")
  c.execute(sql.SQL('ALTER DATABASE {} RENAME TO {}').format(sql.Identifier(LIVE),sql.Identifier(FAILED)))
  c.execute(sql.SQL('ALTER DATABASE {} RENAME TO {}').format(sql.Identifier(RB),sql.Identifier(LIVE)))
  apply_metadata(c,LIVE,snap)
 save('rollback-database.json',{'restored_old_schema':True,'failed_database':FAILED,'new_live_oid':capture(c,LIVE)['oid'],'closed':True})
print('R1 continued after line 613: old schema exchanged; failed database retained')
""",
}


def heredoc(number):
    return re.fullmatch(r"\"\$FR_PY\" -I - \"\$FR_OP\" <<'PY'\n(.*)\nPY\n", blocks[number - 1], re.S).group(1) + "\n"


def line_of(text, source):
    found = [i for i, line in enumerate(text.splitlines(), 1) if line.strip() == source]
    assert len(found) == 1, source
    return found[0]


context_text = re.search(r"<<'PY'\n(.*?)\nPY\n", blocks[4], re.S).group(1)
ZERO_ASSERT = "assert r and not r['datallowconn'] and r['n']==0"
OP_PATH = "/root/zhiming-core-backups/first-release-1a131275da9dc8d6"


def zero_tail(step, number, source):
    return [
        f'  File "{OP_PATH}/{step}.py", line {line_of(heredoc(number), source)}, in <module>',
        f"    {source}",
        f'  File "{OP_PATH}/context.py", line {line_of(context_text, ZERO_ASSERT)}, in zero',
        f"    {ZERO_ASSERT}",
        "AssertionError",
    ]


D2_302 = next(line.strip() for line in heredoc(6).splitlines() if line.strip().startswith("assert db.execute("))
FILLS = {
    "@@D2_SHA@@": repr(hashlib.sha256(heredoc(6).encode("utf-8")).hexdigest()),
    "@@D3_SHA@@": repr(hashlib.sha256(heredoc(7).encode("utf-8")).hexdigest()),
    "@@D4_SHA@@": repr(hashlib.sha256(heredoc(8).encode("utf-8")).hexdigest()),
    "@@D2_302@@": repr(
        [f'  File "{OP_PATH}/d2-backup.py", line {line_of(heredoc(6), D2_302)}, in <module>', f"    {D2_302}", "AssertionError"]
    ),
    "@@D2_312@@": repr(zero_tail("d2-backup", 6, "allow(c,LIVE,False);zero(c,LIVE)")),
    "@@D2_321@@": repr(zero_tail("d2-backup", 6, "zero(c,LIVE)")),
    "@@D3_335@@": repr(zero_tail("d3-restore", 7, "zero(c,LIVE);snap=read('database-before.json');validate(c,snap)")),
    "@@D3_349@@": repr(zero_tail("d3-restore", 7, "allow(c,NEW,False);zero(c,NEW)")),
    "@@D4_368@@": repr(zero_tail("d4-migrate", 8, "zero(c,LIVE);zero(c,NEW);allow(c,NEW,True)")),
}


def filled(text):
    for key, value in FILLS.items():
        text = text.replace(key, value)
    assert "@@" not in text
    return text


cont_scripts = {}
for name, value in CONT_PY.items():
    cont_scripts[name] = HEADER + f"\"$FR_PY\" -I - \"$FR_OP\" <<'PY'\n{COMMON}{filled(value)}PY\n"
for name, value in CONT_BG.items():
    cont_scripts[name + "-start"] = (
        HEADER
        + RETIRE
        + f"retire_failed {name}\n"
        + f"cat > \"$FR_OP/{name}.py\" <<'PY'\n{COMMON}{filled(value)}PY\n"
        + f'chmod 600 "$FR_OP/{name}.py"\n'
        + f'start_step {name} "$FR_PY" -I "$FR_OP/{name}.py" "$FR_OP"\n'
    )
    cont_scripts[name + "-status"] = HEADER + f"step_status {name}\n"
cont_listing = {}
for name, text in cont_scripts.items():
    data = text.encode("utf-8")
    assert b"\r" not in data and data.startswith(b"set -euo pipefail\n")
    (OUT / (name + ".sh")).write_bytes(data)
    check = subprocess.run([GIT_BASH, "-n", str(OUT / (name + ".sh"))], capture_output=True, text=True)
    assert check.returncode == 0, (name, check.stderr)
    cont_listing[name] = {"sha256": hashlib.sha256(data).hexdigest(), "runbook_blocks": []}

listing = {
    **manifest,
    "r04-reopen-after-rollback": {"sha256": hashlib.sha256(reopen).hexdigest(), "runbook_blocks": []},
    "r04-reopen-timer-held": {"sha256": hashlib.sha256(held).hexdigest(), "runbook_blocks": []},
    **cont_listing,
}
(OUT / "steps.json").write_text(json.dumps(listing, indent=1), encoding="utf-8")

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
rows += [
    "",
    "## 附录：回滚后重新开门（R59，不在默认流程）",
    "",
    "`r04-reopen-after-rollback.sh`，sha256 `" + hashlib.sha256(reopen).hexdigest() + "`。不改执行单。"
    "只有用户或大脑当次明确下令才执行：发送脚本另外要求 `reopen-order.json`，默认流程不会带上它。"
    "顺序：r03 通过 → 开库连接 → 启动 7dbc951 Web → 门内健康检查 → 读 timer 原状态 → 去维护标记 → 启动飞书并确认 active → timer 按原状态恢复。"
    "飞书走外连长连接，不经过 nginx，维护门挡不住，所以和 D7 一样在去维护标记之后才启动。"
    "下这个令同时表示接受到期报告恢复投递；不接受就改用 `r04-reopen-timer-held.sh`（sha256 `"
    + hashlib.sha256(held).hexdigest()
    + "`），它只少恢复 timer 这一行。"
    "任何一步失败即停；健康检查失败时维护页保持，只有 Web 在门内运行，不自动停，等指令。不删除任何发布、备份或库。",
    "",
    "```bash",
    REOPEN.rstrip("\n"),
    "```",
    "",
    "## 附录：撞上 autovacuum 后的续跑（R67，不在默认流程）",
    "",
    "`c-` 开头的脚本默认发不出去：除 `window-go.json` 外，还要当次的 `continue-order.json`，"
    "内容 `{\"script\": \"<下表脚本名>\"}`；发送脚本在连接前把它改名为 `continue-order.used-*`，一份令只用一次。"
    "判定仍是 n==0：每次等待最多 5 分钟，发现 autovacuum worker 以外的后端立刻停，到时限也停，维护页保持。"
    "回执字段和原 D 块相同，仍是独占写；重复执行不会覆盖已有回执。文件只移开不删除。"
    "不重新改名、不重新 apply；`c-r1-after-restore` 里的对调是 R1 原块还没执行的那一步。",
    "",
    "发送命令都是 `python docs/v4/release/first_release_prod_send.py <步骤> <attempt>`，下表 attempt 写 2，再次重发递增。",
    "",
    "| 撞车位置（执行单行） | 状态 | 处置 |",
    "| --- | --- | --- |",
    "| D2 首检 302 | LIVE 开着，只写了 `central-before.json` | `c-d2-rerun-prep` → `p06a-d2-start 2` → `p06b-d2-status 2` |",
    "| D2 关库 312 | 四份 before 已写，LIVE 已关，原块连不上 | `c-d2-mid-start` → `c-d2-mid-status` |",
    "| D2 尾 321 | dump 已写，无 receipt | `c-d2-tail-start` → `c-d2-tail-status` |",
    "| D3 首检 335 | 无变化 | `c-d3-rerun-prep` → `p07a-d3-start 2` → `p07b-d3-status 2` |",
    "| D3 尾 349 | NEW 已恢复已关，无 receipt | `c-d3-tail-start` → `c-d3-tail-status` |",
    "| D4 首检 368 | 无变化 | `c-d4-rerun-prep` → `p08a-d4-start 2` → `p08b-d4-status 2` |",
    "| D4 尾 393 | 回执已写，两库已关 | `c-wait-zero` → 继续 `p09-d5-exchange` |",
    "| D5 首检 409 | 未改名 | `c-wait-zero` → `p09-d5-exchange 2` |",
    "| D5 尾 418 | 已对调，无 receipt | `c-d5-tail-start` → `c-d5-tail-status` |",
    "| D5 资产 432 | 无变化 | `c-wait-zero` → `p10-d5-assets 2` |",
    "| D6 497 | 无变化 | `c-wait-zero` → `p11-d6-preopen 2` |",
    "| D6 521 | 无变化 | `c-wait-zero` → `p12-d6-writer 2` |",
    "| D6 尾 530 | 回执已写，LIVE 已关 | `c-wait-zero` → 继续 `p13-d7-open` |",
    "| D7 550 | 无 `opened.json`，标记还在，库未开 | `c-wait-zero` → `p13-d7-open 2` |",
    "| R1 598 | 无状态变化 | `c-wait-zero` → `r01-rollback-database 2` |",
    "| R1 613（LIVE、RB 两处） | RB 已恢复已关，未对调 | `c-r1-after-restore-start` → `c-r1-after-restore-status` |",
    "| R3 646 | 库未开 | `c-wait-zero` → `r03-rollback-verify 2` |",
    "| R3 652 | 库已关，无回执 | `c-wait-zero` → `r03-rollback-verify 2` |",
    "| r04 第一段 | 库未开 | `c-wait-zero` → `r04-reopen-after-rollback 2`（或 `r04-reopen-timer-held 2`），`reopen-order.json` 仍要 |",
    "",
    "D5 尾没有补回执时不能进 R1：R1 要求 `exchange-receipt.json`，先跑 `c-d5-tail`。"
    "`c-wait-zero` 要求库已关闭，只用于 D2 关库之后。",
    "",
    "| 脚本 | sha256 |",
    "| --- | --- |",
    *[f"| `{name}` | `{value['sha256']}` |" for name, value in cont_listing.items()],
]
(ROOT / "docs/v4/release/first_release_prod_steps.md").write_bytes(("\n".join(rows) + "\n").encode("utf-8"))
print(len(manifest), "steps; all 17 runbook blocks rebuilt byte for byte")
sys.exit(0)
