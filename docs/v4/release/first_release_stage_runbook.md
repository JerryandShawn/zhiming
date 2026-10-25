# 首发 F 副本 stage 执行单（候选e578e2d）

执行人：**主线**。本单已绑定候选 `e578e2d5d83dcf3b63c74af6e1b9f1a4c86453bd`，授权依据为 v13 授权 F、main v36/v41/v49/v50 和匹配候选的37号首行 `结论：Go`；复核时间须晚于2026-10-24 12:30。文档就绪与服务器执行分开记录：37号未出现时只完成本机准备，不连接服务器，不上传。

固定交付：`C:/Users/Administrator/Documents/Codex/zhiming-v4-r46/private/fr-stage-e578e2d5d83dcf3b63c74af6e1b9f1a4c86453bd/`；包SHA256 `e1c245ebc220c136a1902ad878d7fe42014f99c91a72da87c845dde9b19bc795`；bootstrap SHA256 `18cf1f19742ae49267087856110521a47b5a957afb7a8e5b5695bf6bfc67ce42`；operation `4e680f175ea28cc8`。同源R11证据：`C:/Users/Administrator/Documents/Codex/zhiming-v4-r46/private/candidate-eval/e578e2d5d83dcf3b63c74af6e1b9f1a4c86453bd/R11-de7472f506d04966a4b1a54c8bc78f72/assessment.json`，48/48、7/7、69/69、29/29已核。质量依据main v41/38号第九节：旧8727完整29＋220定向五题＋独立人工改判，安全5/5、其他23/24；TA01保留失败，首发后查。不覆盖原机器分数，不再跑评测。

PR24同SHA CI run 40217280728（https://github.com/JerryandShawn/zhiming/actions/runs/40217280728）已启动，已实际success，head_sha/attempt1与全部job终态已核，最后实际job完成时间2026-10-25T18:50:07Z（北京时间02:50:07）。进入服务器前须同SHA success，并由37号引用；37号未放行前无服务器执行结果。原220失败证据保留在v43_candidate_ci.json。

## 范围与现有证据

原 `zhiming_core_stage` 只有只读备份；演练只用新 `zhiming_core_fr_stage` 及 `zhiming_core_fr_<operation>_restore/failed`。仅新 `zhiming-core-fr-stage.service`、127.0.0.1:8788，无模型/中央凭据，飞书/报告/公网反代不启动。原stage/live/Hermes不改、不停、不删。禁止freeze/install/publish、旧库clean恢复、Docker/代理/WSL/ACL修复。

恢复/复制/回填、B7和运行资产的唯一本机原件索引见[恢复计划14:00–14:19四活节](../execplans/first_release_recovery_20261023.md)。各定向轮次分别通过；不称一次完整Linux链。stage模型端口明确拒绝请求，真实Agent/公开K3/PG装配只开放健康、状态、历史，原Web子app队列/dispatcher/维护worker不启动。这不是模型或常驻队列验收。

|门|当前结论|
|---|---|
|同一首发源码、CI、R11|本单绑定e578e2d包/R11原件，R11已根核通过，同SHA CI success（run40217280728，attempt1，完成北京时间02:50:07）；同SHA success并由37号引用后才继续，不复用旧候选批准|
|新库保owner/ACL/设置与0连接对调|本机必要门已解除，证据见恢复计划；Linux结果由本单实际执行记录|
|副本迁移/回填/撤销收据及空增量B7|本机必要门已解除；不得把副本旁账称为生产停写后最新旁账|
|无模型新角色/8788资产/维护栅栏|本机必要门已解除；systemd、cgroup和Linux解释器仍须现场核验|
|F/37、容量、凭据与目标全新|主线按下方37号/候选本机门与现场只读容量、凭据和全新对象门核验，任一缺失即停止|

任何**非预设负验**异常：立刻停，保持当前库/门/文件，记日报；不修补重试、覆盖、删除或杀PG会话。SSH每次一个短会话；拒绝等10分钟最多3次。耗时动作后台，后续短连只读检查结果；前一步未明确exit0不得执行下一步。备份/操作目录0700、文件0600、保留14天，不自动清理。回滚只在开门之前，B7只做空增量；开门后只关闭新服务准入，不回退数据。

## 执行前本机身份门（不连接服务器）

主线读取37号，只接受首行Go、明确复核时间晚于2026-10-24 12:30且同一40位SHA；缺失即停止。先通过下列本机校验，再结合当次授权范围进入服务器步骤。本轮37号未出现，服务器命令均未执行。同SHA CI已success；37号仍必须引用该候选和成功CI后才继续。

