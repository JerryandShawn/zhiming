# 核心首发 stage 执行草案（B0–B8）

2026-10-24 11:56，北京时间。**No-Go / 草案：尚不能照本单完成部署。** 新显式本机源写CLI的默认早拒/零副作用与prefix7非空完整链已首次两目标通过；只证明本机 `main(argv)` 真实调用，不等于Linux应用进程、正式恢复或最终候选通过。源replay/回填及新CLI的实际archive、范围、原失败和唯一证据统一见[增量ExecPlan](../execplans/first_release_incremental_20261024.md)，不重复归档。正式集成`f6fb9f1`原push/PR的M1会话失败仍保留，额外PID原因未知，不能用本机通过消除；新捕获须重新审核含observer和admission的10控pin。正式apply、Linux应用、原中央保全、全局writer、切换和开门均未放行，工具头不是最终发布SHA。本单没有授权或执行服务器、模型或飞书动作。

本单取代首发范围内旧B1执行建议，不改写旧证据。旧授权B/D已取消；stage和生产分别需要用户对最终SHA、对象、窗口、动作与止损范围的新授权。大脑复核或本文件存在均不能代替该授权。当前不执行任何SSH、建库、备份、服务或网络动作。

v13范围收窄：本单尚未就绪。指令板记录的F仅限原stage的只读备份→新`zhiming_core_fr_stage`副本及演练库间恢复对调；原stage/live/Hermes不改、不删除。服务只能新`zhiming-core-fr-stage.service`、127.0.0.1:8788、独立无模型凭据env、禁止出站、飞书关闭、不启动报告/反代，健康/状态/历史冒烟0模型。旧下表涉及原stage或Hermes的通用步骤不能套用F；当前正式工具固定目标也不接受此新副本，须先完成对应受审入口。开始还需本聊天直接新授权、37号首行Go且复核晚于10-24 12:30、当前容量≥8GiB；不从文件自授SSH。v12已取消Docker拉镜像/数据库演练投入，36号服务器数据库结果仅是大脑提供的证据，不能代替应用Linux验收。

R16新增审核资产使用固定候选`config/models.first-release.yaml`，共同env明确`MODELS_CONFIG`指向该文件；主与外部评审均k3.1-pro/high，原default/v3与旧k3/k3-256k配置保留。只有新OpenAI原生路径发送显式high并在内容前核真实响应model；Anthropic K3.1路径未核wire，发送前拒绝。当前仅Mock验证，不是账号接入或新评测授权。F的无模型stage不得注入密钥或调用该配置做效果评测。

## 1. 候选与安全边界

v14分工：真实评测及服务器stage均交大脑执行，本代理只完成必要代码与本地隔离验证。以下新R2接口已具备必要Windows PG15/独立进程证据，但整个执行单仍未就绪：最终候选打包、原stage只读备份→副本、Linux迁移/重放/回填/新unit串联的精确命令仍须补齐。不能把本节当成37号Go或服务器执行许可。

首发按当前`core-only-1-8-v1`契约覆盖P1/P1b/P2/P3、旧网页兼容和现有文字飞书入口；P4/P6及新前端不在此单。当前要求迁移0001–0008精确连续且checksum不变。P5若达到就绪门并纳入候选，须另审含0009的profile、关系/routine清单、恢复工具及本单，不能以忽略0009绕过现契约。

最终审核输入至少包括：精确Git候选SHA、规范Git blob发布manifest原始SHA、artifact SHA、迁移八项hash、`requirements-core.lock`、`requirements-charts.lock`、`k3-tokenizer.lock.json`、模型配置及依赖工具commit/hash。最终候选或任一运行源码变化后，已有候选脚本/质量/恢复证据须重新判断绑定关系，不拼凑不同来源的通过报告。

这是已有Core PG的增量路径：不重跑旧SQLite/JSON导入，不使用`deploy_core freeze/install/publish`迁移已有库，不使用硬编码live的`restore-withdrawals`。旧B1控制器、proof及Linux SQL drill仍固定b9、迁移1–7；它们的apply命令不能换个SHA直接用于本单，也不能把旧授权带过来。

0008中央额度账本独立于业务时间和恢复点：不回退usage/attempt/batch/stop，不清空或provision账户来通过启动门，不复用生产凭据或伪造account、ledger identity及实际PG location。若账本位置随恢复库变化、备份包含旧账本，必须有另审的保全与重绑定方案；目前没有该入口，届时停止。

所有故障保持当前维护/停写状态，保留私有产物与安全错误码，交大脑复核；不自行修好重试、不覆盖或删除旧库/容器卷/备份。时间均为Asia/Shanghai，测试不能依赖机器时区。本文所有耗时是排期估计，不是测得RTO。

## 2. 必须解除的门（当前全部未放行）

| 门 | 当前事实与缺口 | 放行所需 |
| --- | --- | --- |
| 候选身份 | 最终候选、manifest、artifact及外部审核pin待冻结 | 同一候选的明确审核、来源与必要评测；不能手填admissible |
| 实际Linux运行时 | 现有Windows PG定向证据只证明相应逻辑；Linux Core/Charts/K3未整体验证 | Python3.11双环境、锁依赖/导入来源、真实文件权限、官方K3本地小文件及网络隔离 |
| 增量与恢复 | 正式入口仍仅validate/可选只读ACL；本机Forward4/7、prefix7同call源重放及回填组合已有实证，正式恢复仍缺失 | 将已验证本机内部链接入受审正式入口，再补Linux、全局writer及既有中央身份保全 |
| 停写与切换 | 最终Web/飞书/报告+timer、Hermes wrapper及维护/锁尚未联合演练 | 实际Linux完整进程寿命writer栅栏、部分失败保持关门、所有入口同源 |
| 当前环境及授权 | 未做新的服务器盘点；容量、旧schema/服务状态不能沿用历史值 | 用户新的stage授权，明确新对象/窗口；获准后只读B0复核一致 |

