# B1 stage 执行单：已有 Core PG 的增量升级（B0–B8）

版本：2026-10-21 09:41:34 +08:00。**当前 No-Go：30号08:16复核明确No-Go，真实 Linux PG15、systemd/fcntl/恢复和完整权限/停写证据未通过。** 两次非破坏环境恢复均已失败，不再探测/修复。B3真实生成器及consumer已交本机Windows证据，B6完整13资产/缓存隔离已交静态证据；均不能解除Linux门。生成器/应用与总编排差额见第5节；本单不是执行授权，不因工具存在而访问服务器。

## 1. 固定输入、授权与禁止项

发布包固定 `b9a89b6f84f7bebb640de080548010859aae630c`（P1+P2，schema1–7）；部署工具可来自本次工作分支，分别记录commit/controller hash。不得改b9，不得把P3/P1b/0008/tzdata修复塞进包。`__release_manifest__.json` 原始字节SHA256应为 `49038f8c0dc6bb293ba688af91018cbe6339b319c388d290fd000a256e36b33c`。旧包7dbc951eaffebd3d812169865eaefcde16a00ed9保留。

本机额外0008实验仅验证P1b未来兼容，与本单真实服务器B1分开；**授权B只允许0005–0007**。模型保留k3/现有端点，新ModelPort不开，stage不配置模型凭据。

唯一授权来源是用户10-20本聊天委托与29号第四节：北京时间10-21 08:30以后，完整读30号文件，结论明确Go且先完成其修改要求。30不存在/No-Go时不建立SSH。08:30:07已完整读取本次30号，结论No-Go；31不存在。早期两文件未出现仅为历史，不作当前依据；每次续作重读，不把正文提到Go当本次放行。指令板不能扩大这次授权。生产Native恢复入口按v2排stage之后，31号复核前必须解除。

允许目标仅服务器1.14.59.242的历史 `zhiming_core_stage`、新 `core_test_b1` / `zhiming_core_b1_web` / `zhiming_core_b1_restore`及各自独立owner/writer、新 `zhiming-core-b1-stage.service`（回环8788）。历史stage仅primary回填，另16 owner只计数。不碰live库/服务/文件，不改Hermes，不启动stage报告/飞书，不新增公网反代，不删除已有文件/目录/库，不发送消息或真实模型请求，不合并主干。

任何操作异常（hash/身份/迁移/第二回填/权限/容量等）立即停止，保持现状及已建立的维护/栅栏，写日报等待大脑；**不能自行修好再试**。只有SSH连接被拒可10分钟后重试，最多3次；每次一个短会话，长步骤后台执行后短连接取安全计数。失败记录使用实际北京时间，不补造小时进度。

## 2. 执行前必须解锁的本机门

| 门 | 继续证据 | 当前状态 |
| --- | --- | --- |
| 本机PG15真实增量/恢复 | 独立容器及镜像身份、schema4备份恢复、b9 4→7、权限、primary幂等、恢复兼容 | 阻塞：Docker/WSL不可用；22项传输测试不等于真实恢复 |
| B7重放入口 | 新stage恢复副本allowlist CLI、候选b9底层调用、最新撤销+sent/uncertain单调、重复无变化 | 入口及B3生成器/consumer已实现，Windows PG与归档窄组各自留证；Linux同一备份→B3→精确B7链仍阻塞 |
| 固定命令与解释器 | systemctl/pg_dump/pg_restore绝对路径/版本/hash/权限；Core/Charts解释器和锁定依赖完整性 | 候选缓存隔离/严格PG路由与TEMP检查已补本机反例；真实Linux版本、venv来源/权限/依赖完整性仍阻塞 |
| 停写与失败恢复 | 实际Linux fence覆盖跨exec、部分retarget失败不启动、stage不影响live | 阻塞：替身结果不能替代实证 |
| 受保护执行配置 | 精确scope/DB/角色/host/hash请求、独立0600配置/审批、输出不覆盖、loader无密钥回显 | 阻塞：实际配置须B0后据当前元数据生成 |

这些门没有解除，即使时间到了也先记No-Go，不执行写操作。用户说明服务器磁盘已清理完，旧0.74GiB记录不再当作当前容量事实；获准B0仍必须实查≥8GiB。

## 3. 操作目录与安全配置

在获准Linux主机的root短会话中使用已审、无符号链接的新operation目录，权限0700；所有配置/approval/回执/dump/旁账0600，保留14天，今晚不写删除任务。不要复用已有operation_id或覆盖输出。

