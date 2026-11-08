# 首发 F 副本 stage 执行单（候选bf6e0bbc）

main64/R45认证参数：本机发起的每次SSH/SCP必须显式使用 `-i C:/Users/Administrator/.ssh/gto_deploy_key`；若使用DEPLOY_KEY_FILE，固定为该路径。只供SSH工具按路径使用，不读取/复制/输出钥匙内容，不改服务器认证或网络。Windows向远端bash发送已审脚本时，须以UTF-8且LF原始字节写stdin，禁止text=True等文本管道转成CRLF；失败后仍按本单停止，不现场修补重试。

main67/R49警告裁定：必须先verify exit0，再逐行精确核对输出。只豁免既有 `/etc/systemd/system/tat_agent.service` 的旧 `/var/run` PIDFile，以及 `/usr/lib/systemd/system/iptables.service`、`ip6tables.service` 的过时syslog输出警告；原始豁免行写回执。其他任何输出/警告，尤其zhiming unit、drop-in或runtime相关，均停止；不改、重载或停用这三个既有unit。下面捕获与严格过滤代码只落实此名单，其他执行步骤不变。

执行人：**主线**。本单已绑定合并候选 `bf6e0bbc720b85510d757b17d4ccd74ff60687bb`，操作授权依据为用户 2026-11-07 的连续上线指令；同候选37号、CI、R11和stage技术门不变。文档就绪与服务器执行分开记录，未满足前不连接或上传。

固定交付：`C:/Users/Administrator/Documents/Codex/zhiming-v4-release-candidate-20261107/private/fr-stage-bf6e0bbc720b85510d757b17d4ccd74ff60687bb/`；包SHA256 `3294003e56ca152b6de7f1127e68f850e25f4eb114b5b7478b1f810a7f46d59d`；bootstrap SHA256 `18cf1f19742ae49267087856110521a47b5a957afb7a8e5b5695bf6bfc67ce42`；operation `bcac4df7780c4516`。交付物已从精确 Git 提交生成，共1863个跟踪文件；同源R11、CI和完整回归结果待本候选实际通过后填写，旧候选结果不移植。

本候选 Core CI run 42388565834 正在执行，时区 run 待实际结果后绑定（e6616500 的 run 42375109086 属于文档分支，不是候选证据）。进入服务器前由37号引用完整SHA和实际成功结果；旧 run 42337532390 仅属于 6d803bff，不能作为本单证据。

## 范围与现有证据

原 `zhiming_core_stage` 只有只读备份；演练副本是候选工具固定的 `zhiming_core_fr_stage`（first_release_stage_copy的copy目标、first_release_native_exchange的原名，不带operation），新writer固定为 `zhiming_core_fr_stage_writer`（first_release_stage_runtime），另有本operation的 `zhiming_core_fr_bcac4df7780c4516_restore/failed`。11-07 afdfc演练留下的同名副本库（OID 70807）与writer（OID 72548）必须先经B2.5改名保留为 `zhiming_core_fr_stage_6d803bff` / `zhiming_core_fr_stage_6d803bff_writer`，否则copy报 `EXCHANGE_NEW_NAME_ALREADY_EXISTS`、provision报 `STAGE_NEW_WRITER_REQUIRED`。仅新 `zhiming-core-fr-stage-bcac4df7780c4516.service`、127.0.0.1:8788，无模型/中央凭据，飞书/报告/公网反代不启动。原stage/live/Hermes不改、不停、不删。禁止freeze/install/publish、旧库clean恢复、Docker/代理/WSL/ACL修复。

恢复/复制/回填、B7和运行资产的唯一本机原件索引见[恢复计划14:00–14:19四活节](../execplans/first_release_recovery_20261023.md)。各定向轮次分别通过；不称一次完整Linux链。stage模型端口明确拒绝请求，真实Agent/公开K3/PG装配只开放健康、状态、历史，原Web子app队列/dispatcher/维护worker不启动。这不是模型或常驻队列验收。

