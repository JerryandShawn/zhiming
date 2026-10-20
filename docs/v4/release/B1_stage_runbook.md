# B1 stage 执行单：已有 Core PG 的增量升级（B0–B8）

版本：2026-10-20 23:07 +08:00。**当前 No-Go：真实 Linux PG15、systemd/fcntl/恢复和完整权限/停写证据未通过。** Docker Inference socket不可访问，独立WSL启动E_ACCESSDENIED，精确重命名仍拒绝后已停止修复；没有Reset或删卷。本单不是执行授权或已完成回执。root随实际工具/演练补全后交大脑审阅；不能只因为标题存在就进入服务器。

## 1. 固定输入、授权与禁止项

发布包固定 `b9a89b6f84f7bebb640de080548010859aae630c`（P1+P2，schema1–7）；部署工具可来自本次工作分支，分别记录commit/controller hash。不得改b9，不得把P3/P1b/0008/tzdata修复塞进包。`__release_manifest__.json` 原始字节SHA256应为 `49038f8c0dc6bb293ba688af91018cbe6339b319c388d290fd000a256e36b33c`。旧包7dbc951eaffebd3d812169865eaefcde16a00ed9保留。

本机额外0008实验仅验证P1b未来兼容，与本单真实服务器B1分开；**授权B只允许0005–0007**。模型保留k3/现有端点，新ModelPort不开，stage不配置模型凭据。

唯一授权来源是用户10-20本聊天委托与29号第四节：北京时间10-21 08:30以后，完整读30号文件，结论明确Go且先完成其修改要求。30不存在/No-Go时不建立SSH。当前30/31未出现；每次续作重读，不把同名旧文件或正文提到Go当本次放行。指令板不能扩大这次授权。

允许目标仅服务器1.14.59.242的历史 `zhiming_core_stage`、新 `core_test_b1` / `zhiming_core_b1_web` / `zhiming_core_b1_restore`及各自独立owner/writer、新 `zhiming-core-b1-stage.service`（回环8788）。历史stage仅primary回填，另16 owner只计数。不碰live库/服务/文件，不改Hermes，不启动stage报告/飞书，不新增公网反代，不删除已有文件/目录/库，不发送消息或真实模型请求，不合并主干。

任何操作异常（hash/身份/迁移/第二回填/权限/容量等）立即停止，保持现状及已建立的维护/栅栏，写日报等待大脑；**不能自行修好再试**。只有SSH连接被拒可10分钟后重试，最多3次；每次一个短会话，长步骤后台执行后短连接取安全计数。失败记录使用实际北京时间，不补造小时进度。

## 2. 执行前必须解锁的本机门

| 门 | 继续证据 | 当前状态 |
| --- | --- | --- |
| 本机PG15真实增量/恢复 | 独立容器及镜像身份、schema4备份恢复、b9 4→7、权限、primary幂等、恢复兼容 | 阻塞：Docker/WSL不可用；22项传输测试不等于真实恢复 |
| B7重放入口 | 新stage恢复副本allowlist CLI、候选b9底层调用、最新撤销+sent/uncertain单调、重复无变化 | 阻塞：旧restore-withdrawals硬live不可用 |
| 固定命令与解释器 | systemctl/pg_dump/pg_restore绝对路径/版本/hash/权限；Core/Charts解释器和锁定依赖完整性 | 固定路径/root所有权/保留venv调用路径已补替身测试，真实Linux版本与依赖完整性仍阻塞 |
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

本段环境须由受审loader注入，不能把服务器private env上传到Git。新合成Web库、角色及checkpoint初始化/只读账本授权，独立unit的精确内容与出站阻断验证尚未交付时，B6为阻塞；不拼写未经测试的systemd/SQL模板当作已验收入口。只允许回环8788，不给stage配置真实模型key，不发送chat探针或真实飞书。

### B7：恢复与单调重放

**当前阻塞：stage专用CLI和真实PG证据未定稿。** 不运行旧deploy_core restore-withdrawals；它硬编码live。新入口必须先核目标仅zhiming_core_b1_restore、PG15、owner、候选b9、schema、源dump/ledger原始hash、停写与空队列，默认只校验，apply显式选择。

恢复库新建时使用独立owner/writer；不得覆盖stage/live，不给writer DDL。源dump为schema4，先核1–4前缀和原始安全计数，再用b9迁5–7/重授；不能initialize=False直接把schema4当7。真实pg_restore后重放最新无正文withdrawals-v2，保持sent与uncertain终态，验证重复重放零变化。只有实际入口与proof生成工具到位才补其可运行命令；输出proof须绑定B2精确backup对象hash、b9 manifest、恢复目标、七checksum和四项真实验证，不能手填true。

### B8：回执、保留与停机状态

记录每步北京时间、主动/等待耗时、候选/工具/原包SHA、source/controller/artifact/hash、DB/schema/角色安全元数据、迁移/回填两次计数、restore/replay proof、网络隔离、0模型/0外发、未验证与异常。stage成功也不自动生产；等大脑审stage证据并写31及具体窗口。

备份保留14天，权限0700/0600；不在本单授权内删除已有备份或目录。阶段任一异常保持当前停写/维护，不启动旧schema4包，不擅自恢复dump覆盖原库。B1仍No-Go时继续主线开发，不等待睡觉用户。

## 5. 本机演练结果（待真实交付更新）

尚无本轮Linux/PG实测成功结果。10-18的28项为Windows替身，不能填进本表。后续追加精确脚本参数、容器/镜像digest、DB身份、实际计数、源码hash、测试结果与未覆盖项；0008另轨结果单列，不改变B1候选。

## 6. 证据来源

用户10-20最新请求；大脑28 §1–4、29 §〇/§四/§五b、33公共/主线；[旧A盘点](B1_operation_sheet.md)、[现有控制器契约](B1_incremental_runbook.md)、[旧替身验证](B1_incremental_validation.md)、[本机计划](../execplans/B1_linux_rehearsal_2026-10-21.md)。旧文档“容量待用户决定/授权B未申请”是历史，本单最新授权条件优先。