以下变量只含公开路径/版本，不含口令；运行前由已核配置填好，未填就停止。`CONTROL_DIR`必须是审过工具的独立目录，不能是固定发布包。`CORE_INCREMENTAL_OWNER_DSN`与`CORE_INCREMENTAL_WRITER_DSN`仅由受保护loader注入进程，不放argv、不source任意env、不打印环境。stage loader不得读取live env。

    B1_SHA=b9a89b6f84f7bebb640de080548010859aae630c
    RELEASE_DIR=/root/zhiming-core-releases/$B1_SHA
    CONTROL_DIR=/root/zhiming-core-b1-control
    CONTROL_PYTHON="$CONTROL_DIR/venv/bin/python"
    test -n "${B1_OP:?requires-reviewed-new-operation-directory}"
    export B1_OP
    REQUEST="$B1_OP/request-stage.json"
    HOST_CONFIG="$B1_OP/host-stage.json"
    test -x "$CONTROL_PYTHON"

说明：`B1_OP`、具体工具commit、审批哈希和各输出文件须在30复核后记录；本单不预填合成proof来解锁。只读输入校验的真实现有CLI为：

    cd "$CONTROL_DIR"
    "$CONTROL_PYTHON" -m tools.core_incremental --request "$REQUEST"

默认仅验证request，不建Native、不连接业务库。实际apply必须分步，不以一个shell循环串过所有审查门。

## 4. B0–B8 执行表

| 步骤 | 操作与命令入口 | 继续条件 | 停止条件 | 估时 |
| --- | --- | --- | --- | --- |
| B0 | 核30/时刻→单短SSH→主机/容量/已知单位/PG身份/schema前缀 | 授权有效；主机VM-0-7-opencloudos、PG15回环5432；≥8GiB；live无非预期变化 | 授权缺、连接3次拒绝、身份/容量/原1–4不符 | 10–20分 |
| B1 | 固定干净b9 bundle/prepare；核逐文件与Core/Charts双环境 | 636源blob和manifest、pip check、Charts合成零skip均有证据 | SHA/额外源码/依赖/解释器/hash不符；不得改包补救 | 20–45分 |
| B2 | 历史stage无writer→controller backup→提取精确backup对象；dump/旁账hash与权限 | queued/running/有效lease=0；除获准连接无其它会话；停写状态前后摘要不变 | 活跃队列/其他writer、backup写失败或状态漂移 | 15–30分 |
| B3 | 先用B2 dump在新恢复库演练B7→恢复proof审查→controller migrate | schema7七checksum、runtime新三表CRUD、无DDL/ownership/继承、账本只读 | 迁移/授权/恢复proof/状态hash任一异常 | 5–20分+恢复 |
| B4 | primary dry-run审查→controller backfill（内部apply+repeat） | 第二次message_metadata/search_tokens/assistant_created全部0，原文保持；其他16 owner计数未变 | 第二次有变化、hash/原文/固定牌/Outbox不符 | 10–40分 |
| B5 | 固定b9在core_test_b1跑Core/v4/脚本/Charts；新合成Web库schema7和checkpoint授权 | Core/v4/Charts零skip；80脚本+48自检；runtime无DDL | 任一失败/跳过；不可拿P3测试代替b9 | 30–60分 |
| B6 | 新独立8788 unit/env/work/media，空队列、无凭据、出站阻断，合成HTTP/DOM | 登录/health/state/history/固定牌与隐私合成断言；无真实POST或外发 | 复用live env/DB/目录、出站可用、worker恢复旧任务 | 20–40分 |
| B7 | B2 dump→新恢复库→核schema4前缀→b9迁7→最新撤销/收据重放→只读核验 | 实际pg_restore、账本单调/不复活、sent/uncertain不重发、权限与幂等 | 用硬live CLI、错库/角色、过期ledger或任何差异 | 20–45分 |
| B8 | 汇总精确代码/工具/hash/耗时/安全计数/失败门，交大脑 | 所有必要门均有证据才报告通过；不自动进入生产 | 未测项目不可填true；存在异常保持停写待脑 | 10–20分 |

主动操作预计2–4小时起；首次双venv安装、镜像/依赖等待及新增工具审查另计。B7逻辑上须在B3前先完成精确备份恢复proof；编号沿旧操作单不变，不能把B3跑完才第一次证明B2可恢复。

### B0：命令与只读范围