|门|当前结论|
|---|---|
|同一首发源码、CI、R11|本单绑定bf6e0bbc包；同源R11、同SHA CI与完整回归须实际通过，37号在全部技术证据满足后引用|
|新库保owner/ACL/设置与0连接对调|本机必要门已解除，证据见恢复计划；Linux结果由本单实际执行记录|
|副本迁移/回填/撤销收据及空增量B7|本机必要门已解除；不得把副本旁账称为生产停写后最新旁账|
|无模型新角色/8788资产/维护栅栏|本机必要门已解除；systemd、cgroup和Linux解释器仍须现场核验|
|F/37、容量、凭据与目标全新|主线按下方37号/候选本机门与现场只读容量、凭据和全新对象门核验，任一缺失即停止|

任何**非预设负验**异常：立刻停，保持当前库/门/文件，记日报；不修补重试、覆盖、删除或杀PG会话。SSH每次一个短会话；拒绝等10分钟最多3次。耗时动作后台，后续短连只读检查结果；前一步未明确exit0不得执行下一步。备份/操作目录0700、文件0600、保留14天，不自动清理。回滚只在开门之前，B7只做空增量；开门后只关闭新服务准入，不回退数据。

## 执行前本机身份门（不连接服务器）

主线读取本次37号复核记录，只接受首行Go、明确复核时间晚于2026-11-07 12:00且同一40位SHA；缺失即停止。先通过下列本机校验，再结合当次授权范围进入服务器步骤。37号必须引用该候选和实际成功CI后才继续。