关系/函数/ACL校验通过不代表数据已恢复、运行时已受信、中央账本已合法迁移或渠道已验收；本单不将任一门标为“已解除”。

### R2新库恢复与改名对调：明确接口，尚未服务器执行

工具`tools.first_release_native_exchange`只允许新首发副本`zhiming_core_fr_stage`，其他演练库名称由固定16位operation派生；不能指向原`zhiming_core_stage`、live或生产。先由大脑按F停新stage unit/所有该副本writer并核维护门。使用已经审核的同候选Core环境、B7空增量备份（备份后无新业务写入）与独立私有管理员文件；该文件只能含`FIRST_RELEASE_EXCHANGE_ADMIN_DSN`，固定回环5432/控制库postgres/实际PG15超级用户，不把DSN写进命令。操作前确认备份与目录0700/0600，保留14天，不自动清理。

下面变量在本次审核执行上下文中绑定；缺少任何变量立即停止。只允许一次生成operation，失败后不能换ID重试。`FR_R2_BACKUP`必须是前一步审核过的精确dump，不能临时换成另一份。

```bash
set -eu
: "${FR_RELEASE:?}" "${FR_R2_BACKUP:?}" "${FR_BACKUP_DIR:?}"
FR_PY="$FR_RELEASE/venv/core/bin/python"
FR_ADMIN_FILE=/root/zhiming-core-secrets/fr-stage-admin.env
FR_PG_RESTORE=/usr/lib/postgresql/15/bin/pg_restore
test -f "$FR_PG_RESTORE"
FR_OP=$("$FR_PY" -I -c 'import secrets; print(secrets.token_hex(8))')
FR_R2_DIR="$FR_BACKUP_DIR/r2-$FR_OP"
umask 077
mkdir -m 700 "$FR_R2_DIR"
FR_METADATA="$FR_R2_DIR/database-metadata.json"
FR_DUMP_SHA=$(sha256sum "$FR_R2_BACKUP" | cut -d' ' -f1)
FR_PG_RESTORE_SHA=$(sha256sum "$FR_PG_RESTORE" | cut -d' ' -f1)
fr_exchange() {
  "$FR_PY" -I -c 'import sys; sys.path.insert(0,sys.argv.pop(1)); from tools.first_release_native_exchange import main; raise SystemExit(main())' \
    "$FR_RELEASE" "$@" --operation "$FR_OP" --admin-env-file "$FR_ADMIN_FILE" --metadata "$FR_METADATA"
}
```

分步执行，每一步非零或`status=blocked`立即停并保留全部对象，不继续后续命令、不改权限修重试。不得打印metadata或env正文。工具只支持libc locale及单属主grantor的库ACL；其他形态明确拒绝并交大脑复核。

```bash
fr_exchange capture --output "$FR_R2_DIR/capture.json"
FR_METADATA_SHA=$(sha256sum "$FR_METADATA" | cut -d' ' -f1)
```

继续条件：`metadata_captured`，当前副本OID/PG系统身份和owner、全部库ACL（含CONNECT/PUBLIC/授权选项）、库级及角色库级设置已保存并将被后续逐项重核。此步不改库。

```bash
fr_exchange restore --metadata-sha256 "$FR_METADATA_SHA" \
  --backup "$FR_R2_BACKUP" --backup-sha256 "$FR_DUMP_SHA" \
  --pg-restore "$FR_PG_RESTORE" --pg-restore-sha256 "$FR_PG_RESTORE_SHA" \
  --output "$FR_R2_DIR/restore.json"
```

继续条件：`restored_new_database`，真实pg_restore只写新`zhiming_core_fr_<operation>_restore`且保对象owner/ACL，不使用clean/create/no-owner/no-acl；新库恢复库级元数据后关闭连接准入。目标已存在、输入/身份漂移或恢复失败均留现场，不能接管目标或重试。

```bash
fr_exchange seal --metadata-sha256 "$FR_METADATA_SHA" --output "$FR_R2_DIR/seal.json"
```

继续条件：`closed_zero_connections`。只关闭副本新连接准入，不强制断开任何会话；仍有客户端时停止并保持关门，不杀会话。新旧两库的准入关闭及0连接在下一事务内再核。

```bash
FR_RESTORE_RECEIPT_SHA=$(sha256sum "$FR_R2_DIR/restore.json" | cut -d' ' -f1)
fr_exchange exchange --metadata-sha256 "$FR_METADATA_SHA" \
  --restore-receipt "$FR_R2_DIR/restore.json" --restore-receipt-sha256 "$FR_RESTORE_RECEIPT_SHA" \
  --output "$FR_R2_DIR/exchange.json"
```

继续条件：`exchanged_closed`。一个PG事务中旧副本→`zhiming_core_fr_<operation>_failed`、新库→`zhiming_core_fr_stage`，重新施加并核验原库owner/ACL/设置，旧失败库保留；两库仍不开放连接。工具不改unit/env/中央位置、不删除或重新开门。B7后是否允许重新开放副本及启动新unit，必须由后续明确步骤核schema/候选兼容后处理，本节不自动执行。正式生产对调尚无入口，此限定stage工具不能拿掉限制用于live。

### 原中央与新业务库的配置接缝（不放行正式门）

现有P1b按独立中央设计：业务仓库读取 `ZHIMING_DATABASE_URL`，中央守卫只读取 `MEMBER_CENTRAL_DSN`、`MEMBER_CENTRAL_SCHEMA`、`MEMBER_ACCOUNT_ID`、`MEMBER_LEDGER_IDENTITY`，不回退业务DSN。若已有正确中央，恢复业务到新库时可仅切业务DSN，保留原中央四项与实际PG位置，不把备份中的中央表当作权威。普通启动和每次物理请求都核原账号UUID与实际数据库/server/port/schema位置；旧中央改名、迁址或换schema须另审，禁止靠provision、改location/identity、clear stop修过启动门。若尚无中央账号，先停在门前，待另审的显式配置及授权；runtime不能自动创建。