本机先核当前北京时间（不改系统时区）：

    python -c "from datetime import datetime; from zoneinfo import ZoneInfo; print(datetime.now(ZoneInfo('Asia/Shanghai')).isoformat())"

只有满足授权门后才使用本机已存在的部署密钥文件，严格known_hosts；不读取私钥正文。示例SSH参数只表示连接方式，不是现在执行许可：

    ssh -i "$DEPLOY_KEY_FILE" -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 root@1.14.59.242

单短会话内只读命令：

    hostname
    date --iso-8601=seconds
    df -B1 --output=avail /
    systemctl show mingjingtai.service zhiming-core-feishu.service zhiming-core-reports.service zhiming-core-reports.timer --property=Id,LoadState,ActiveState,UnitFileState,FragmentPath,DropInPaths,NeedDaemonReload
    ss -lnt

不显示完整systemd Environment、口令或完整DSN。DB身份/权限/ledger只通过已审工具安全投影读取，不导出正文。记录变化后按当前hash生成请求与审批，不能复用10-18的unit/env hash冒充新盘点。

### B1：包准备

本机固定干净checkout才可bundle，源不取当前P3工作树。命令已有源码支持：

    python tools/deploy_core.py bundle --commit "$B1_SHA" --release-dir "$RELEASE_DIR" --source "$CLEAN_B9_CHECKOUT" --artifact "$LOCAL_B1_ARTIFACT"

经获准渠道上传后核整体artifact SHA，再在Linux准备双环境：

    python tools/deploy_core.py prepare --commit "$B1_SHA" --release-dir "$RELEASE_DIR" --artifact "$REMOTE_B1_ARTIFACT" --artifact-sha256 "$REVIEWED_ARTIFACT_SHA256" --python "$REVIEWED_PYTHON311"

不运行freeze/install/publish。prepare可能安装锁定依赖、生成独立venv和calculator-validation，不启动业务；出站依赖安装与业务出站隔离分开控制。依赖/源文件不符就停，不临时升级锁文件。

### B2：精确停写备份

审核request/controller/host-config哈希及stage scope后，一次只跑一个阶段；stdout仅状态和回执hash：

    "$CONTROL_PYTHON" -m tools.core_incremental --request "$REQUEST" --apply --native --action backup --approval "$B1_OP/approval-backup.json" --host-config "$HOST_CONFIG" --output "$B1_OP/backup-result.json"

回执里的backup对象提取为新0600文件；不能把外层status当backup：

    "$CONTROL_PYTHON" -c "import json,os; from pathlib import Path; from tools.core_incremental_files import private_write; p=Path(os.environ['B1_OP']); r=json.loads((p/'backup-result.json').read_text()); private_write(p/'backup-object.json',(json.dumps(r['backup'],sort_keys=True)+'\n').encode())"

读回安全hash与文件mode，保留dump和withdrawals原字节；B2之后始终停写。不得靠恢复历史stage的Web来证明备份可用。

### B3/B4：迁移与回填

B3恢复证明生成器现已实现；先完成B2，再在唯一新建空恢复库生成，不能把B7回执、Windows local回执或调用方手填JSON当证明。B0必须核`PG_RESTORE_ABSOLUTE`的绝对路径、PG15版本与`PG_RESTORE_RAW_SHA256`；dump/旧账本路径来自B2实际产物。专用受保护loader仅传`B1_PROOF_OWNER_DSN`/`B1_PROOF_WRITER_DSN`及必要显式密码文件；禁止继承11种通用PG路由变量，不显示DSN。以下只是未来Go后的受审命令，当前不执行：

    PYTHONPYCACHEPREFIX=/dev/null "$CONTROL_PYTHON" -B -m tools.b1_restore_proof --request "$REQUEST" --backup "$B1_OP/backup-object.json" --dump "$REVIEWED_DUMP_FILE" --backup-ledger "$REVIEWED_BACKUP_LEDGER_FILE" --ledger "$B1_OP/latest-withdrawals-v2.json" --ledger-sha256 "$REVIEWED_LEDGER_RAW_SHA256" --database zhiming_core_b1_restore --candidate-source "$RELEASE_DIR" --candidate-python "$RELEASE_DIR/venv/core/bin/python" --pg-restore "$PG_RESTORE_ABSOLUTE" --pg-restore-sha256 "$PG_RESTORE_RAW_SHA256" --apply --quiesced --output "$B1_OP/restore-proof.json"