```powershell
$FrGate = 'C:/Users/Administrator/Documents/Codex/zhiming-v4-release-prep/private/review-37-bf6e0bbc720b85510d757b17d4ccd74ff60687bb.md'
if (-not (Test-Path -LiteralPath $FrGate -PathType Leaf)) { throw '37号未出现，停止' }
$FrGateLines = Get-Content -LiteralPath $FrGate -Encoding UTF8
if ($FrGateLines[0].Trim() -ne '结论：Go') { throw '37号没有Go，停止' }
$FrGateText = $FrGateLines -join "`n"
if ($FrGateText -notmatch 'bf6e0bbc720b85510d757b17d4ccd74ff60687bb') { throw '37号候选不符，停止' }
$FrTimes = [regex]::Matches($FrGateText, '(?:复核时间|写入时间)[：:]\s*(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?\s*(?:\+08:00|北京时间))')
if ($FrTimes.Count -ne 1) { throw '37号复核时间缺失或歧义，停止' }
$FrTime = [DateTimeOffset]::Parse($FrTimes[0].Groups[1].Value.Replace('北京时间','+08:00'))
if ($FrTime -le [DateTimeOffset]'2026-11-07T12:00:00+08:00') { throw '37号复核时间太旧，停止' }
```

37号时间字段按上述格式核验；实际文件格式不同或有歧义就停，不能用文件修改时间代替。继续条件为同SHA CI success及37号明确放行；否则停止并提醒。

## B0–B1：本机固定包、引导文件与公开分词器

在下面固定clean候选树核验已经实际生成的包，不重新打包、不覆盖旧交付物。任一hash/候选不符即停止。

```powershell
$FrSha = 'bf6e0bbc720b85510d757b17d4ccd74ff60687bb'
$FrRepo = 'C:/Users/Administrator/Documents/Codex/zhiming-v4-release-candidate-20261107'
$FrPython = 'C:/Users/Administrator/Documents/Codex/zhiming-v4-release-prep/.venv-k3-local/Scripts/python.exe'
$FrTokenizer = 'C:/Users/Administrator/Documents/Codex/zhiming-v4/private/artifacts/kimi-k3-installer-20261023'
Set-Location $FrRepo
if ((git rev-parse HEAD) -ne $FrSha -or (git status --porcelain)) { throw '候选或clean状态不符' }
$FrDelivery = Join-Path $FrRepo "private/fr-stage-$FrSha"
$FrTar = Join-Path $FrDelivery 'release.tar.gz'
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $FrTar).Hash.ToLowerInvariant() -ne '3294003e56ca152b6de7f1127e68f850e25f4eb114b5b7478b1f810a7f46d59d') { throw '包hash不符' }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $FrDelivery 'bootstrap.py')).Hash.ToLowerInvariant() -ne '18cf1f19742ae49267087856110521a47b5a957afb7a8e5b5695bf6bfc67ce42') { throw '引导hash不符' }
& $FrPython -m tools.install_k3_tokenizer --destination $FrTokenizer --verify-only
if ($LASTEXITCODE -ne 0) { throw '公开分词器原件不符' }
$FrBound = Get-Content (Join-Path $FrDelivery 'delivery.json') -Raw | ConvertFrom-Json
if ($FrBound.candidate -ne $FrSha -or $FrBound.operation -ne 'bcac4df7780c4516') { throw '交付身份不符' }
```

主线用上述命令核delivery.json中的SHA、operation、两项hash；全部相等才采用下方固定参数，任一不符停止并提醒。交付包没有私有env/key/数据库。**不要SCP整个private目录。** Kimi key文件不在stage交付物中。

### B0.5：容量准备（独立短SSH，先于B1首个SSH）

11-07 的stage B1与生产D0都停在8GiB磁盘门且日志无原因。本块单独一个短会话、在B1之前执行：先只读打印 `df -Pk /` 与各包缓存体积（每项 `du` 限时60秒），再只清可再生成的包缓存——`pip cache purge`、`dnf clean all`、`npm cache clean --force`，以及固定路径 `/root/.local/share/pnpm/store`（服务器无pnpm命令，11-07即按此路径清理）——最后再打印 `df -Pk /`。node-gyp与Prisma缓存只打印不清。不碰任何release、venv、数据库、备份、uploads、tokenizer或operation目录；不建operation目录（B1要求它不存在），回执独占写到 `$FR_ROOT/capacity-$FR_ID-<UTC时间>.log`。单项清理失败只记 `CLEAN-FAILED` 并继续其他缓存，块末不判门，过门仍由B1的8GiB门决定；清完仍不足就停并【提醒用户】决定扩容或指定可归档对象，不降门、不删保留物。

```bash
set -euo pipefail
set -C
umask 077
FR_ID='bcac4df7780c4516'
[[ "$FR_ID" =~ ^[0-9a-f]{16}$ ]]
FR_ROOT=/root/zhiming-core-fr-stage
test "$(id -u)" = 0
test -d "$FR_ROOT"
test ! -L "$FR_ROOT"
FR_CAPACITY="$FR_ROOT/capacity-$FR_ID-$(date -u +%Y%m%dT%H%M%SZ).log"
: > "$FR_CAPACITY"
rec() { "$@" 2>&1 | tee -a "$FR_CAPACITY"; }
size() {
  if test -e "$1"; then
    if ! timeout 60 du -sxk -- "$1"; then echo "DU-TIMEOUT-OR-ERROR $1"; fi
  else
    echo "ABSENT $1"
  fi
}
FR_CACHES=(/root/.cache/pip /var/cache/dnf /root/.npm /root/.cache/node-gyp /root/.cache/prisma /root/.local/share/pnpm/store)
rec df -Pk /
for path in "${FR_CACHES[@]}"; do rec size "$path"; done
if command -v python3.11 >/dev/null && test -d /root/.cache/pip; then
  if ! rec python3.11 -m pip cache purge; then rec echo CLEAN-FAILED pip; fi
fi
if command -v dnf >/dev/null; then
  if ! rec dnf clean all; then rec echo CLEAN-FAILED dnf; fi
fi
if command -v npm >/dev/null; then
  if ! rec npm cache clean --force; then rec echo CLEAN-FAILED npm; fi
fi
FR_PNPM_STORE=/root/.local/share/pnpm/store
if test -d "$FR_PNPM_STORE" && ! test -L "$FR_PNPM_STORE" && ! test -L /root/.local/share/pnpm && ! test -L /root/.local/share; then
  if ! rec rm -rf --one-file-system -- "$FR_PNPM_STORE"; then rec echo CLEAN-FAILED pnpm-store; fi