本机已用真实prefix7恢复至8、原非空中央历史、当前宿主生产装配/Registry及受限角色验证该路由：允许调用只向原中央追加，错误库/UUID/位置及已有停机拒绝，新业务额度表保持空。这里只替换传输为Mock，未注入guard绕路；完整唯一结果在[恢复ExecPlan](../execplans/first_release_recovery_20261023.md)。这不是fresh候选进程、完整Agent业务run、正式权限或配置切换验收，`central_binding_verified`保持false。正式切换仍须保全原四表/sequence完整基线、明确原中央库/角色长期保留与旧业务writer处置、审核实际受保护env，并在同候选Linux和所有入口重核；不能据构造guard成功推断旧usage/stop未回退。

### 固定服务入口与进程寿命栅栏（组件，不放行停写门）

`tools.first_release_service` 是新的同进程入口，固定 `web`、`feishu`、`report`、`hermes` 四个角色。默认只校验已有路径和显式 writer 配置形状，零 PG、零业务导入、零进程启动和零写；实际运行必须显式加 `--run`。它不加载管理员或 owner DSN、不建角色或栅栏文件、不改维护标记，也不替代候选审核。限定真实PG15/子进程首链3/3通过，范围及唯一原件统一见[服务栅栏 ExecPlan](../execplans/first_release_service_fence_20261024.md)；只是原生 MemoryService 接缝验证，四个完整应用和Linux均未验收，不能解除正式门。

以下只是静态校验的真实参数形状，变量须来自未来受审配置，不能照填任意 OID 或拿它执行服务器动作：

```bash
cd "$FR_CANDIDATE_ROOT"
"$FR_CORE_PYTHON" -m tools.first_release_service \
  --role web --candidate "$FR_CANDIDATE_ROOT" --workspace "$FR_FENCE_WORKSPACE" \
  --system-identifier "$FR_SYSTEM_IDENTIFIER" --database "$FR_DATABASE" \
  --database-oid "$FR_DATABASE_OID" --writer "$FR_WRITER" --writer-oid "$FR_WRITER_OID"
```

候选根必须是 launcher 自己所在的普通源码根；Web 固定单 worker、无 reload、127.0.0.1:8787，不接受其他原生参数。报告及 Hermes 的原生参数只能在 `--` 后；Hermes 的 stdout 仍完全交原业务，不追加包装回执。`ZHIMING_DATABASE_URL` 只含该受限 writer 的显式数字 TCP 地址/端口、数据库、用户和口令，不允许 PG 隐式路由、DSN options/service/passfile 或管理员凭据。实际运行核 PG15、SID、数据库/OID、session/current writer/OID、真实位置及无 owner/DDL 权能；若缺 `pg_control_system()` EXECUTE 则拒绝，只能由另审步骤给予该函数的精确权限，不能加广泛监控角色或自动授权。

所有入口必须使用同一受保护 `FR_FENCE_WORKSPACE`，与 M1/Forward 的稳定文件和 PG key 一致。两个共享锁取得且维护标记不存在后才导入/调用业务；原入口 finally 完成后，仍持双锁刷新输出并真实结束整个进程，避免后台线程活着时先解锁。PG 专用连接丢失仍保留文件锁。这个退出方式可能中断尚未排空的投递或后台任务，不能证明外部请求已经取消，也不自动重试或补发；必须结合运行/Outbox 状态另审排空与止损。

旧 unit、Hermes wrapper、其他 CLI 和外部子进程尚未统一纳管；下文已补本机“关闭新准入→旧服务自然退出→M1显式采用原标记”接线，但实际停止服务、门内 readiness、移除标记及开门尚未编排。M1 仍须取得两个 EX，旧进程未退出就拒绝；不能据 launcher 或关闭准入成功声称全局停写。Linux 权限/进程链和四个完整应用的联合运行仍待验证，B0–B8 与五个门继续 No-Go。

### 首发服务审核资产（只在本机生成，尚未安装）

`tools.first_release_service_assets` 生成三份固定 service、Hermes `core_consultation.py`、共同的无秘密配置/环境片段和 manifest，共七个文件。它不生成 timer、不运行 systemctl、不更新真实 unit、技能目录或链接。原 timer 的 effective 文件、drop-in、active/enabled 及到期任务仍待审核，不能把“保留且保持停止”的清单策略当成已执行的状态。

输入 schema 为 `first-release-service-assets-v1`，精确字段为 `candidate`、`workspace`、`system_identifier`、`database`、`database_oid`、`writer`、`writer_oid`、`report_owner`、有序的两个 `env_files`、`config_path`、`common_env_path`、`k3_tokenizer_dir`。这些值须由最终审核输入给定；生成时只检查 Linux 字面路径和身份格式，不查询真实 SID/OID，不认证候选或环境存在。Core/Charts 解释器由同一 SHA 固定推导。秘密只引用原受保护文件，不写入此配置、argv 或 manifest；不能写入 `local_projection` 或 Go 标记。

以下是现有本机接口，`FR_ASSETS_OUTPUT` 必须是当前控制工作目录 `private/` 内尚不存在的绝对目录；没有最终审核输入时不运行：

```bash
cd "$FR_CONTROL_DIR"
"$FR_CONTROL_PYTHON" -m tools.first_release_service_assets \
  --config "$FR_ASSET_PLAN" --output "$FR_ASSETS_OUTPUT"
"$FR_CONTROL_PYTHON" -m tools.first_release_service_assets \
  --config "$FR_ASSET_PLAN" --output "$FR_ASSETS_OUTPUT" --write-assets-local
```

默认零 PG/启动/写入；显式写入使用新目录和独占文件，失败保留现存产物，不覆盖、不清理重试。三 service 和 wrapper 共用固定 Core `-I` 薄入口，再进入原受限 writer/双锁 launcher；报告 owner 明确传递，Hermes 原参数按数组传递。共同环境固定 Agent=true、运行容量3、池4及独立 CHART/K3 路径，不强制开启飞书，不重写原四项 MEMBER 中央身份。实际运行才按声明顺序读取受保护环境及精确共同片段；非隔离解释器、隐式 PG/Python 注入或保护模式不符均拒绝。Windows 权限不能代替 POSIX 验收。