```powershell
$FrGate = 'C:/Users/Administrator/Documents/Codex/2026-10-11/p-jerrymeng-asia-1-14-59/outputs/明镜台v4_大脑交付/37_大脑复核_首发stage.md'
if (-not (Test-Path -LiteralPath $FrGate -PathType Leaf)) { throw '37号未出现，停止' }
$FrGateLines = Get-Content -LiteralPath $FrGate
if ($FrGateLines[0].Trim() -ne '结论：Go') { throw '37号没有Go，停止' }
$FrGateText = $FrGateLines -join "`n"
if ($FrGateText -notmatch 'e578e2d5d83dcf3b63c74af6e1b9f1a4c86453bd') { throw '37号候选不符，停止' }
$FrTimes = [regex]::Matches($FrGateText, '(?:复核时间|写入时间)[：:]\s*(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?\s*(?:\+08:00|北京时间))')
if ($FrTimes.Count -ne 1) { throw '37号复核时间缺失或歧义，停止' }
$FrTime = [DateTimeOffset]::Parse($FrTimes[0].Groups[1].Value.Replace('北京时间','+08:00'))
if ($FrTime -le [DateTimeOffset]'2026-10-24T12:30:00+08:00') { throw '37号复核时间太旧，停止' }
```

37号时间字段按上述格式核验；实际文件格式不同或有歧义就停，不能用文件修改时间代替。CI原证据见 `../eval/v50_candidate_ci.json`；原220失败见v43_candidate_ci.json，不覆盖原件。继续条件为同SHA CI success及37号明确放行；否则停止并提醒。

## B0–B1：本机固定包、引导文件与公开分词器

在下面固定clean候选树核验已经实际生成的包，不重新打包、不覆盖旧交付物。任一hash/候选不符即停止。

```powershell
$FrSha = 'e578e2d5d83dcf3b63c74af6e1b9f1a4c86453bd'
$FrRepo = 'C:/Users/Administrator/Documents/Codex/zhiming-v4-r46'
$FrPython = 'C:/Users/Administrator/Documents/Codex/zhiming-v4/.venv-k3/Scripts/python.exe'
$FrTokenizer = 'C:/Users/Administrator/Documents/Codex/zhiming-v4/private/artifacts/kimi-k3-installer-20261023'
Set-Location $FrRepo
if ((git rev-parse HEAD) -ne $FrSha -or (git status --porcelain)) { throw '候选或clean状态不符' }
$FrDelivery = Join-Path $FrRepo "private/fr-stage-$FrSha"
$FrTar = Join-Path $FrDelivery 'release.tar.gz'
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $FrTar).Hash.ToLowerInvariant() -ne 'e1c245ebc220c136a1902ad878d7fe42014f99c91a72da87c845dde9b19bc795') { throw '包hash不符' }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $FrDelivery 'bootstrap.py')).Hash.ToLowerInvariant() -ne '18cf1f19742ae49267087856110521a47b5a957afb7a8e5b5695bf6bfc67ce42') { throw '引导hash不符' }
& $FrPython -m tools.install_k3_tokenizer --destination $FrTokenizer --verify-only
if ($LASTEXITCODE -ne 0) { throw '公开分词器原件不符' }
$FrBound = Get-Content (Join-Path $FrDelivery 'delivery.json') -Raw | ConvertFrom-Json
if ($FrBound.candidate -ne $FrSha -or $FrBound.operation -ne '4e680f175ea28cc8') { throw '交付身份不符' }
```

主线用上述命令核delivery.json中的SHA、operation、两项hash；全部相等才采用下方固定参数，任一不符停止并提醒。交付包没有私有env/key/数据库。**不要SCP整个private目录。** Kimi key文件不在stage交付物中。

第一次短SSH只读确认 `df -Pk /` 可用至少8388608 KiB、Python3.11和PG15客户端存在、原服务与8788端口当前状态。确认新root和新unit均不存在后，才在F范围内创建新目录；若已有同名物停止，不接管。

```bash
set -euo pipefail
umask 077
FR_SHA='e578e2d5d83dcf3b63c74af6e1b9f1a4c86453bd'
FR_ID='4e680f175ea28cc8'
[[ "$FR_SHA" =~ ^[0-9a-f]{40}$ && "$FR_ID" =~ ^[0-9a-f]{16}$ ]]
FR_ROOT=/root/zhiming-core-fr-stage
awk 'NR==2 {exit !($4>=8388608)}' < <(df -Pk /)
# v49: use programs beside the actual 5432 postmaster, never a distribution-specific path.
mapfile -t FR_PG_PIDS < <(ss -H -ltnp 'sport = :5432' | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u)
test "${#FR_PG_PIDS[@]}" = 1
FR_PG_EXE="$(readlink -f "/proc/${FR_PG_PIDS[0]}/exe")"
test "$(basename "$FR_PG_EXE")" = postgres -o "$(basename "$FR_PG_EXE")" = postmaster
FR_PG_BIN="$(dirname "$FR_PG_EXE")"
FR_DUMP="$FR_PG_BIN/pg_dump"
FR_RESTORE="$FR_PG_BIN/pg_restore"
FR_PSQL="$FR_PG_BIN/psql"
for program in "$FR_PG_EXE" "$FR_DUMP" "$FR_RESTORE" "$FR_PSQL"; do
 test -x "$program"
 "$program" --version | grep -Eq '\) 15\.'