fi
for path in "${FR_CACHES[@]}"; do rec size "$path"; done
rec df -Pk /
chmod 600 "$FR_CAPACITY"
echo "capacity record: $FR_CAPACITY; gate is decided by B1"
```

第一次短SSH只读确认 `df -Pk /` 可用至少8388608 KiB、Python3.11和PG15客户端存在、原服务与8788端口当前状态。确认新root和新unit均不存在后，才在F范围内创建新目录；若已有同名物停止，不接管。

```bash
set -euo pipefail
umask 077
FR_SHA='bf6e0bbc720b85510d757b17d4ccd74ff60687bb'
FR_ID='bcac4df7780c4516'
[[ "$FR_SHA" =~ ^[0-9a-f]{40}$ && "$FR_ID" =~ ^[0-9a-f]{16}$ ]]
FR_ROOT=/root/zhiming-core-fr-stage
df -Pk / >&2
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
test -d "$FR_ROOT"
for directory in uploads releases venvs tokenizer operations; do test -d "$FR_ROOT/$directory"; done
test ! -e /etc/systemd/system/zhiming-core-fr-stage-bcac4df7780c4516.service
test ! -e "$FR_ROOT/operations/$FR_ID"
test ! -e "$FR_ROOT/releases/$FR_SHA"
test ! -e "$FR_ROOT/venvs/$FR_SHA"
test ! -e "$FR_ROOT/tokenizer/$FR_SHA"
test ! -e "$FR_ROOT/uploads/$FR_ID"
FR_LISTEN="$(ss -H -ltn)"
if awk '$4 ~ /(^|:)8788$/ {found=1} END {exit !found}' <<<"$FR_LISTEN"; then echo '127.0.0.1:8788 already has a listener; stop' >&2; exit 1; fi
sha256sum "$FR_PG_EXE" "$FR_DUMP" "$FR_RESTORE" "$FR_PSQL" > "$FR_ROOT/pg-programs-$FR_ID.sha256"
mkdir -m 700 "$FR_ROOT/tokenizer/$FR_SHA" "$FR_ROOT/operations/$FR_ID" "$FR_ROOT/uploads/$FR_ID"
```

根分区不足8GiB（磁盘门前 `df -Pk /` 已打到stderr，停时日志可见实际可用量）、同名unit或operation路径存在均停止；既有root和旧operation保留，除B0.5列明的包缓存外不删旧物腾空间。固定副本库/writer名被11-07 afdfc占用的问题由B2.5改名保留解决，copy/provision的实际PG门再次核验。

回到本机，只上传三份公开交付物和lock列出的六个已核公开文件；下面是主线在执行准入满足后使用的传输命令；当前没有上传。

```powershell
scp -i 'C:/Users/Administrator/.ssh/gto_deploy_key' -- $FrTar (Join-Path $FrDelivery 'bootstrap.py') (Join-Path $FrDelivery 'delivery.json') 'root@1.14.59.242:/root/zhiming-core-fr-stage/uploads/bcac4df7780c4516/'
if ($LASTEXITCODE -ne 0) { throw '上传失败停止' }
$FrNames = (Get-Content 'k3-tokenizer.lock.json' -Raw | ConvertFrom-Json).files.PSObject.Properties.Name
$FrPublicFiles = @($FrNames | ForEach-Object { Join-Path $FrTokenizer $_ })
scp -i 'C:/Users/Administrator/.ssh/gto_deploy_key' -- @FrPublicFiles "root@1.14.59.242:/root/zhiming-core-fr-stage/tokenizer/$FrSha/"
if ($LASTEXITCODE -ne 0) { throw '公开分词器上传失败停止' }
```

## B2：核包、独立环境、短会话公共命令

每次新短SSH重设已审的FR_SHA/FR_ID及下列路径；不能从新的HEAD自动取号。hash使用本机delivery原件中的已审核值，不能只信服务器同目录可改的JSON。

```bash
set -euo pipefail
set -C
umask 077
FR_SHA='bf6e0bbc720b85510d757b17d4ccd74ff60687bb'
FR_ID='bcac4df7780c4516'
[[ "$FR_SHA" =~ ^[0-9a-f]{40}$ && "$FR_ID" =~ ^[0-9a-f]{16}$ ]]
FR_ROOT=/root/zhiming-core-fr-stage
FR_OP="$FR_ROOT/operations/$FR_ID"
FR_UPLOAD="$FR_ROOT/uploads/$FR_ID"
FR_RELEASE="/root/zhiming-core-fr-stage/releases/$FR_SHA"
FR_PY="$FR_ROOT/venvs/$FR_SHA/core/bin/python"
FR_TOKENIZER="$FR_ROOT/tokenizer/$FR_SHA"
FR_ADMIN=/root/zhiming-core-secrets/fr-stage-bcac4df7780c4516-admin.env
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
sha256sum -c "$FR_ROOT/pg-programs-$FR_ID.sha256"
FR_PACKAGE_SHA='3294003e56ca152b6de7f1127e68f850e25f4eb114b5b7478b1f810a7f46d59d'
FR_BOOTSTRAP_SHA='18cf1f19742ae49267087856110521a47b5a957afb7a8e5b5695bf6bfc67ce42'
h() { sha256sum "$1" | cut -d ' ' -f 1; }
```

首次准备：两hash均须64hex且匹配，解包只允许全新release。只装Core锁，不混旧requirements-web.lock/Charts环境。不启动任何服务。

```bash
[[ "$FR_PACKAGE_SHA" =~ ^[0-9a-f]{64}$ && "$FR_BOOTSTRAP_SHA" =~ ^[0-9a-f]{64}$ ]]
test "$(h "$FR_UPLOAD/release.tar.gz")" = "$FR_PACKAGE_SHA"
test "$(h "$FR_UPLOAD/bootstrap.py")" = "$FR_BOOTSTRAP_SHA"
python3.11 -I "$FR_UPLOAD/bootstrap.py" --candidate "$FR_SHA" --artifact "$FR_UPLOAD/release.tar.gz" --artifact-sha256 "$FR_PACKAGE_SHA" --release "$FR_RELEASE"
test ! -e "$FR_ROOT/venvs/$FR_SHA"
mkdir -m 700 "$FR_ROOT/venvs/$FR_SHA"
```

venv创建、锁依赖安装应后台单步运行并留exit/log，不在长SSH会话等。下面公共函数可用于任意固定参数的长命令，未产生exit文件只表示未完成，不能进入下一步。函数不重试任何步骤，同名日志/pid/exit一律拒绝覆盖。

```bash
start_step() {
  local name="$1"; shift
  [[ "$name" =~ ^[a-z0-9-]+$ ]]
  for ext in log pid exit; do test ! -e "$FR_OP/$name.$ext"; done
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
paths=[parent/'fr-stage-bcac4df7780c4516-admin.env',parent/'fr-prod-admin.env']
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
test -f "$FR_ADMIN"
test ! -L "$FR_ADMIN"
test "$(stat -c '%a %u' "$FR_ADMIN")" = '600 0'
test "$(stat -c '%a %u' "$(dirname "$FR_ADMIN")")" = '700 0'
```

上述文件使用单字段URI DSN；若已有文件不是该受支持格式，停止审查而不覆盖。任意错误输出只记录步骤失败，不复制SQL/口令/原stderr；不现场安装软件或修改认证。

## B2.5：改名保留上次stage副本（独立短SSH，B3 copy之前）

候选工具的副本库名与writer名固定（见“范围与现有证据”）。11-07 afdfc99790984105（候选6d803bff）留下的 `zhiming_core_fr_stage`（OID 70807，见 `private/stage-afdfc99790984105/` 的exchange current_oid、block-13.2 runtime receipt database_oid、block-18 finish seal）与 `zhiming_core_fr_stage_writer`（OID 72548，block-13.2 writer_oid）必须先改名保留，不删除、不改口令、不撤授权；授权与库级/角色库级SET按OID随对象保留。本块在B2的dependencies成功、R28之后、`start_step copy` 之前单独一个短会话执行，只用B2的FR_PY与FR_ADMIN（单字段URI DSN）以psycopg autocommit连接：先断言两个旧unit均不在运行（inactive或failed且MainPID=0）、8788无监听；库存在且OID=70807、datallowconn=false，除autovacuum worker外0会话（最多等300秒，只等autovacuum，出现其他会话立即停，不terminate）；writer存在且OID=72548、0会话；两个目标名都不存在；同时持有与exchange工具相同的 `fr-exchange:zhiming_core_fr_stage` advisory锁。然后在同一事务内改名库与writer，复核OID与新名，独占写 `$FR_OP/stage-6d803bff-preserved.json`，打印 `B25_RENAMED`。改名提交之前的任一断言失败即停，现场不变；提交之后（复核或写回执时）中断则两个对象已改名、回执缺失：重发本块时先识别这一“已完成”状态（70807名为 `zhiming_core_fr_stage_6d803bff` 且仍closed、72548名为 `zhiming_core_fr_stage_6d803bff_writer`、两个旧名都不存在、回执不存在），跳过改名只补写回执并打印 `B25_ALREADY_RENAMED` / `B25_RECEIPT_AFTER_EARLIER_COMMIT`，其余状态照旧逐项断言。回执已存在说明已执行过，本块拒绝重跑。改名后afdfc私有runtime.json里的旧writer名不再可用于登录，该unit保持inactive，仅作证据保留。

```bash
set -euo pipefail
set -C
umask 077
FR_SHA='bf6e0bbc720b85510d757b17d4ccd74ff60687bb'
FR_ID='bcac4df7780c4516'
[[ "$FR_SHA" =~ ^[0-9a-f]{40}$ && "$FR_ID" =~ ^[0-9a-f]{16}$ ]]
FR_ROOT=/root/zhiming-core-fr-stage
FR_OP="$FR_ROOT/operations/$FR_ID"
FR_RELEASE="/root/zhiming-core-fr-stage/releases/$FR_SHA"
FR_PY="$FR_ROOT/venvs/$FR_SHA/core/bin/python"
FR_ADMIN=/root/zhiming-core-secrets/fr-stage-bcac4df7780c4516-admin.env
test -d "$FR_OP"
test -x "$FR_PY"
test -d "$FR_RELEASE"
test "$(cat "$FR_OP/dependencies.exit")" = 0
test -f "$FR_ADMIN"
test ! -L "$FR_ADMIN"
test "$(stat -c '%a %u' "$FR_ADMIN")" = '600 0'
for ext in log pid exit; do test ! -e "$FR_OP/copy.$ext"; done
test ! -e "$FR_OP/stage-6d803bff-preserved.json"
for unit in zhiming-core-fr-stage-afdfc99790984105.service zhiming-core-fr-stage.service; do
  state="$(systemctl show -p ActiveState --value "$unit")"
  pid="$(systemctl show -p MainPID --value "$unit")"
  echo "$unit ActiveState=$state MainPID=$pid"
  test "$state" = inactive -o "$state" = failed
  test "$pid" = 0
done
FR_LISTEN="$(ss -H -ltn)"
if awk '$4 ~ /(^|:)8788$/ {found=1} END {exit !found}' <<<"$FR_LISTEN"; then echo '127.0.0.1:8788 already has a listener; stop' >&2; exit 1; fi
"$FR_PY" -I - "$FR_RELEASE" "$FR_ADMIN" "$FR_OP" <<'PY'
import json,sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from tools.first_release_hermes_entry import _private_read,_parse_environment
from tools.first_release_native_exchange import write_private
admin=_parse_environment(_private_read(Path(sys.argv[2])))
assert set(admin)=={'FIRST_RELEASE_EXCHANGE_ADMIN_DSN'}
fields=conninfo_to_dict(admin['FIRST_RELEASE_EXCHANGE_ADMIN_DSN'])
assert fields.get('host') in ('127.0.0.1','::1') and fields.get('port')=='5432' and fields.get('dbname')=='postgres'
OP=Path(sys.argv[3])
OLD_DB,NEW_DB,DB_OID='zhiming_core_fr_stage','zhiming_core_fr_stage_6d803bff',70807
OLD_ROLE,NEW_ROLE,ROLE_OID='zhiming_core_fr_stage_writer','zhiming_core_fr_stage_6d803bff_writer',72548
WAIT_SECONDS=300
with psycopg.connect(admin['FIRST_RELEASE_EXCHANGE_ADMIN_DSN'],autocommit=True,row_factory=dict_row) as c:
 r=c.execute("SELECT current_database() AS db,current_user=session_user AS same,inet_server_port() AS port,current_setting('server_version_num')::int AS version,(SELECT rolsuper FROM pg_roles WHERE rolname=session_user) AS su").fetchone()
 assert r['db']=='postgres' and r['same'] and r['port']==5432 and 150000<=r['version']<160000 and r['su']
 assert c.execute("SELECT pg_try_advisory_lock(hashtextextended('fr-exchange:zhiming_core_fr_stage',0)) AS held").fetchone()['held'],'stage exchange tool holds the lock; stop'
 by_oid_db=c.execute('SELECT datname,datallowconn FROM pg_database WHERE oid=%s',(DB_OID,)).fetchone()
 by_oid_role=c.execute('SELECT rolname FROM pg_roles WHERE oid=%s',(ROLE_OID,)).fetchone()
 old_db_left=c.execute('SELECT 1 FROM pg_database WHERE datname=%s',(OLD_DB,)).fetchone() is not None
 old_role_left=c.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(OLD_ROLE,)).fetchone() is not None
 # An earlier run may have committed both renames and stopped before its receipt; recognise that state only.
 completed=bool(by_oid_db and by_oid_db['datname']==NEW_DB and by_oid_role and by_oid_role['rolname']==NEW_ROLE and not old_db_left and not old_role_left)
 if completed:
  assert by_oid_db['datallowconn'] is False,'preserved database is open; stop'
  print('B25_ALREADY_RENAMED: both renames were committed earlier and no receipt exists; renames skipped, writing receipt only',flush=True)
 else:
  db=c.execute('SELECT oid::int AS oid,datallowconn FROM pg_database WHERE datname=%s',(OLD_DB,)).fetchone()
  assert db and db['oid']==DB_OID and db['datallowconn'] is False,'old stage database is not the closed 11-07 OID; stop'
  role=c.execute('SELECT oid::int AS oid FROM pg_roles WHERE rolname=%s',(OLD_ROLE,)).fetchone()
  assert role and role['oid']==ROLE_OID,'old stage writer is not the 11-07 OID; stop'
  assert not c.execute('SELECT 1 FROM pg_database WHERE datname=%s',(NEW_DB,)).fetchone(),'preserve database name already taken; stop'
  assert not c.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(NEW_ROLE,)).fetchone(),'preserve role name already taken; stop'
  assert c.execute('SELECT count(*) AS n FROM pg_stat_activity WHERE usesysid=%s',(ROLE_OID,)).fetchone()['n']==0,'old stage writer has sessions; stop, nothing terminated'
  end=time.monotonic()+WAIT_SECONDS;seen=set()
  while True:
   rows=c.execute('SELECT pid,backend_type FROM pg_stat_activity WHERE datid=%s',(DB_OID,)).fetchall()
   other=[x for x in rows if x['backend_type']!='autovacuum worker']
   assert not other,'old stage database has a session other than autovacuum; stop, nothing terminated'
   if not rows:break
   seen.update(x['pid'] for x in rows)
   assert time.monotonic()<end,'old stage database not at 0 sessions after 300s; stop'
   time.sleep(2)
  print('old stage database at 0 sessions; autovacuum workers seen while waiting:',len(seen),flush=True)
  with c.transaction():
   c.execute("SET LOCAL lock_timeout='2s'")
   c.execute(sql.SQL('ALTER DATABASE {} RENAME TO {}').format(sql.Identifier(OLD_DB),sql.Identifier(NEW_DB)))
   c.execute(sql.SQL('ALTER ROLE {} RENAME TO {}').format(sql.Identifier(OLD_ROLE),sql.Identifier(NEW_ROLE)))
  after_db=c.execute('SELECT datname,datallowconn FROM pg_database WHERE oid=%s',(DB_OID,)).fetchone()
  after_role=c.execute('SELECT rolname FROM pg_roles WHERE oid=%s',(ROLE_OID,)).fetchone()
  assert after_db['datname']==NEW_DB and after_db['datallowconn'] is False and after_role['rolname']==NEW_ROLE
  assert not c.execute('SELECT 1 FROM pg_database WHERE datname=%s',(OLD_DB,)).fetchone()
  assert not c.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(OLD_ROLE,)).fetchone()