本片的限定实证与未覆盖范围仅登记在[服务资产 ExecPlan](../execplans/first_release_service_assets_20261024.md)。资产是供审核的安装输入，不是 installer、effective unit、Linux 应用运行或切换回执；五个门继续 No-Go。

## 3. 现有可运行的校验命令

以下仅描述已有接口，**本轮没有运行**。所有变量须先由审核输入绑定为绝对路径；不从任意env文件source，不在argv放口令、DSN、token或正文。`FR_CONTROL_DIR`是含已审工具的目录，`FR_CONTROL_PYTHON`是其固定解释器。未有正式候选和pin时先停，不能用合成测试pin代替。

```bash
cd "$FR_CONTROL_DIR"
"$FR_CONTROL_PYTHON" -m tools.first_release_restore \
  --pin "$FR_PIN" --contract "$FR_CONTRACT"
```

默认只有文件/契约校验，PG连接数0、mutations=0。外部pin格式为`first-release-pin-v1`，契约为`first-release-restore-contract-v1`；字段以[源码契约](../../../tools/first_release_contracts.py)为准，不能多加通过布尔位。正式源码路径固定`/root/zhiming-core-releases/<最终SHA>`；本机模式须显式`local_drill=true`，且源码位于当前工作目录的`private/first-release-<operation随机标识>/<SHA>`。本机模式的成功不是Linux放行。

正式允许的新恢复目标仅`zhiming_core_first_restore`及对应`_owner`/`_writer`；本机仅`fr_restore_<operation随机标识>`。该目标不是原stage库，也不是可用于任意数据库的模板。当前工具不创建这些对象，目标不存在时不能自动创建。

未来恢复apply还须证明目标为空且属于本次操作。stage完成后应保留恢复副本；同机生产若遇到同名已占用目标，先停下另审独立目标/契约，不删除或覆盖stage副本来腾位置。

当且仅当本机测试范围或新的stage授权允许、且独立恢复库已通过另审步骤建立后，可增加：

```bash
"$FR_CONTROL_PYTHON" -m tools.first_release_restore \
  --pin "$FR_PIN" --contract "$FR_CONTRACT" --check-acl
```

只由受保护加载器注入`FIRST_RELEASE_OWNER_DSN`与`FIRST_RELEASE_WRITER_DSN`；角色/库/loopback/端口必须一致，实际进程及显式环境均不得夹带PG隐式路由变量。工具各开一次只读事务，先固定并核验`search_path=pg_catalog`，检查真实PG15身份、精确关系/routine、额度表/列/序列权限、两个迁移账本只读及checkpoint DML；不修授权、不迁移、不重放。该入口不接受原stage/live DSN，不能拿它直接扫描业务库。

正常输出始终`runtime_verified=false`、`linux_attestation=false`、`native_restore_completed=false`、`publication=false`，没有`admissible=true`。外部pin被视为可信审核输入，但工具不认证审核人、pin保护模式、真实Git tree归属或审核新鲜度，这些仍由发布审查负责。`--apply`、`--native`及`--action migrate`均不是此入口的命令。

本机最终干净checkout的打包接口已存在；冻结之后才可按审核路径运行，打包不等于部署：

```bash
"$FR_CONTROL_PYTHON" tools/deploy_core.py bundle \
  --commit "$FR_SHA" --release-dir "/root/zhiming-core-releases/$FR_SHA" \
  --source "$FR_CLEAN_CHECKOUT" --artifact "$FR_LOCAL_ARTIFACT"
```

构建要求checkout HEAD与SHA一致、工作树干净。不得将测试库、凭据、备份、真实正文或未跟踪运行目录打进发布包。

## 4. B0–B8：动作、继续与停止条件

### 本机新入口（不能替代B3/B7）

`tools.first_release_local_restore`已提供本机原始prefix恢复基础。外部同源审核dump-pin为`first-release-local-dump-pin-v1`，绑定候选/manifest、custom dump及PG15 pg_restore原始hash、源迁移前缀；只接受1–7，实际验证4或7。示例为已存在接口，不表示现在授权服务器执行：

```bash
cd "$FR_CONTROL_DIR"
"$FR_CONTROL_PYTHON" -m tools.first_release_local_restore \
  --pin "$FR_PIN" --contract "$FR_CONTRACT" --dump-pin "$FR_LOCAL_DUMP_PIN" \
  --dump "$FR_LOCAL_BACKUP_DUMP" --pg-restore "$FR_LOCAL_PG_RESTORE"
```

默认只读文件、0PG/0子进程；显式`--apply-local`才创建本次随机新库/新owner和writer并实际恢复。必须local_drill=true，dump固定在本次operation目录的backup.dump，管理DSN仅同一loopback 55480/55481的postgres/core_test_main控制库。任何既有目标库或任一角色均拒绝；失败保留新对象，再调用拒绝接管，不清理重跑。应用前实际TOC检查拒绝中央额度表，即使dump-pin谎称prefix7也不复制0008。

新public初始化仅在本次新库/新owner匹配、public为空且原owner为pg_database_owner时进行，不放宽NOINHERIT或writer权限。角色DDL只提交客户端生成的SCRAM verifier，口令和verifier均不进回执。实际pg_restore由新owner执行no-owner/no-acl/exit-on-error/single-transaction/no-password；默认随后只核原prefix和owner。

同一命令显式增加`--apply-local --upgrade-local`，才在该调用持锁新建且恢复的目标继续：再次核候选SQL和历史、一个事务前向至8、独立autocommit阶段checkpoint setup、复用最小授权、两角色精确只读ACL。正常总连接7，默认路径仍4；没有采用现成库的单独入口。0008四表必须实际为空，非空立即停止并保留，不清表或provision；空表不代表中央账本合法保全/重绑定。任一阶段失败保留其已提交现场，不修权限重试；不重放撤销/收据。成功仍保持正式native_restore_completed、linux_attestation、publication为false。本机新升级窄链11/11及原恢复证据见原ExecPlan，不新增证据副本。B3/B7所需正式全链仍缺失。