done
command -v python3.11 sha256sum runuser
test "$(stat -fc %T /sys/fs/cgroup)" = cgroup2fs
grep -Fq 'if (-f /www/wwwroot/p-acme/core-maintenance.flag)' /www/server/panel/vhost/nginx/p.jerrymeng.asia.conf
! test -e "$FR_ROOT"
! test -e /etc/systemd/system/zhiming-core-fr-stage.service
! ss -ltn | awk '{print $4}' | grep -Eq '(^|:)8788$'
mkdir -m 700 "$FR_ROOT"
sha256sum "$FR_PG_EXE" "$FR_DUMP" "$FR_RESTORE" "$FR_PSQL" > "$FR_ROOT/pg-programs.sha256"
mkdir -m 700 "$FR_ROOT/uploads" "$FR_ROOT/releases" "$FR_ROOT/venvs" "$FR_ROOT/tokenizer" "$FR_ROOT/operations"
mkdir -m 700 "$FR_ROOT/tokenizer/$FR_SHA" "$FR_ROOT/operations/$FR_ID"
```

根分区不足8GiB、现有fr_stage数据库/新writer角色/同名unit或root存在均停止；不删旧物腾空间。数据库是否全新由copy/provision的实际PG门再次核验。

回到本机，只上传三份公开交付物和lock列出的六个已核公开文件；下面是主线在执行准入满足后使用的传输命令；当前没有上传。

```powershell
scp -- $FrTar (Join-Path $FrDelivery 'bootstrap.py') (Join-Path $FrDelivery 'delivery.json') 'root@1.14.59.242:/root/zhiming-core-fr-stage/uploads/'
if ($LASTEXITCODE -ne 0) { throw '上传失败停止' }
$FrNames = (Get-Content 'k3-tokenizer.lock.json' -Raw | ConvertFrom-Json).files.PSObject.Properties.Name
$FrPublicFiles = @($FrNames | ForEach-Object { Join-Path $FrTokenizer $_ })
scp -- @FrPublicFiles "root@1.14.59.242:/root/zhiming-core-fr-stage/tokenizer/$FrSha/"
if ($LASTEXITCODE -ne 0) { throw '公开分词器上传失败停止' }
```

## B2：核包、独立环境、短会话公共命令

每次新短SSH重设已审的FR_SHA/FR_ID及下列路径；不能从新的HEAD自动取号。hash使用本机delivery原件中的已审核值，不能只信服务器同目录可改的JSON。

```bash
set -euo pipefail
set -C
umask 077
FR_SHA='e578e2d5d83dcf3b63c74af6e1b9f1a4c86453bd'
FR_ID='4e680f175ea28cc8'
[[ "$FR_SHA" =~ ^[0-9a-f]{40}$ && "$FR_ID" =~ ^[0-9a-f]{16}$ ]]
FR_ROOT=/root/zhiming-core-fr-stage
FR_OP="$FR_ROOT/operations/$FR_ID"
FR_RELEASE="$FR_ROOT/releases/$FR_SHA"
FR_PY="$FR_ROOT/venvs/$FR_SHA/core/bin/python"
FR_TOKENIZER="$FR_ROOT/tokenizer/$FR_SHA"
FR_ADMIN=/root/zhiming-core-secrets/fr-stage-admin.env
# v49: use programs beside the actual 5432 postmaster, never a distribution-specific path.
mapfile -t FR_PG_PIDS < <(ss -H -ltnp 'sport = :5432' | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u)
test "${#FR_PG_PIDS[@]}" = 1
FR_PG_EXE="$(readlink -f "/proc/${FR_PG_PIDS[0]}/exe")"
test "$(basename "$FR_PG_EXE")" = postgres -o "$(basename "$FR_PG_EXE")" = postmaster
FR_PG_BIN="$(dirname "$FR_PG_EXE")"
FR_DUMP="$FR_PG_BIN/pg_dump"
FR_RESTORE="$FR_PG_BIN/pg_restore"
FR_PSQL="$FR_PG_BIN/psql"
for program in "$FR_PG_EXE" "$FR_DUMP" "$FR_RESTORE" "$FR_PSQL"; do
 test -x "$program"
 "$program" --version | grep -Eq '\) 15\.'
