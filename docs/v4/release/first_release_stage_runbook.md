# 首发 F 副本 stage 执行单（候选2200485）

2026-10-25 04:58，北京时间。命令和固定交付物绑定候选 `220048573110862d378015c35d99a37c0d83503e`，工作树 `C:/Users/Administrator/Documents/Codex/zhiming-v4-r39`。包hash `9478c42966d98150c71307950702aff6a8d4b751f370041e2d66d23dc71c94ff`，bootstrap hash `18cf1f19742ae49267087856110521a47b5a957afb7a8e5b5695bf6bfc67ce42`，operation `ba63f7b2fa8a405d`。R11原件：`C:\Users\Administrator\Documents\Codex\zhiming-v4-r39\private\r11-run-c38bd9e6b67744e387d110627f7e7ef6\metadata.json`，assessment：`C:\Users\Administrator\Documents\Codex\zhiming-v4-r39\private\candidate-eval\220048573110862d378015c35d99a37c0d83503e\R11-58e3c43c0c33414cbe1b2d60e3d786ff\assessment.json`。此时R11仍在途；CI未核、五题定向真实复测未运行、37号Go缺失，执行准入尚未满足，不能宣布stage/首发就绪。

执行人：**主线**。只有本聊天具备直接人类F授权、37号首行 `结论：Go` 且复核晚于2026-10-24 12:30、候选40位SHA与本单一致，才进入下列服务器步骤。指令板和37号本身不扩大服务器权限。生产仍另需直接D授权与31号Go窗口，本文不操作生产。当前未SSH/上传/执行服务器命令。

## 范围与现有证据

原 `zhiming_core_stage` 只有只读备份；演练只用新 `zhiming_core_fr_stage` 及 `zhiming_core_fr_<operation>_restore/failed`。仅新 `zhiming-core-fr-stage.service`、127.0.0.1:8788，无模型/中央凭据，飞书/报告/公网反代不启动。原stage/live/Hermes不改、不停、不删。禁止freeze/install/publish、旧库clean恢复、Docker/代理/WSL/ACL修复。

恢复/复制/回填、B7和运行资产的唯一本机原件索引见[恢复计划14:00–14:19四活节](../execplans/first_release_recovery_20261023.md)。各定向轮次分别通过；不称一次完整Linux链。stage模型端口明确拒绝请求，真实Agent/公开K3/PG装配只开放健康、状态、历史，原Web子app队列/dispatcher/维护worker不启动。这不是模型或常驻队列验收。

|门|当前结论|
|---|---|
|同一首发源码、CI、R11|本单绑定2200485包/R11原件；R11完成需根核，CI未核，不复用旧候选批准|
|新库保owner/ACL/设置与0连接对调|本机必要门已解除，证据见恢复计划；Linux结果由本单实际执行记录|
|副本迁移/回填/撤销收据及空增量B7|本机必要门已解除；不得把副本旁账称为生产停写后最新旁账|
|无模型新角色/8788资产/维护栅栏|本机必要门已解除；systemd、cgroup和Linux解释器仍须现场核验|
|F/37、容量、凭据与目标全新|执行前由大脑核；任一缺失即停止，不从文件自授权限|

任何**非预设负验**异常：立刻停，保持当前库/门/文件，记日报；不修补重试、覆盖、删除或杀PG会话。SSH每次一个短会话；拒绝等10分钟最多3次。耗时动作后台，后续短连只读检查结果；前一步未明确exit0不得执行下一步。备份/操作目录0700、文件0600、保留14天，不自动清理。回滚只在开门之前，B7只做空增量；开门后只关闭新服务准入，不回退数据。

## B0–B1：本机固定包、引导文件与公开分词器

在下面固定clean候选树核验已经实际生成的包，不重新打包、不覆盖旧交付物。任一hash/候选不符即停止。