本机同次新库还可显式增加以下候选只读预检；这是已有参数的完整组合，不能去掉apply/upgrade后用于采用现成库：

```bash
"$FR_CONTROL_PYTHON" -m tools.first_release_local_restore \
  --pin "$FR_PIN" --contract "$FR_CONTRACT" --dump-pin "$FR_LOCAL_DUMP_PIN" \
  --dump "$FR_LOCAL_BACKUP_DUMP" --pg-restore "$FR_LOCAL_PG_RESTORE" \
  --apply-local --upgrade-local --replay-preflight-local \
  --preflight-pin "$FR_LOCAL_PREFLIGHT_PIN" \
  --preflight-ledger "$FR_LOCAL_LATEST_WITHDRAWALS" --candidate-python "$FR_CANDIDATE_PYTHON"
```

外部预检pin使用`first-release-local-preflight-pin-v1`，绑定同一候选/manifest/dump、最新旁账、实际Python可执行文件和受审控制worker的hash。候选Python必须是实际Python3.11 venv，并满足Core锁在该平台激活的版本及依赖闭包；只有锁文件相同不够。该新子进程拒绝预载控制树业务包，实际导入并核候选业务来源，只以新owner进行额外1次只读连接，正常总连接8。预检通过仅表示源码/已装依赖元数据/目标迁移和owner全集/空运行队列与中央空表核验；不调用apply_withdrawals，`latest_withdrawals_replayed`、`runtime_verified`、`native_restore_completed`、`linux_attestation`、`publication`仍为false。失败保留新目标，不自动重试或清理。证据只登记在原恢复ExecPlan；此命令不解除B3/B7或实际Linux门。

另有经过隔离PG验证的显式本机双重放入口，只接受原备份prefix4或7。它与上述只读预检模式互斥，使用独立`first-release-local-replay-pin-v1`并额外绑定受审effects helper的hash：

```bash
"$FR_CONTROL_PYTHON" -m tools.first_release_local_restore \
  --pin "$FR_PIN" --contract "$FR_CONTRACT" --dump-pin "$FR_LOCAL_DUMP_PIN" \
  --dump "$FR_LOCAL_BACKUP_DUMP" --pg-restore "$FR_LOCAL_PG_RESTORE" \
  --apply-local --upgrade-local --replay-withdrawals-local \
  --replay-pin "$FR_LOCAL_REPLAY_PIN" \
  --replay-ledger "$FR_LOCAL_LATEST_WITHDRAWALS" --candidate-python "$FR_CANDIDATE_PYTHON"
```

仍只操作同call新建且持锁的本机目标，正常总连接9。子进程先只读核目标，再调用实际候选的原生apply/export；每次apply保留其原事务与提交后checkpoint清理边界。旁账不能比已恢复状态旧，第二次apply后的全部Core/checkpoint字段、sequence及导出必须与第一次相同，中央四表及sequence保持原空状态。实际测试含当前已提交候选的非空撤销/收据/墓碑，以及真实旧候选因状态变化或正文残留被拒的负例，没有向旧包注入修复。独立后验已覆盖whole撤销、draw、revoked-run checkpoint、真实legacy映射目标及受支持直接派生，另有原生更正source_span和whole fact组合的独立样本，验证保留原话、上下文/实际FTS遮挡、非重叠事实及运行私密清理。备份后才新增再更正的原话可在实际零同owner血缘时保留marker-only，单列计数，不冒称已擦除原文；孤立残留、损坏引用和无法归属形态仍保守拒绝，不借另一owner证明身份。其他片段形态和全部间接血缘仍未验证；证据统一见原恢复ExecPlan。失败保留并停止，不自动再试。成功只标记本机候选重放，中央身份保全、运行时、正式native恢复、Linux和publication仍为false；不能据此解除B7整链。

**B7的新库恢复证明必须在B3修改已有stage库之前完成。** 表中缺失入口不是待猜命令，不能用旧B1 apply或手工SQL补过门。只要必要入口缺失，停在本地准备阶段。

### 本机已有合成库备份（M1，不能替代stage停写）

下列真实入口仅接受本机55480/55481、已存在的`fr_upgrade_<operation>`合成库与原prefix4或7。独立`first-release-local-incremental-backup-pin-v1`绑定实际系统/库/角色OID、owner全集、候选/manifest/三锁、Python、PG15 pg_dump及受审控制文件；`FIRST_INCREMENTAL_OWNER_DSN`、`FIRST_INCREMENTAL_WRITER_DSN`和同一服务器控制库的`FIRST_INCREMENTAL_ADMIN_DSN`只从受保护环境加载。

```bash
"$FR_CONTROL_PYTHON" -m tools.first_release_incremental --pin "$FR_LOCAL_INCREMENTAL_PIN"
"$FR_CONTROL_PYTHON" -m tools.first_release_incremental --pin "$FR_LOCAL_INCREMENTAL_PIN" --backup-local
```

第一条默认0连接/0进程/0文件写；第二条才取得合作性文件/PG栅栏，保留维护标记，实际生成同一MVCC快照的custom dump、候选原生旁账与独立前后状态证据。错误OID、额外会话、活动run/lease、锁冲突、已有输出或源漂移均停止，保留已写产物，不自动清理重试；锁释放不解除维护。新固定launcher已接同一协议，但旧实际入口尚未联合纳管，前后会话检查不证明dump期间全局停写，`global_quiescence_verified=false`。成功仅为`backup_captured`，不能据JSON回执采用既有恢复库、迁移源库或解除B2/B3/B7、Linux、中央身份和发布门。原实际8/8与独立marker写阻断1/1见[增量ExecPlan](../execplans/first_release_incremental_20261024.md)，不重复归档证据。