done
command -v python3.11 sha256sum runuser
test "$(stat -fc %T /sys/fs/cgroup)" = cgroup2fs
grep -Fq 'if (-f /www/wwwroot/p-acme/core-maintenance.flag)' /www/server/panel/vhost/nginx/p.jerrymeng.asia.conf
sha256sum -c "$FR_ROOT/pg-programs.sha256"
FR_PACKAGE_SHA='e1c245ebc220c136a1902ad878d7fe42014f99c91a72da87c845dde9b19bc795'
FR_BOOTSTRAP_SHA='18cf1f19742ae49267087856110521a47b5a957afb7a8e5b5695bf6bfc67ce42'
h() { sha256sum "$1" | cut -d ' ' -f 1; }
```

首次准备：两hash均须64hex且匹配，解包只允许全新release。只装Core锁，不混旧requirements-web.lock/Charts环境。不启动任何服务。

```bash
[[ "$FR_PACKAGE_SHA" =~ ^[0-9a-f]{64}$ && "$FR_BOOTSTRAP_SHA" =~ ^[0-9a-f]{64}$ ]]
test "$(h "$FR_ROOT/uploads/release.tar.gz")" = "$FR_PACKAGE_SHA"
test "$(h "$FR_ROOT/uploads/bootstrap.py")" = "$FR_BOOTSTRAP_SHA"
python3.11 -I "$FR_ROOT/uploads/bootstrap.py" --candidate "$FR_SHA" --artifact "$FR_ROOT/uploads/release.tar.gz" --artifact-sha256 "$FR_PACKAGE_SHA" --release "$FR_RELEASE"
! test -e "$FR_ROOT/venvs/$FR_SHA"
mkdir -m 700 "$FR_ROOT/venvs/$FR_SHA"
```

venv创建、锁依赖安装应后台单步运行并留exit/log，不在长SSH会话等。下面公共函数可用于任意固定参数的长命令，未产生exit文件只表示未完成，不能进入下一步。函数不重试任何步骤，同名日志/pid/exit一律拒绝覆盖。

```bash
start_step() {
  local name="$1"; shift
  [[ "$name" =~ ^[a-z0-9-]+$ ]]
  for ext in log pid exit; do ! test -e "$FR_OP/$name.$ext"; done
  nohup /bin/bash -c 'set -C; out=$1; shift; "$@"; rc=$?; printf "%s\n" "$rc" > "$out"; exit "$rc"' fr-step "$FR_OP/$name.exit" "$@" > "$FR_OP/$name.log" 2>&1 < /dev/null &
  printf '%s\n' "$!" > "$FR_OP/$name.pid"
}
check_step() {
  local name="$1"
  test -f "$FR_OP/$name.exit"
  test "$(cat "$FR_OP/$name.exit")" = 0
}
FR_RUN=(env -i PATH=/usr/bin:/bin HOME=/root LANG=C.UTF-8 TZ=Asia/Shanghai "$FR_PY" -I -c 'import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module(sys.argv.pop(1),run_name="__main__")' "$FR_RELEASE")
fr() { "${FR_RUN[@]}" "$@"; }
receipt_status() {
  "$FR_PY" -I - "$1" "$2" <<'PY'
import json,sys
v=json.load(open(sys.argv[1],encoding='utf-8'))
assert v['status']==sys.argv[2]
assert not v.get('admission_opened',False)
print('receipt status verified:',sys.argv[2])
PY
}