```powershell
$FrSha = '220048573110862d378015c35d99a37c0d83503e'
$FrRepo = 'C:/Users/Administrator/Documents/Codex/zhiming-v4-r39'
$FrPython = 'C:/Users/Administrator/Documents/Codex/zhiming-v4/.venv-k3/Scripts/python.exe'
$FrTokenizer = 'C:/Users/Administrator/Documents/Codex/zhiming-v4/private/artifacts/kimi-k3-installer-20261023'
Set-Location $FrRepo
if ((git rev-parse HEAD) -ne $FrSha -or (git status --porcelain)) { throw '候选或clean状态不符' }
$FrDelivery = Join-Path $FrRepo "private/fr-stage-$FrSha"
$FrTar = Join-Path $FrDelivery 'release.tar.gz'
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $FrTar).Hash.ToLowerInvariant() -ne '9478c42966d98150c71307950702aff6a8d4b751f370041e2d66d23dc71c94ff') { throw '包hash不符' }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $FrDelivery 'bootstrap.py')).Hash.ToLowerInvariant() -ne '18cf1f19742ae49267087856110521a47b5a957afb7a8e5b5695bf6bfc67ce42') { throw '引导hash不符' }
& $FrPython -m tools.install_k3_tokenizer --destination $FrTokenizer --verify-only
if ($LASTEXITCODE -ne 0) { throw '公开分词器原件不符' }
$FrBound = Get-Content (Join-Path $FrDelivery 'delivery.json') -Raw | ConvertFrom-Json
if ($FrBound.candidate -ne $FrSha -or $FrBound.operation -ne 'ba63f7b2fa8a405d') { throw '交付身份不符' }
```

大脑审核delivery.json中的SHA、operation、两项hash，作为后续固定参数。交付包没有私有env/key/数据库。**不要SCP整个private目录。** Kimi key文件不在stage交付物中。

第一次短SSH只读确认 `df -Pk /` 可用至少8388608 KiB、Python3.11和PG15客户端存在、原服务与8788端口当前状态。确认新root和新unit均不存在后，才在F范围内创建新目录；若已有同名物停止，不接管。