若需要先阻新服务再排空旧进程，新增两阶段**本机**接口如下；只在允许的合成库上使用，不能据此操作服务器：

```bash
"$FR_CONTROL_PYTHON" -m tools.first_release_incremental --pin "$FR_LOCAL_INCREMENTAL_PIN" --close-admission-local
```

该命令在既有文件 SH 与 PG SH 内核实际身份，O_EXCL/fsync 写原格式维护标记。旧服务仍可持 SH 继续，回执 `admission_closed=true`、`drained=false`，不得当作已停写。已有标记一律拒，不建锁文件，不停 unit、不等待重试。审核确认该合成样本旧进程已自然退出后，另一次显式调用：

```bash
"$FR_CONTROL_PYTHON" -m tools.first_release_incremental --pin "$FR_LOCAL_INCREMENTAL_PIN" --backup-local --use-admission
```

只有 `--use-admission` 才采用同 operation/DBOID 且普通文件、字节和inode/mtime/hash始终未变的标记；不覆盖它，仍须两个 EX 和全部原会话/busy/源状态/同快照门。未加采用旗标的旧备份继续拒任何既有标记；任一 backup-started/dump/ledger/receipt 已存在就拒重入，真实进程错误后保留现场、新服务继续拒，不自动清理或恢复。

本片新helper纳入M1控制hash，当前严格为10项，旧9项pin不能补字段/改hash自动升级，必须重新审核新输入。三条新行为及唯一受影响旧prefix4行为首次4/4；真实 native 旧服务→关闭准入→新服务拒→旧退出→实际M1采集和真实pg_dump失败保留、原guard材料兼容的唯一证据统一见[准入接线ExecPlan](../execplans/first_release_admission_20261024.md)。业务archive与控制源码分开记录，不冒称最终同候选验收；源0008、正式库、Linux及全局/发布位依旧关闭。

### 本机捕获与原始恢复绑定（M2）

新捕获显式使用UTC行投影，包含逻辑列集合及同次实际核验输入的`capture_lineage`。只接受`source_projection=postgres-jsonb-utc-v1`的新真实产物；旧无UTC/列/血缘的回执不能补字段或改hash后冒充。本次M1输入的逐字节副本固定为其operation目录的`capture-inputs.json`，独立`first-release-local-capture-binding-pin-v1`绑定它、receipt、dump、旁账、完整状态、候选/manifest、另一新恢复operation与消费控制文件。

```bash
"$FR_CONTROL_PYTHON" -m tools.first_release_local_restore \
  --pin "$FR_PIN" --contract "$FR_CONTRACT" --dump-pin "$FR_LOCAL_DUMP_PIN" \
  --dump "$FR_LOCAL_BACKUP_DUMP" --pg-restore "$FR_LOCAL_PG_RESTORE" \
  --apply-local --upgrade-local --capture-bind-local \
  --capture-inputs "$FR_LOCAL_CAPTURE_INPUTS" --capture-pin "$FR_LOCAL_CAPTURE_BINDING_PIN"
```

比较在同call新目标creator锁内、实际原始恢复后且任何升级之前执行：实际owner/原prefix/关系、逻辑列和全部原字段行hash精确相等，sequence集合及last_value/is_called相等；保留源log_cnt证据，不伪造跨恢复日志计数相等。任一异常保留原目标且不升级；默认不加绑定参数仍0连接。上面的命令只增加嵌套`local_original_content_verified`，不执行latest撤销/收据重放，也不证明源库捕获后未再变化；源库升级、全局停写、正式恢复、Linux、中央身份和发布仍未放行。真实证据为首链3项通过、必要失败复验3项通过、合法profile两正例2项通过，不冒称一次8/8；两轮失败与修正均在原增量ExecPlan保留。

同次原始恢复比较和候选原生双重放还可明确组合，两个独立pin都必须完整提供：

```bash
"$FR_CONTROL_PYTHON" -m tools.first_release_local_restore \
  --pin "$FR_PIN" --contract "$FR_CONTRACT" --dump-pin "$FR_LOCAL_DUMP_PIN" \
  --dump "$FR_LOCAL_BACKUP_DUMP" --pg-restore "$FR_LOCAL_PG_RESTORE" \
  --apply-local --upgrade-local --capture-bind-local \
  --capture-inputs "$FR_LOCAL_CAPTURE_INPUTS" --capture-pin "$FR_LOCAL_CAPTURE_BINDING_PIN" \
  --replay-withdrawals-local --replay-pin "$FR_LOCAL_REPLAY_PIN" \
  --replay-ledger "$FR_LOCAL_LATEST_WITHDRAWALS" --candidate-python "$FR_CANDIDATE_PYTHON"
```

这条组合已在真实本机PG15的prefix7样本完成1/1定向验证：先真实更正，再M1捕获含新更正事实和三类物理checkpoint的原始状态；另一新目标先M2比较，再升级至8和实际候选双重放，最后才核擦除及完整第二遍不变。新更正事实、原话、非重叠事实、另一owner和源库完整状态保持，三类checkpoint从各1行清至0。复杂blob由明确合成SDK种子生成，未向重放注入结果。前两次新fixture阶段语义错误及最后通过均见[原恢复ExecPlan](../execplans/first_release_recovery_20261023.md)，不称首次全绿、全部样本或Linux通过；源库升级和正式各门仍关闭。

### 本机目标证明与源升级组件（正式源写入口未就绪）

以下为基线后逐片实现/验证的开发组件；本机完整入口见后节，组件本身不提供正式源升级命令。每轮实际候选archive、控制代码与原始失败/修正统一见[原增量ExecPlan](../execplans/first_release_incremental_20261024.md)，不另归档日志或合并不同轮次为一次全绿；不能把它们拼成同一最终发布包通过证据。