省去`--apply --quiesced --output`时只核输入、0PG；不在正式路径使用`--local-drill`。实际生成器先观察空库（含未知type/namespace/extension拒绝），单事务pg_restore→核schema4全状态与checkpoint→固定b9迁5–7→最新撤销/收据两遍→writer权限/5个实际拒绝探针，再签正式Linux回执；它不创建库，库创建身份另核。第二遍必须changed=false且三段摘要连续，任意异常停留现状，不清目标重试。consumer会在Native副作用前严格核此观察字段与B2绑定；当前无Linux合格proof，不能继续。

增量工具现也在连接前拒隐式路由、锁定同服角色/空passfile；TEMP权限会使runtime_safe=false。如历史stage角色存在多余权限，先停止交审，不自动撤权限修好再试。B0还须实核候选venv/pyvenv.cfg/site-packages来源、root不可组他写及锁依赖，版本元数据一致不能代替整个解释器/包目录信任。

先完成下述B7生成的**真实**restore-proof，经大脑/授权范围内审核后将对象hash绑定migrate审批。已有CLI：

    "$CONTROL_PYTHON" -m tools.core_incremental --request "$REQUEST" --apply --native --action migrate --approval "$B1_OP/approval-migrate.json" --host-config "$HOST_CONFIG" --backup "$B1_OP/backup-object.json" --restore "$B1_OP/restore-proof.json" --output "$B1_OP/migrate-result.json"

migrate仅迁5–7、授权、逐获准owner dry-run，返回review映射；它不会apply回填。审核primary预览及原文/撤销范围，提取review为独立0600 JSON，将migration/result及review对象hash绑定backfill审批，再执行：

    "$CONTROL_PYTHON" -m tools.core_incremental --request "$REQUEST" --apply --native --action backfill --approval "$B1_OP/approval-backfill.json" --host-config "$HOST_CONFIG" --backup "$B1_OP/backup-object.json" --restore "$B1_OP/restore-proof.json" --migration "$B1_OP/migrate-result.json" --review "$B1_OP/review-primary.json" --output "$B1_OP/backfill-result.json"

request.owners必须恰为primary；其余16只核计数。工具每owner再次dry-run核预览hash，随后apply与repeat；repeat任何新增不为0立即停止。retarget只涉及stage约定unit（不存在则保持不存在），不得改live/Hermes。输出publication=false，**不等于允许开门**。

### B5/B6：合成验收

从固定b9目录运行，清空全部provider/飞书凭据，关闭tracing，CORE_TEST_DSN明确指向core_test_b1且测试各schema隔离。完整回归只在北京时间每小时00–15开始：

    "$RELEASE_DIR/venv/core/bin/python" -m unittest discover -s tests -p 'test_core*.py'
    "$RELEASE_DIR/venv/core/bin/python" -m pytest tests/v4 -q
    "$RELEASE_DIR/venv/core/bin/python" tools/eval/runner.py --mode scripted
    "$RELEASE_DIR/venv/charts/bin/python" tools/verify_core_calculators.py --output "$B1_OP/calculators.json"

本段环境须由受审loader注入，不能把服务器private env上传到Git。

### B6：独立合成 Web 资产与实际隔离门

2026-10-21 北京时间：已按指令板v2第5项补齐[完整B6资产](B1_B6_stage_assets.md)：新 `zhiming_core_b1_web` / 独立owner与writer的创建SQL、固定b9 schema1–7与PostgresSaver.setup、三个checkpoint表CRUD/两本迁移账本只读、writer无DDL/owner/继承的只读核验，及无模型凭据env、精确启动包装、`zhiming-core-b1-stage.service`。原 `core_test_b1` 与 `zhiming_core_b1_restore` 仍分库分角色；不借历史stage/live配置或数据。

**当前仍为阻塞/No-Go：30号复核明确No-Go；以下只是未来Go后的执行顺序，未运行SQL、systemd或服务器连接。** 不修改第2节五个门，不将静态检查当Linux通过，B3恢复proof由独立任务生成，不能手填。

未来先核B0–B5和最新30 Go，逐项照资产第2–6节准备：所有新对象先核不存在；root打开SQL stdin交本机PG15管理员创建新角色/新Web库；仅新owner初始化与checkpoint setup；仅新writer做只读有效权限/空队列核验。env只含新PGPASSFILE/合成token文件路径，token本机0600生成不回显。b9无key可以构造ConfiguredModel并提供health/state/history，但不能据此声称可回答真实问题；不发chat/readings/retry/resume生成请求。