```bash
set -euo pipefail
umask 077
FR_SHA='220048573110862d378015c35d99a37c0d83503e'
FR_ID='ba63f7b2fa8a405d'
[[ "$FR_SHA" =~ ^[0-9a-f]{40}$ && "$FR_ID" =~ ^[0-9a-f]{16}$ ]]
FR_ROOT=/root/zhiming-core-fr-stage
awk 'NR==2 {exit !($4>=8388608)}' < <(df -Pk /)
command -v python3.11 sha256sum
/usr/lib/postgresql/15/bin/pg_dump --version
/usr/lib/postgresql/15/bin/pg_restore --version
! test -e "$FR_ROOT"
! test -e /etc/systemd/system/zhiming-core-fr-stage.service
! ss -ltn | awk '{print $4}' | grep -Eq '(^|:)8788$'
mkdir -m 700 "$FR_ROOT"
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
FR_SHA='220048573110862d378015c35d99a37c0d83503e'
FR_ID='ba63f7b2fa8a405d'
[[ "$FR_SHA" =~ ^[0-9a-f]{40}$ && "$FR_ID" =~ ^[0-9a-f]{16}$ ]]
FR_ROOT=/root/zhiming-core-fr-stage
FR_OP="$FR_ROOT/operations/$FR_ID"
FR_RELEASE="$FR_ROOT/releases/$FR_SHA"
FR_PY="$FR_ROOT/venvs/$FR_SHA/core/bin/python"
FR_TOKENIZER="$FR_ROOT/tokenizer/$FR_SHA"
FR_ADMIN=/root/zhiming-core-secrets/fr-stage-admin.env
FR_DUMP=/usr/lib/postgresql/15/bin/pg_dump
FR_RESTORE=/usr/lib/postgresql/15/bin/pg_restore
FR_PACKAGE_SHA='9478c42966d98150c71307950702aff6a8d4b751f370041e2d66d23dc71c94ff'
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

大脑先备妥其已审的PG管理员私有文件FR_ADMIN：仅`FIRST_RELEASE_EXCHANGE_ADMIN_DSN`一个字段，实际PG15 superuser、数字回环127.0.0.1或::1、5432、控制库postgres；不能用业务writer替代、不要输出正文。文件/父目录须root所有0600/0700，无链接；工具会核实际身份。缺文件/凭据即停请大脑处理，不能自动建账户/改认证绕过。长步骤原始日志均在0700操作目录，禁止上传包含私有数据或凭据的日志正文。

```bash
test "$(stat -c '%a %u' "$FR_ADMIN")" = '600 0'
test "$(stat -c '%a %u' "$(dirname "$FR_ADMIN")")" = '700 0'
```

## B3–B5：只读复制、迁移与primary回填/副本旁账重放

```bash
start_step copy "${FR_RUN[@]}" tools.first_release_stage_copy --operation "$FR_ID" --workspace "$FR_OP" --pg-dump "$FR_DUMP" --pg-dump-sha256 "$(h "$FR_DUMP")" --pg-restore "$FR_RESTORE" --pg-restore-sha256 "$(h "$FR_RESTORE")" --admin-env-file "$FR_ADMIN" --apply
# check_step copy 明确0，核copy-receipt.status=copied_closed后：
start_step prepare "${FR_RUN[@]}" tools.first_release_stage_prepare --operation "$FR_ID" --workspace "$FR_OP" --copy-receipt "$FR_OP/copy-receipt.json" --copy-receipt-sha256 "$(h "$FR_OP/copy-receipt.json")" --admin-env-file "$FR_ADMIN" --apply
```

`check_step prepare`明确0；prepare-receipt须prepared_closed、migrations完整1–8/checksum匹配、backfill_repeat的message_metadata/search_tokens/assistant_created全0、replay_full_state_unchanged=true、model_calls/external_sends=0。source/target OID必须来自同次copy；不手改receipt、started或任何数据来放行。缺primary、旧未核checksum、无run_id/冲突收据等真实错误均停止。

## B7：开门前空增量新库恢复与改名对调

新服务和writer均尚未创建。使用迁移后的新副本做空增量备份；不是恢复原stage旧前缀，也不在已迁移库执行clean。

```bash
fr tools.first_release_native_exchange capture --operation "$FR_ID" --admin-env-file "$FR_ADMIN" --metadata "$FR_OP/rollback-before.json" --output "$FR_OP/capture-receipt.json"
start_step backup "${FR_RUN[@]}" tools.first_release_stage_backup --operation "$FR_ID" --workspace "$FR_OP" --metadata "$FR_OP/rollback-before.json" --metadata-sha256 "$(h "$FR_OP/rollback-before.json")" --pg-dump "$FR_DUMP" --pg-dump-sha256 "$(h "$FR_DUMP")" --admin-env-file "$FR_ADMIN" --apply
# check_step backup 明确0，核backed_up_closed后：
start_step restore "${FR_RUN[@]}" tools.first_release_native_exchange restore --operation "$FR_ID" --admin-env-file "$FR_ADMIN" --metadata "$FR_OP/empty-delta-metadata.json" --metadata-sha256 "$(h "$FR_OP/empty-delta-metadata.json")" --backup "$FR_OP/empty-delta.dump" --backup-sha256 "$(h "$FR_OP/empty-delta.dump")" --pg-restore "$FR_RESTORE" --pg-restore-sha256 "$(h "$FR_RESTORE")" --output "$FR_OP/restore-receipt.json"
# check_step restore 明确0，核restored_new_database后：
fr tools.first_release_native_exchange seal --operation "$FR_ID" --admin-env-file "$FR_ADMIN" --metadata "$FR_OP/empty-delta-metadata.json" --metadata-sha256 "$(h "$FR_OP/empty-delta-metadata.json")" --output "$FR_OP/seal-receipt.json"
fr tools.first_release_native_exchange exchange --operation "$FR_ID" --admin-env-file "$FR_ADMIN" --metadata "$FR_OP/empty-delta-metadata.json" --metadata-sha256 "$(h "$FR_OP/empty-delta-metadata.json")" --restore-receipt "$FR_OP/restore-receipt.json" --restore-receipt-sha256 "$(h "$FR_OP/restore-receipt.json")" --output "$FR_OP/exchange-receipt.json"
```

继续条件：exchange-receipt为exchanged_closed，current_oid为新恢复库OID，failed_database为本operation唯一failed名，admission_opened/old_database_deleted/production均false。两库必须保持closed/0连接；旧failed库和全部备份保留。owner、CONNECT ACL/授权选项、库级及角色库级SET由捕获原件恢复。任何活动会话/元数据漂移/已有目标都立即停，不终止PG会话。新writer和任何应用开门后不再执行本节回滚。

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

出站核验必须检查**实际新unit cgroup**，不是另建transient unit。以下仅大脑在F内做TCP连通正负验，不发任何应用层payload，不访问模型/飞书；外部正验自身不可达时本项不能证明阻断，停止交大脑核。子进程只把自己加入已确认的新unit cgroup，退出后不留进程、不动其他cgroup。

```bash
FR_CGROUP="$(systemctl show -p ControlGroup --value zhiming-core-fr-stage.service)"
test "$FR_CGROUP" = /system.slice/zhiming-core-fr-stage.service
"$FR_PY" -I - "$FR_CGROUP" <<'PY'
import errno,os,pathlib,socket,sys
endpoint=('1.1.1.1',443)
with socket.create_connection(endpoint,timeout=3):
    pass
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

不自动恢复/重启，不移除维护门或删除任何备份/库/unit。Linux实际执行人负责一页以内回执：最终SHA/operation、每步exit/用时/安全结果、偏差或第一失败码、实际模型/外发次数0、原stage/live/Hermes未改、最终closed/inactive状态。没有实际执行的项目写“未验证”，不据本机测试补造Linux结果。生产执行单仍未放行，需用户另给D及另审原生生产目标入口。