```

依次start、退出SSH、后续短连check，**每次check明确0后才手动开始下一条**：

```bash
start_step venv python3.11 -m venv "$FR_ROOT/venvs/$FR_SHA/core"
# 后续短会话 check_step venv 成功后：
start_step dependencies "$FR_PY" -m pip install --require-hashes -r "$FR_RELEASE/requirements-core.lock"
# 后续 check_step dependencies 成功后：
"$FR_PY" -m pip check
fr tools.install_k3_tokenizer --destination "$FR_TOKENIZER" --verify-only
```

### R28：只在服务器就地准备回环管理员（stage / 生产共用）

仅在对应37/31号Go及授权范围内运行。先读权限、已有文件和实际身份；两文件都不存在才经 postgres 系统用户和 `/tmp` socket 创建 `zhiming_fr_admin`。32字节随机口令仅在服务器内存/两个root私有文件中，禁止shell tracing、打印、日志或回传；已有角色但凭据文件都缺失则停，不重置口令。只供127.0.0.1本机管理，不配置远程访问，不修改pg_hba。TCP口令认证不允许时停并【提醒用户】，保留现场、不重试建角色。

```bash
set +x
python3.11 -I - "$FR_PSQL" <<'PY'
import os,pathlib,secrets,shlex,shutil,stat,subprocess,urllib.parse
assert os.geteuid()==0
psql=__import__('sys').argv[1]
parent=pathlib.Path('/root/zhiming-core-secrets')
assert not parent.is_symlink()
if not parent.exists():parent.mkdir(mode=0o700)
assert parent.is_dir() and parent.stat().st_uid==0 and stat.S_IMODE(parent.stat().st_mode)==0o700
paths=[parent/'fr-stage-admin.env',parent/'fr-prod-admin.env']
key='FIRST_RELEASE_EXCHANGE_ADMIN_DSN'
def private(path):
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
 with os.fdopen(fd,'rb') as stream:
  s=os.fstat(stream.fileno());assert stat.S_ISREG(s.st_mode) and s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o600
  data=stream.read(8193);assert len(data)<=8192
 return data