| 组件 | 本机已验证范围 | 仍关闭的门 |
| --- | --- | --- |
| same-call TargetProof | 八个独立行为按4+3+1分轮通过，另旧public M2 prefix7兼容1；同次新目标真实原始内容绑定→8→候选双重放后，核创建时OID、最终ACL/完整状态，creator锁内mint并单次消费，消费失败也耗尽token | 不透明对象不能由JSON重建；正常目标链16连接。仅可在下述实际Forward组合内消费，不单独赋予源写权；正式恢复仍未完成，先前session setup拒绝来源仍未知 |
| Source guard | 12个独立行为分轮验证（纯文件1、真实PG夹具11）；真实Windows独占锁内改用同一持锁句柄读fence，保持默认锁行为及精确文件身份/hash、实际源OID/权限/会话/完整UTC状态核验 | 只读scope仍要求源capture不变，不返回写连接或升级许可；旧实际入口尚未接全合作栅栏，不能证明全局停写或Linux完整进程寿命行为 |
| Source postcheck | 七个独立行为按6+1分轮通过，验证真实4/7测试夹具前向8后的原字段/列、完整迁移账本及owner/writer精确终态；两个正例均实际调用SDK setup，版本10→10、新增0 | 不是源升级入口，尚未覆盖存在待应用SDK迁移的升级；不因新增版本0声称setup未执行或零SQL，不自动修复异常状态 |
| SourceForward内部API及本机CLI | 真实4/7同call目标证明、controller核验、源双栅栏与Core/SDK/grant组合已有实证；独立pin已接prefix7实际源隐私双重放及后续源回填。新显式main的默认/坏材料与非空prefix7全链首次2/2，保维护标记，未知提交停止不重入 | 不是Linux应用进程验收；应用全局停写与正式门仍未证明 |
| 源重放worker及接线 | 独立组件4/4；新同call组合保留首1红1绿及规范UTC后仅原红1绿，真实SourceWitness内完成双重放、活lease/父终态ACK和末段独立业务/状态/导出核验 | 分轮证据见原计划，不称一次2/2；初始连接失败/控制故障注入与Linux未覆盖 |
| 回填effects及源接线 | core3精确逐值/第二遍无写与异常整事务回滚2/2；core4历史缺口及撤销后不复活另2/2。独立pin/fresh worker已在原活witness内接到源replay之后，受影响正反两目标于07:07共同2/2，首遍回填两条历史、第二遍三个写计数0，closed及完整后验成立 | 原失败与各轮archive分别保留，只索引原计划；不把Windows本机、组件或成功dict当作Linux/正式恢复/发布能力 |

Forward内部已有prefix7源隐私重放→回填的完整本机闭环，显式本机CLI的两条必要行为已完成上述限定验收。上文针对同call新`fr_restore`目标的双重放接口保持原范围。源隐私重放须先于回填，不能跳过。公开回执的`source_write_authorized`、全局停写、正式native/runtime/Linux、中央身份保全和publication继续关闭；内部活witness的一次性源写许可不等于这些公开发布位，Windows PG结果及组件测试均不构成stage或生产授权。

### 本机完整源写命令（仅本机合成库）

新增开发入口为 `tools.first_release_source_forward`，只选择原完整链，不增加授权或证明协议。所有输入路径均须绝对路径：原M1的 `capture-inputs.json` / capture pin、独立的目标release / contract / dump pin、原custom dump、真实PG15 `pg_restore`、候选Core Python与最新撤销账本/replay pin，以及TargetProof、controller runtime、Forward、源replay、源backfill五份独立受审pin。不可用JSON中的成功位、旧恢复目标或手填输出替代这些材料；控制代码变化后重新审核pin，不能自动更新hash继续。

在本次合成工作区根目录，用pin绑定的同一Core Python3.11虚拟环境调用。只设受保护的 `FIRST_INCREMENTAL_OWNER_DSN` / `WRITER_DSN` / `ADMIN_DSN` 和 `FIRST_RELEASE_OWNER_DSN` / `WRITER_DSN` / `ADMIN_DSN`，不在命令行或记录中放DSN。原路由继续只允许同一回环55480/55481、既有本次 `fr_upgrade_<id>` prefix4/7源及同call新建 `fr_restore_<id>`，目标不可已存在；这不是stage或生产入口。

参数集合固定为下列15项：`--pin`、`--contract`、`--dump-pin`、`--dump`、`--pg-restore`、`--capture-inputs`、`--capture-pin`、`--candidate-python`、`--replay-ledger`、`--replay-pin`、`--target-proof-pin`、`--controller-runtime-pin`、`--forward-pin`、`--source-replay-pin`、`--source-backfill-pin`。没有最后两份pin时连默认校验也拒绝。默认调用 `python -B -m tools.first_release_source_forward <上述文件参数>`，预期仅文件校验、连接/进程/文件写均0；唯一执行旗标是加 `--apply-source-local`，不能选择跳过撤销重放或回填。

执行顺序仍是源维护/双栅栏→同次新目标恢复证明→controller运行时→源Core/SDK/最小授权→源原生撤销/收据双重放→源回填双遍→closed及完整后验。成功保留源维护标记，`source_forward_completed=true`、`privacy_replay_pending=false`、`backfill_pending=false`；公开正式位全部仍false。任一异常返回2及有界无正文错误码/phase、实际session恢复投影和 `automatic_cleanup=false`，保留源、目标与材料，不自动清理、解除维护或重试。唯一真实PG首链约15.6分钟（含夹具、有效默认验证和完整执行），只索引增量ExecPlan原件，不是测得RTO；实际验证为方法级 `main(argv)`，没有称Linux可执行进程已验。Linux应用、正式恢复、中央身份保全、全局writer及切换依旧另需验收和用户新授权。