09:34缓存边界补丁仅更新资产文本：所有B6候选Python命令、unit预检与launcher二次exec都显式`-I -B -X pycache_prefix=/dev/null`；二次uvicorn使用固定RELEASE的`--app-dir`，启动前校原manifest字节与636成员。env/launcher精确允许`PYTHONPYCACHEPREFIX=/dev/null`供固定b9无-I的Charts worker继承，CHART_PYTHON仍是原隔离解释器路径。13项摘要已重算，9段AST/Ruff E9/F、11段Bash -n、4条unit命令前缀静态核对通过；没有执行资产、Python服务、PG或网络，不能替代B0完整包/依赖检查、真实Linux或Charts缓存对照。

出站阻断按资产第7–9节执行：只在已核本机RFC1918 IPv4上临时绑定随机高端口、仅接受同机源、180秒自停的合成listener。unit外阳性→同unit cgroup ExecStartPre阴性→同cgroup loopback PG阳性→启动→unit外再次阳性必须同时成立；没有私有IPv4、BPF/安全选项不生效或对照缺失立即停止，不改防火墙、不用真实外网探针冒充失败证明。unit明确 `IPAddressDeny=any` / `IPAddressAllow=localhost`、仅AF_UNIX/AF_INET且实核IPv6不能创建；只监听127.0.0.1:8788，Restart=no，不enable，不启动其他stage/报告/飞书unit。

通过只读GET验证登录/health/state/history空库，随后只在新Web库调用b9真实TarotService建立合成固定牌、幂等重放不变，再两次GET对比牌面hash；无模型、无sender。DOM/截图、实际Linux/systemd/PG权限结果另列证据，不能把模板或HTTP200写成验收。命令、继续/停止条件、配置工具hash、隐私与同机对照细节以资产页为准；准备10–15分、初始化/权限5–15分、隔离/HTTP10–20分均为估计。任何异常保持现状停审，仅可止损停止本次新unit，不删除新旧对象、不自动修复重试。

### B7：恢复与单调重放

stage专用CLI已定稿，Windows PG15.19对照25项通过（17纯护栏+8真实PG，27.70秒），[精确证据](../evidence/B1/2026-10-21-stage-replay.md)及同名JSON保留结果；这不是Linux通过，B1仍No-Go。不运行旧deploy_core restore-withdrawals；它硬编码live。新入口只允许指定恢复副本，不创建库、不迁移、不启停服务，不支持生产回滚。

恢复库新建时使用独立owner/writer；不得覆盖stage/live，不给writer DDL。源dump为schema4，先核1–4前缀和原始安全计数，再用b9迁5–7/重授；不能initialize=False直接把schema4当7。真实pg_restore后才可在schema7恢复副本运行下列入口。变量只含路径/原始文件SHA，DSN仅由受保护loader注入`B1_RESTORE_OWNER_DSN`，不能放argv或显示环境。

    "$CONTROL_PYTHON" -m tools.b1_restore_replay --operation-id "$B7_OPERATION_ID" --scope stage --database zhiming_core_b1_restore --schema mingjing_core --candidate-source "$RELEASE_DIR" --candidate-python "$RELEASE_DIR/venv/core/bin/python" --ledger "$B1_OP/latest-withdrawals-v2.json" --ledger-sha256 "$REVIEWED_LEDGER_RAW_SHA256" --quiesced

上式缺省无`--apply`只核本地输入/包，PG连接数0；源ledger是raw `core3-withdrawals-v2`，不能包额外envelope。审核最新ledger原始字节hash、候选636 blobs/manifest、恢复目标/完整owner集、空队列与无其它会话后，真实应用命令为：

    "$CONTROL_PYTHON" -m tools.b1_restore_replay --operation-id "$B7_OPERATION_ID" --scope stage --database zhiming_core_b1_restore --schema mingjing_core --candidate-source "$RELEASE_DIR" --candidate-python "$RELEASE_DIR/venv/core/bin/python" --ledger "$B1_OP/latest-withdrawals-v2.json" --ledger-sha256 "$REVIEWED_LEDGER_RAW_SHA256" --quiesced --apply --output "$B1_OP/stage-replay-receipt.json"

正式入口强制Linux、PG15、回环5432、`zhiming_core_b1_restore_owner`、schema `mingjing_core`、七checksum、私有文件与无symlink、advisory lock。`--quiesced`不替代上层维护门/writer fence；`--local-drill`只允许本机55480/55481和合成`b1_replay_<32hex>`，不能在服务器使用它绕过Linux/身份检查。receipt为`b1-stage-restore-replay-v1`，含ledger原始hash、目标/checksum、前后状态hash/计数、解释器hash、POSIX是否实核；第二次重放须changed=false且hash不变。重复验证须单独受审新receipt路径，不自动重试异常。