result={'status':'previous_stage_preserved_not_deleted','source_operation':'afdfc99790984105','source_candidate':'6d803bff9832f2a9582c09d25e0a6b9c6207dddc','database':{'old':OLD_DB,'new':NEW_DB,'oid':DB_OID,'datallowconn':False},'writer':{'old':OLD_ROLE,'new':NEW_ROLE,'oid':ROLE_OID},'sessions_terminated':0,'objects_deleted':0,'renamed_in_this_run':not completed}
write_private(OP/'stage-6d803bff-preserved.json',result)
print('B25_RECEIPT_AFTER_EARLIER_COMMIT' if completed else 'B25_RENAMED',json.dumps(result,sort_keys=True))
PY
```

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
systemd-analyze verify "$FR_OP/zhiming-core-fr-stage.service" > "$FR_OP/verify-stage.log" 2>&1
# R49: set -e requires verify exit0 before this exact whitelist check.
python3.11 -I - "$FR_OP/verify-stage.log" <<'PY'
import pathlib,re,sys
patterns=(
 r'/etc/systemd/system/tat_agent\.service:[0-9]+: PIDFile= references a path below legacy directory /var/run/, updating /var/run/tat_agent\.pid → /run/tat_agent\.pid; please update the unit file accordingly\.',
 r'/usr/lib/systemd/system/(?:ip6tables|iptables)\.service:[0-9]+: Standard output type syslog is obsolete, automatically updating to journal\. Please update your unit file, and consider removing the setting altogether\.',
)
for line in pathlib.Path(sys.argv[1]).read_text(encoding='utf-8').splitlines():
 if not line.strip():continue
 assert any(re.fullmatch(pattern,line) for pattern in patterns),'R49 non-exempt verify output; stop'
 print(line)
PY
test ! -e /etc/systemd/system/zhiming-core-fr-stage-bcac4df7780c4516.service
# set -C的独占重定向保护已有unit；不使用覆盖式install/cp。
(umask 022; cat "$FR_OP/zhiming-core-fr-stage.service" > /etc/systemd/system/zhiming-core-fr-stage-bcac4df7780c4516.service)
test "$(h /etc/systemd/system/zhiming-core-fr-stage-bcac4df7780c4516.service)" = "$(h "$FR_OP/zhiming-core-fr-stage.service")"
systemctl daemon-reload
fr tools.first_release_stage_runtime admit --operation "$FR_ID" --workspace "$FR_OP" --receipt "$FR_OP/runtime-receipt.json" --receipt-sha256 "$(h "$FR_OP/runtime-receipt.json")" --admin-env-file "$FR_ADMIN" --apply
systemctl start zhiming-core-fr-stage-bcac4df7780c4516.service
test "$(systemctl show -p ActiveState --value zhiming-core-fr-stage-bcac4df7780c4516.service)" = active
systemctl show zhiming-core-fr-stage-bcac4df7780c4516.service -p MainPID -p ControlGroup -p IPAddressDeny -p IPAddressAllow -p RestrictAddressFamilies -p SocketBindAllow -p SocketBindDeny
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
FR_CGROUP="$(systemctl show -p ControlGroup --value zhiming-core-fr-stage-bcac4df7780c4516.service)"
test "$FR_CGROUP" = /system.slice/zhiming-core-fr-stage-bcac4df7780c4516.service
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
        assert sys.argv[1]=='/system.slice/zhiming-core-fr-stage-bcac4df7780c4516.service'
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
systemctl stop zhiming-core-fr-stage-bcac4df7780c4516.service
test "$(systemctl show -p ActiveState --value zhiming-core-fr-stage-bcac4df7780c4516.service)" = inactive
fr tools.first_release_native_exchange capture --operation "$FR_ID" --admin-env-file "$FR_ADMIN" --metadata "$FR_OP/finish-metadata.json" --output "$FR_OP/finish-capture.json"
fr tools.first_release_native_exchange seal --operation "$FR_ID" --admin-env-file "$FR_ADMIN" --metadata "$FR_OP/finish-metadata.json" --metadata-sha256 "$(h "$FR_OP/finish-metadata.json")" --output "$FR_OP/finish-sealed.json"
```

不自动恢复/重启，不移除维护门或删除任何备份/库/unit。Linux实际执行人负责一页以内回执：最终SHA/operation、每步exit/用时/安全结果、偏差或第一失败码、实际模型/外发次数0、原stage/live/Hermes未改、最终closed/inactive状态。没有实际执行的项目写“未验证”，不据本机测试补造Linux结果。生产执行单仍未放行，按独立31号窗口核D范围及原生生产目标入口。