| 步骤 | 动作与当前入口 | 继续条件 | 停止条件 | 预计耗时 |
| --- | --- | --- | --- | --- |
| B0 | 新授权后只读盘点主机、PG15/实际schema前缀、角色、服务/反代、队列、磁盘和备份；命令范围见下文 | 目标、旧包、schema/checksum、owner范围及容量与审核输入一致；所有目标名称明确 | 无新授权、环境漂移、低于受审容量预算、未知writer/旧任务 | 10–20分 |
| B1 | 本机冻结最终候选并规范打包；§3 validate；受审渠道传包/准备双环境的首发入口待补 | manifest/三锁/1–8一致；实际Linux Core、Charts、K3来源与权限均验过 | 依赖/额外文件/解释器不符；最终包未定；只有Windows或元数据证据 | 30–60分，下载另计 |
| B2 | 保持stage停写，取得stage专属writer栅栏，精确备份与导出最新无正文旁账；首发控制器缺失 | 队列/lease/其他写会话为0；dump、原schema、状态摘要、撤销/收据及配置可绑定 | 无停写证据、来源读取依赖源库尚无的表、备份或导出失败 | 15–30分 |
| B3 | B7已通过后才允许已有库前向迁至8、checkpoint setup及最小授权；首发apply入口缺失 | 原checksum合法连续前缀，目标八项精确一致；新恢复证据同源 | 任何迁移/身份/ACL异常；禁止改历史迁移或补多余DELETE | 10–20分 |
| B4 | 对明确获准owner dry-run→审核→apply→repeat；首发回填控制器缺失 | repeat的message_metadata/search_tokens/assistant_created均0，其他只读计数可非0；原文/来源/牌面/撤销/收据不变；未获准owner只核计数 | repeat写变化、丢正文或固定牌、owner越界、收据回退 | 10–40分 |
| B5 | 最终候选同源的必要脚本与定向回归；只用可丢弃验收库、替身传输；不在实际stage历史库跑测试 | 首发脚本/集成证据已满足当前门，无未解释失败/跳过；来源一致 | 假目标代替v4、旧报告凑绿、测试连业务库、触发真实供应商/消息 | 30–60分，按规模修正 |
| B6 | 独立合成Web库/owner/writer/目录/端口/unit与实际出站封锁；首发装配/启动资产待补 | Agent实际启用且替身装配受审；loopback PG阳性/同cgroup出站阴性有对照；历史与记忆回执等行为通过 | 借live env/目录/中央身份，关闭Agent只验旧health，网络封锁未实证或有待恢复真实任务 | 20–45分 |
| B7 | B2精确dump恢复到新allowlist库→核原前缀→前向1–8→最新撤销/收据重放两次→§3只读ACL；正式stage恢复/replay控制器缺失 | 非空deleted_draws墓碑可再导出、owner隔离；sent/uncertain不重发；checkpoint清除；第二遍无变化；中央账本不回退 | 复用旧b9恢复、覆盖stage/live、过期旁账、中央账户重建、任一状态/权限/提交后checkpoint异常 | 30–60分起 |
| B8 | 一份stage回执，绑定候选/工具/配置与每步证据和实际耗时，交大脑审核 | 所有必要门真实完成，停止状态和未验证项明确 | 输入或步骤缺失仍写stage accepted；自动进入生产 | 10–20分 |

B0获准后的现有只读命令可包括`hostname`、`date --iso-8601=seconds`、`df -B1 --output=avail /`、`ss -lnt`及对**授权所列精确stage units**的`systemctl show`（Id/ActiveState/UnitFileState/FragmentPath/DropInPaths/NeedDaemonReload）。不打印Environment、完整DSN、私钥、正文；PG安全投影工具/当前参数未核准时停止，不临时拼接含口令命令。

容量以本次盘点和实测数据库/备份/双环境/恢复副本占用加余量计算；不能因历史磁盘已清理就认定充足。首次整体准备暂按3–5小时估计，缺失实现、审核和依赖等待另计；不能承诺维护时间或RTO。

## 5. B6/B7还缺的具体内容

独立合成环境需分别批准测试DDL库、Web库与恢复库的精确新名称和角色。当前validator只支持恢复目标，不存在通用`--stage`部署参数。旧[B6资产](B1_B6_stage_assets.md)固定b9、schema7及旧启动逻辑，只能参考隔离方法，不能原样安装后声称P3已通过。

Agent启动还要求明确的`MINGJING_AGENT_ENABLED=true`、至少三条运行容量、同源模型registry、已有中央account/ledger identity/location及已验`K3_TOKENIZER_DIR`。当前生产装配并非一个现成stage ScriptedProvider启动器；必须补受审离线装配，不能塞假API key或发真实请求来证明启动。P6独立评审不随此profile开启。

恢复证明须观察实际pg_restore及空目标、备份源前缀、全部owner、最新撤销/墓碑/delivery收据、checkpoint及两次状态摘要，不接受手填字段。源prefix4/7的本机原生恢复及候选双重放已有定向证据；源prefix8、旧包/旧schema回退兼容、中央账本保全与重绑定、提交后checkpoint或回执写入失败的停留状态仍须补齐，整体还需本机Linux演练。

当前精确ACL仅支持已审24张Core表、4张checkpoint表、0008单sequence和0007受审invoker触发函数；额外关系/规则/例程拒绝。新组件有真实需要时先变更审核profile与测试，不能临场宽授权。

## 6. 失败与回执

异常立刻停止，保留stage维护门/栅栏与私有产物；不自动删除新库再跑，不覆盖原stage，不启动旧代码配不兼容schema。**仅开门前可按另审并已演练的回滚方案恢复；开门后只关门止损、停writer、保存现场，等待审核的向前修复。** 本单不包含任何可执行rollback命令。

B8记录实际北京时间、候选/工具/manifest/三锁、PG版本/角色/迁移安全投影、备份与最新旁账hash、两次回填/重放计数、ACL/网络/DOM行为、未完成项与停止状态。只引用现有证据索引，不复制多套证据。真实模型、飞书或外部消息默认0；任何真实冒烟须另有精确授权。

相关来源：[恢复ExecPlan](../execplans/first_release_recovery_20261023.md)、[校验入口](../../../tools/first_release_restore.py)、[精确ACL](../../../tools/first_release_acl.py)、[生产草案](first_release_prod_runbook.md)。旧[B1 stage单](B1_stage_runbook.md)是历史范围，不能授予本次权限。