Windows真实对照已证明原文/事实/塔罗tombstone不复活、三张checkpoint清除、sent/uncertain不能再次claim、冲突整事务回滚及重复无变化；没有sender。**B7 replay receipt不是`b1-isolated-restore-proof-v1`**：B2精确backup绑定、Linux真实pg_restore/权限、完整四项验证仍须经真实演练与受审proof生成工具补齐，当前不能手工填true供B3放行。写最终receipt失败可能发生在PG提交后，须保持现状停审，不能自行重放。

### B8：回执、保留与停机状态

记录每步北京时间、主动/等待耗时、候选/工具/原包SHA、source/controller/artifact/hash、DB/schema/角色安全元数据、迁移/回填两次计数、restore/replay proof、网络隔离、0模型/0外发、未验证与异常。stage成功也不自动生产；等大脑审stage证据并写31及具体窗口。

备份保留14天，权限0700/0600；不在本单授权内删除已有备份或目录。阶段任一异常保持当前停写/维护，不启动旧schema4包，不擅自恢复dump覆盖原库。B1仍No-Go时继续主线开发，不等待睡觉用户。

## 5. 本机演练结果

Linux真实演练未通过。B3生成器[55项目标](../evidence/B1/2026-10-21-restore-proof-generator.md)、[consumer59项+41子断言](../evidence/B1/2026-10-21-restore-proof-consumer.md)、[无Git联合88项及独立PG11项](../evidence/B1/2026-10-21-restore-proof-portability.md)、[应用48项](../evidence/B1/2026-10-21-linux-application-gap.md)、[旧入口26项+4子断言](../evidence/B1/2026-10-21-existing-candidate-bytecode.md)、[PG路由71项+4子断言](../evidence/B1/2026-10-21-incremental-pg-routing.md)与[TEMP修复73项+4子断言](../evidence/B1/2026-10-21-runtime-temp.md)各为独立范围，重叠不相加，全部不当Linux放行。总编排/共同fixture仍在实现，见[完整差额计划](../execplans/B1_bootstrap_replay_orchestration_20261021.md)。可重复入口与旧边界22项见[Linux准备证据](../evidence/B1/2026-10-21-linux-drill-prepared.md)，Docker/WSL阻塞见[环境证据](../evidence/B1/2026-10-21-linux-environment-blocked.md)。默认只输出计划，环境恢复并审查后才可能运行显式apply：

    python -m tools.b1_linux_drill
    python -m tools.b1_linux_drill --mode storage-preparation --apply --pull-postgres15 --run-id b1-20261021-local --p1b-migration8 C:/Users/Administrator/Documents/Codex/zhiming-v4-p1b/mingjing_core/repositories/migrations/0008_model_usage.sql --output docs/v4/evidence/B1/2026-10-21-linux-actual.json

第二条本轮未运行且环境两次额度已用尽，不能现在重试。新storage-preparation只生成/观察schema4备份后停止，保留B3恢复目标为空，application_ready=false；旧完整SQL模式不能先消费该目标。后续合格checkpoint/B2→唯一B3→共同profile回填→精确B7→fcntl总链尚未完成。旧入口只覆盖PG迁移切片：固定b9 4→7、源/恢复摘要、角色权限、schema4另空库回滚、容量；0008另库且hash固定，不混B1。不会产生全流程restore-proof，backfill/Native/fcntl/三个unit/wrapper仍另验。唯一container/volume标签/loopback55481/PG15 digest必须匹配；未知既有资源或任一目标库已存在立即停止，不自动删除或重放。

B7 Windows PG15.19真实对照25项、publication19项离线控制流/临时文件测试已通过；后者见[publication证据](../evidence/B1/2026-10-21-publication-offline.md)。不能将任一项当Linux、stage或生产Go。10-18旧28项替身保留历史，不混新计数。

## 6. 证据来源

用户10-20最新请求；大脑28 §1–4、29 §〇/§四/§五b、33公共/主线；[旧A盘点](B1_operation_sheet.md)、[现有控制器契约](B1_incremental_runbook.md)、[旧替身验证](B1_incremental_validation.md)、[本机计划](../execplans/B1_linux_rehearsal_2026-10-21.md)。旧文档“容量待用户决定/授权B未申请”是历史，本单最新授权条件优先。