existing=[private(p) for p in paths if p.exists() or p.is_symlink()]
base={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PGCONNECT_TIMEOUT':'5'}
def call(argv,query,env):
 r=subprocess.run(argv,input=query,text=True,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 assert r.returncode==0,'R28 authentication/SQL refused; stop, do not alter pg_hba; private diagnostics not printed'
 return r.stdout.strip()
runuser=shutil.which('runuser');assert runuser and pathlib.Path(runuser).is_absolute()
socket=[runuser,'-u','postgres','--',psql,'-X','-w','-h','/tmp','-p','5432','-d','postgres','-v','ON_ERROR_STOP=1','-Atq']
if existing:
 assert all(data==existing[0] for data in existing),'R28 files disagree; stop'
 data=existing[0];lines=[x for x in data.decode().splitlines() if x.strip()]
 assert len(lines)==1
 name,sep,value=lines[0].partition('=');assert sep and name==key
 values=shlex.split(value);assert len(values)==1
 dsn=values[0];u=urllib.parse.urlsplit(dsn)
 assert u.scheme in ('postgres','postgresql') and u.hostname=='127.0.0.1' and u.port==5432 and u.path=='/postgres' and not u.query and not u.fragment
 user=urllib.parse.unquote(u.username or '');password=urllib.parse.unquote(u.password or '')
 assert user and password
else:
 assert call(socket,"SELECT count(*) FROM pg_roles WHERE rolname='zhiming_fr_admin';",base)=='0','R28 role exists without files; stop, no password rotation'
 password=secrets.token_hex(32);user='zhiming_fr_admin'
 # psql reads separate stdin commands: disable statement logging before sending the credential statement.
 query="SET log_statement='none';\nSET log_min_duration_statement=-1;\nSET log_min_error_statement='panic';\nSET password_encryption='scram-sha-256';\nCREATE ROLE zhiming_fr_admin SUPERUSER LOGIN PASSWORD '"+password+"';\n"
 call(socket,query,base)
 dsn='postgresql://'+user+':'+password+'@127.0.0.1:5432/postgres'
 data=(key+'='+dsn+'\n').encode()
env={**base,'PGPASSWORD':password}
check=call([psql,'-X','-w','-h','127.0.0.1','-p','5432','-U',user,'-d','postgres','-v','ON_ERROR_STOP=1','-Atq'],"SELECT current_user=session_user AND (SELECT rolsuper FROM pg_roles WHERE rolname=session_user) AND current_database()='postgres' AND inet_server_addr()='127.0.0.1'::inet AND inet_server_port()=5432 AND current_setting('server_version_num')::int BETWEEN 150000 AND 159999;",env)
assert check=='t','R28 actual superuser/loopback/PG15 check failed'
for path in paths:
 if path.exists() or path.is_symlink():assert private(path)==data
 else:
  fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
  with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
 assert private(path)==data
env.clear();password=dsn=data=None
print('R28: local administrator authenticated; two private files verified; credential output=0')
PY
test -f "$FR_ADMIN" && ! test -L "$FR_ADMIN"
test "$(stat -c '%a %u' "$FR_ADMIN")" = '600 0'
test "$(stat -c '%a %u' "$(dirname "$FR_ADMIN")")" = '700 0'
```

上述文件使用单字段URI DSN；若已有文件不是该受支持格式，停止审查而不覆盖。任意错误输出只记录步骤失败，不复制SQL/口令/原stderr；不现场安装软件或修改认证。

## B3–B5：只读复制、迁移与primary回填/副本旁账重放

```bash
start_step copy "${FR_RUN[@]}" tools.first_release_stage_copy --operation "$FR_ID" --workspace "$FR_OP" --pg-dump "$FR_DUMP" --pg-dump-sha256 "$(h "$FR_DUMP")" --pg-restore "$FR_RESTORE" --pg-restore-sha256 "$(h "$FR_RESTORE")" --admin-env-file "$FR_ADMIN" --apply
check_step copy
receipt_status "$FR_OP/copy-receipt.json" copied_closed
# 上述两项成功后才执行下一条：
start_step prepare "${FR_RUN[@]}" tools.first_release_stage_prepare --operation "$FR_ID" --workspace "$FR_OP" --copy-receipt "$FR_OP/copy-receipt.json" --copy-receipt-sha256 "$(h "$FR_OP/copy-receipt.json")" --admin-env-file "$FR_ADMIN" --apply
```

prepare结束后执行以下安全投影校验；非0立即停止，不继续B7：

```bash
check_step prepare
receipt_status "$FR_OP/prepare-receipt.json" prepared_closed
fr tools.first_release_stage_prepare --help >/dev/null
"$FR_PY" -I - "$FR_OP/prepare-receipt.json" "$FR_RELEASE" <<'PY'
import json,sys
sys.path.insert(0,sys.argv[2])
from tools.first_release_contracts import MIGRATIONS
v=json.load(open(sys.argv[1],encoding='utf-8'))
assert v['migration_checksums']==MIGRATIONS
assert all(v['backfill_repeat'][k]==0 for k in ('message_metadata','search_tokens','assistant_created'))
assert v['replay_full_state_unchanged'] is True
assert v['model_calls']==v['external_sends']==0
print('prepare: migrations, repeat-zero, privacy replay verified')
PY
```

prepare-receipt还须migrations完整1–8/checksum匹配、backfill_repeat的message_metadata/search_tokens/assistant_created全0、replay_full_state_unchanged=true、model_calls/external_sends=0。source/target OID必须来自同次copy；不手改receipt、started或任何数据来放行。缺primary、旧未核checksum、无run_id/冲突收据等真实错误均停止。

## B7：开门前空增量新库恢复与改名对调

新服务和writer均尚未创建。使用迁移后的新副本做空增量备份；不是恢复原stage旧前缀，也不在已迁移库执行clean。

```bash
fr tools.first_release_native_exchange capture --operation "$FR_ID" --admin-env-file "$FR_ADMIN" --metadata "$FR_OP/rollback-before.json" --output "$FR_OP/capture-receipt.json"
start_step backup "${FR_RUN[@]}" tools.first_release_stage_backup --operation "$FR_ID" --workspace "$FR_OP" --metadata "$FR_OP/rollback-before.json" --metadata-sha256 "$(h "$FR_OP/rollback-before.json")" --pg-dump "$FR_DUMP" --pg-dump-sha256 "$(h "$FR_DUMP")" --admin-env-file "$FR_ADMIN" --apply
check_step backup
receipt_status "$FR_OP/empty-delta-receipt.json" backed_up_closed
# 上述校验成功后：
start_step restore "${FR_RUN[@]}" tools.first_release_native_exchange restore --operation "$FR_ID" --admin-env-file "$FR_ADMIN" --metadata "$FR_OP/empty-delta-metadata.json" --metadata-sha256 "$(h "$FR_OP/empty-delta-metadata.json")" --backup "$FR_OP/empty-delta.dump" --backup-sha256 "$(h "$FR_OP/empty-delta.dump")" --pg-restore "$FR_RESTORE" --pg-restore-sha256 "$(h "$FR_RESTORE")" --output "$FR_OP/restore-receipt.json"
check_step restore
receipt_status "$FR_OP/restore-receipt.json" restored_new_database
# 上述校验成功后：
fr tools.first_release_native_exchange seal --operation "$FR_ID" --admin-env-file "$FR_ADMIN" --metadata "$FR_OP/empty-delta-metadata.json" --metadata-sha256 "$(h "$FR_OP/empty-delta-metadata.json")" --output "$FR_OP/seal-receipt.json"
fr tools.first_release_native_exchange exchange --operation "$FR_ID" --admin-env-file "$FR_ADMIN" --metadata "$FR_OP/empty-delta-metadata.json" --metadata-sha256 "$(h "$FR_OP/empty-delta-metadata.json")" --restore-receipt "$FR_OP/restore-receipt.json" --restore-receipt-sha256 "$(h "$FR_OP/restore-receipt.json")" --output "$FR_OP/exchange-receipt.json"
```

执行exchange后必须运行：

```bash
receipt_status "$FR_OP/exchange-receipt.json" exchanged_closed
"$FR_PY" -I - "$FR_OP/exchange-receipt.json" <<'PY'
import json,sys
v=json.load(open(sys.argv[1],encoding='utf-8'))
assert all(v[k] is False for k in ('admission_opened','old_database_deleted','production'))
assert v['current_oid']>0
print('exchange: closed, preserved, stage-only verified')
PY
```

继续条件还包括current_oid为新恢复库OID，failed_database为本operation唯一failed名，admission_opened/old_database_deleted/production均false。两库必须保持closed/0连接；旧failed库和全部备份保留。owner、CONNECT ACL/授权选项、库级及角色库级SET由捕获原件恢复。任何活动会话/元数据漂移/已有目标都立即停，不终止PG会话。新writer和任何应用开门后不再执行本节回滚。

## B6–B8：新运行资产、Linux启动与限定冒烟

```bash
fr tools.first_release_stage_runtime provision --operation "$FR_ID" --workspace "$FR_OP" --receipt "$FR_OP/exchange-receipt.json" --receipt-sha256 "$(h "$FR_OP/exchange-receipt.json")" --candidate "$FR_SHA" --tokenizer "$FR_TOKENIZER" --admin-env-file "$FR_ADMIN" --apply
systemd-analyze verify "$FR_OP/zhiming-core-fr-stage.service"
! test -e /etc/systemd/system/zhiming-core-fr-stage.service
# set -C的独占重定向保护已有unit；不使用覆盖式install/cp。
(umask 022; cat "$FR_OP/zhiming-core-fr-stage.service" > /etc/systemd/system/zhiming-core-fr-stage.service)
test "$(h /etc/systemd/system/zhiming-core-fr-stage.service)" = "$(h "$FR_OP/zhiming-core-fr-stage.service")"
systemctl daemon-reload
fr tools.first_release_stage_runtime admit --operation "$FR_ID" --workspace "$FR_OP" --receipt "$FR_OP/runtime-receipt.json" --receipt-sha256 "$(h "$FR_OP/runtime-receipt.json")" --admin-env-file "$FR_ADMIN" --apply
systemctl start zhiming-core-fr-stage.service
test "$(systemctl show -p ActiveState --value zhiming-core-fr-stage.service)" = active
systemctl show zhiming-core-fr-stage.service -p MainPID -p ControlGroup -p IPAddressDeny -p IPAddressAllow -p RestrictAddressFamilies -p SocketBindAllow -p SocketBindDeny
```

systemd不识别指令、BPF/cgroup不可用、unit启动失败或监听不符都停止，不能忽略警告或放宽封锁。`ss -ltnp`应仅有新进程127.0.0.1:8788，不能0.0.0.0/公网。只向新角色授予新副本DML，schema/checkpoint迁移台账无写权，不修改旧库ACL。runtime.json含新网站token/DB口令，仅留私有目录，绝不打印或scp。

健康冒烟不把token放进命令行、日志或curl参数；只打印路径/状态码，不打印真实状态/历史正文：

```bash
"$FR_PY" -I - "$FR_OP/runtime.json" <<'PY'
import json,sys,urllib.request
v=json.load(open(sys.argv[1],encoding='utf-8'))
for path in ('/api/health','/api/state','/api/history'):
    request=urllib.request.Request('http://127.0.0.1:8788'+path,headers={'X-Token':v['token']})
    with urllib.request.urlopen(request,timeout=10) as response:
        assert response.status==200
        value=json.loads(response.read(4_000_001))
        if path=='/api/health':
            assert value['ok'] is True and value['model']=='stage-model-access-disabled'
        print(path,response.status)
PY
```

出站核验必须检查**实际新unit cgroup**，不是另建transient unit。以下由主线在F范围内做TCP连通正负验，不发任何应用层payload，不访问模型/飞书；正验依次试1.1.1.1:443、223.5.5.5:443，选首个可达地址做同地址负验；两者都不可达时不能证明阻断，立即停止并发【提醒用户】。子进程只把自己加入已确认的新unit cgroup，退出后不留进程、不动其他cgroup。

```bash
FR_CGROUP="$(systemctl show -p ControlGroup --value zhiming-core-fr-stage.service)"
test "$FR_CGROUP" = /system.slice/zhiming-core-fr-stage.service
"$FR_PY" -I - "$FR_CGROUP" <<'PY'
import errno,os,pathlib,socket,sys
endpoint=None
for candidate in (('1.1.1.1',443),('223.5.5.5',443)):
    try:
        with socket.create_connection(candidate,timeout=3):
            pass
    except OSError:
        continue
    endpoint=candidate
    break
assert endpoint is not None,'neither positive TCP endpoint reachable; stop'
print('selected TCP endpoint:',endpoint[0],endpoint[1])
pid=os.fork()
if pid==0:
    try:
        assert sys.argv[1]=='/system.slice/zhiming-core-fr-stage.service'
        path=pathlib.Path('/sys/fs/cgroup'+sys.argv[1])/'cgroup.procs'
        with path.open('w') as stream:
            stream.write(str(os.getpid()))
        try:
            connection=socket.create_connection(endpoint,timeout=3)
        except OSError as error:
            assert isinstance(error,TimeoutError) or error.errno in (errno.EPERM,errno.EACCES)
            os._exit(0)
        else:
            connection.close()
            os._exit(2)
    except BaseException:
        os._exit(3)
_,status=os.waitpid(pid,0)
assert os.waitstatus_to_exitcode(status)==0,'actual stage cgroup outbound check failed'
print('host TCP reachable; actual new-unit cgroup blocked; application payloads=0')
PY
```

writer负验：新unit保持运行时，用同候选的file_lock对FR_OP/writer.lock申请exclusive必须得到预设`INCREMENTAL_FILE_FENCE_BUSY`；不得获得锁。随后新建maintenance.json，三个GET均应503。该负验为计划内门测试，不是允许忽略实际业务异常。

```bash
"$FR_PY" -I - "$FR_RELEASE" "$FR_OP" <<'PY'
import os,pathlib,sys
sys.path.insert(0,sys.argv[1])
from tools.first_release_contracts import RestoreRejected
from tools.first_release_writer_fence import file_lock
root=pathlib.Path(sys.argv[2])
try:
    with file_lock(root/'writer.lock',exclusive=True,existing_only=True):
        raise SystemExit('unexpected exclusive writer admission')
except RestoreRejected as error:
    assert str(error)=='INCREMENTAL_FILE_FENCE_BUSY'
fd=os.open(root/'maintenance.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as stream:
    stream.write('{"purpose":"F maintenance drill"}\n')
print('expected writer rejection; maintenance gate closed')
PY
```

三个端点均须返回503，不打印正文：

```bash
"$FR_PY" -I - "$FR_OP/runtime.json" <<'PY'
import json,sys,urllib.error,urllib.request
v=json.load(open(sys.argv[1],encoding='utf-8'))
for path in ('/api/health','/api/state','/api/history'):
    request=urllib.request.Request('http://127.0.0.1:8788'+path,headers={'X-Token':v['token']})
    try:
        with urllib.request.urlopen(request,timeout=10):
            raise SystemExit('maintenance request unexpectedly admitted')
    except urllib.error.HTTPError as error:
        assert error.code==503
    print(path,503)
PY
```

然后只停新unit，保持维护门，不做开门后回滚。确认新进程自然退出/0连接，再capture+seal新副本，收尾状态明确为“新unit inactive，新副本及failed均closed，维护门保留”。

```bash
systemctl stop zhiming-core-fr-stage.service
test "$(systemctl show -p ActiveState --value zhiming-core-fr-stage.service)" = inactive
fr tools.first_release_native_exchange capture --operation "$FR_ID" --admin-env-file "$FR_ADMIN" --metadata "$FR_OP/finish-metadata.json" --output "$FR_OP/finish-capture.json"
fr tools.first_release_native_exchange seal --operation "$FR_ID" --admin-env-file "$FR_ADMIN" --metadata "$FR_OP/finish-metadata.json" --metadata-sha256 "$(h "$FR_OP/finish-metadata.json")" --output "$FR_OP/finish-sealed.json"
```

不自动恢复/重启，不移除维护门或删除任何备份/库/unit。Linux实际执行人负责一页以内回执：最终SHA/operation、每步exit/用时/安全结果、偏差或第一失败码、实际模型/外发次数0、原stage/live/Hermes未改、最终closed/inactive状态。没有实际执行的项目写“未验证”，不据本机测试补造Linux结果。生产执行单仍未放行，按独立31号窗口核D范围及原生生产目标入口。
