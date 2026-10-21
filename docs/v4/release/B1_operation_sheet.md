# B1 具体操作单：授权 A 盘点结果与待审执行步骤

2026-10-18，Asia/Taipei。**授权 A 已执行；授权 B 尚未申请、未执行。** 本单先交大脑审阅。依据用户本聊天的只读授权及大脑23号文件第一节；主计划为 [B1_stage_plan.md](B1_stage_plan.md)。本单不是 stage 验收或生产发布回执。

## 1. 结论与发布边界

现状适用 **已有 Core v3 / schema4 → schema7 的增量路径**，不重导旧 SQLite/JSON，不执行 `freeze/install/publish` 代替升级。发布候选仍固定 **b9a89b6f84f7bebb640de080548010859aae630c**，仅含 P1/P2；P3/P1b/P5b/P8/P10 不进入包。

当前为 **No-Go**：根分区仅余约 **0.737 GiB**，尚未核准容量整改、备份恢复演练、增量入口切换方法及授权 B。不要在现有余量下开始双环境安装、备份、恢复副本或索引迁移。

23号文件已裁定：B1 保留实际 `KIMI_MODEL=k3` 和 Kimi Code 端点，不打开新 ModelPort；`k3-256k` 等价性放在 P1b 合并后另行授权。这里不重新询问 D1/D2；所有真实模型请求仍需具体“开始”指令。

2026-10-18夜间大脑裁定：B1候选保持b9a89b6；Charts的`tzdata==2026.5`修复不进B1，随B2发布。该项已决定，不再作为待决问题；不能修改b9包或仅在服务器临时补包。

## 2. 已观察到的事实

盘点区间：**18:12:40–18:29:17 +08:00**。各项是分时只读观察，不是原子快照，执行 B 前须再核当前状态。原始查询只输出服务器内筛选过的元数据；公开安全摘要见 [只读证据 JSON](../evidence/B1/2026-10-18-readonly-inventory.json)。

| 项目 | 实际结果 / 对执行的影响 |
| --- | --- |
| 登录 | `root@1.14.59.242:22`，现有 `gto_deploy_key` 成功，严格匹配已有 known_hosts；未读回私钥正文、未改 SSH、无需口令窗口 |
| 主机 | `VM-0-7-opencloudos`，OpenCloudOS 系 Linux 6.6.117，x86_64；与历史交接的主机相符 |
| 当前代码 | `/root/zhiming-core-releases/7dbc951eaffebd3d812169865eaefcde16a00ed9`；release manifest 与 Web main 导入均指向 Core v3，非旧 ChatAgent |
| Web | `mingjingtai.service` active/enabled，单个 uvicorn 主进程，8787；实际 DB 为回环5432 / `zhiming_core_live` / `zhiming_core_live_writer` |
| 飞书 | `zhiming-core-feishu.service` active/enabled，`CORE_FEISHU_ENABLED=true`，与 Web 同一固定包和 live writer；本轮没有发送消息 |
| 报告 | `zhiming-core-reports.timer` active/waiting，每分钟触发 worker 检查；oneshot service 观察时 inactive/dead，不据此判失败 |
| 实际模型 | Web/飞书进程均为 `https://api.kimi.com/coding/v1`、`k3`；MODELS_CONFIG、MINGJING_MODEL_PORT 未设置；追踪 false，池4/运行并发1 |
| 反代 | `/www/server/panel/vhost/nginx/p.jerrymeng.asia.conf`，`p.jerrymeng.asia` → 回环8787；维护门已配置，维护 flag 当前不存在 |
| stage 进程 | 两个约定 stage unit 均 not-found；8788 未在监听清单出现，stage DB 无活跃应用连接。只证明本次所查名字/端口，不泛称所有可能进程都不存在 |
| PostgreSQL | 同一主机5432为 **15.18**。stage/live 分库，同 schema `mingjing_core`。另见5433监听，但标准 socket 探测未建立连接，身份未验证；本批不用、不修改5433 |
| 旧渠道 | Hermes 服务仍在运行，但旧 Feishu adapter=false；匹配的四个旧知命报告任务均 enabled=false。不得重启全部 Hermes 或启用旧任务 |
| Hermes CLI | 已安装 Core skill manifest 仍固定 **7dbc951…**，配置加载次序为 `/root/.hermes/.env` 后 `/root/zhiming-core-secrets/live-runtime.env`；只是读 manifest，未改 skills |

**需要补入生产切换的入口：Hermes Core wrapper 也固定旧 SHA。** 仅改三个 systemd 服务会遗漏它；旧包只有迁移1–4，不能承诺可读 schema7。后续需单独审阅其 writer fence、固定包重定向与 manifest 更新方式，保持旧解释器退役状态；当前没有受审的“一键增量更新所有入口”命令，也没有执行任何更新。

### 数据库与权限

| 指标 | stage | live |
| --- | --- | --- |
| 库名 / 端口 | `zhiming_core_stage` / 5432 | `zhiming_core_live` / 5432 |
| owner / runtime | `zhiming_core_stage_owner` / `zhiming_core_stage_writer` | `zhiming_core_live_owner` / `zhiming_core_live_writer` |
| 观察库大小 | 25,959,783 B（约24.76 MiB） | 12,393,831 B（约11.82 MiB） |
| schema_migrations | 连续1–4 | 连续1–4 |
| 与 b9 前缀校验 | 四项 SHA256 全一致 | 四项 SHA256 全一致 |
| owner 数 | 17，含约定 primary | 2，含约定 primary |
| run 状态计数 | succeeded96 / failed38 | succeeded9 / failed2 / revoked2 |
| queued / running / 有效租约 | 0 / 0 / 0 | 0 / 0 / 0 |
| Outbox | sent16 / stale2 | sent21 / expired3 |
| 活跃消息 / 缺 at_ms / 非法 at_ms | 409 / 409 / 0 | 261 / 261 / 0 |
| checkpoint 行数 | 1427 | 126 |

两组 runtime role 均非 superuser、无 CREATEDB/CREATEROLE/复制/BYPASSRLS，无角色成员继承；数据库 CREATE、业务/public schema CREATE 均 false，不拥有业务或 checkpoint 表。既有表有 CRUD；schema_migrations 与 checkpoint_migrations 只有 SELECT、无 I/U/D。迁移后仍须重授新表并用真实 runtime 身份复核；`grant_runtime_tables` 成功不等于所有有效权限都已审计。

缺 at_ms 是旧消息待回填状态，不能按非法数据删除；本次没有改正文、日期、revision 或 run。`0006` 转 bigint 的旧值检查未发现非法/溢出值。0001–0004 校验和、角色属性和实际当前包迁移文件一致性均留在证据 JSON；没有读取聊天正文或事实内容。

stage 已有历史、渠道绑定和 sent 收据，**不是可丢弃的空测试库**。本单不授权清空、复制 live、覆盖 stage 或自动对全部17个 owner 回填。

### 报告窗口

两库观察到的当前设置均启用：每日07:00、周日20:00、每月1日09:00、每季首月1日10:00。维护规划按既有Asia/Shanghai、提前15分钟准备规则计算，本轮未执行worker验证投递。生产维护不仅避开06:45–07:00，还要避开这些实际窗口与用户咨询。本日为周日，**19:45–20:00 也应避开**；不因上线改时间或补发。

### 磁盘与备份

根分区总42,881,495,040 B，最后一次观察可用791,592,960 B，约98.15%已用。`/root`、`/var`、备份目录同一文件系统。只读目录计量：备份约360 MiB，cache约1.25 GiB，`/var/log`约3.62 GiB，PG数据目录约99 MiB。release 根目录大小查询未成功（设置25秒限时），未继续无界扫描；不据此估算可安全删除的量。

备份根目录 `/root/zhiming-core-backups` 有12项。最近目录 `20261016T132944Z-maintenance-0aa433af44a1-92574e6e` 中，`core-live-latest.dump` 为563,747 B，撤销旁账15,221 B，均0600；时间为10月16日21:29 +08。**只看文件元数据，未验证 dump、恢复能力或当前版本覆盖，不能作本次切换的最新备份。** 未创建任何新备份。

建议大脑先审容量方案：优先扩容；如选择整理，先逐个核定具体目录、运行包/回滚包/备份保留关系，再申请独立写授权。不能直接删 cache/log/旧 release。执行准备前按“新包+解压+双venv+安装峰值缓存+恢复副本+WAL/索引+备份+增长余量”核算；可先以至少8 GiB可用作为保守工程目标，再用实际包/环境测量修订，它不是已测最低容量或上线保证。

## 3. 待审授权 B 的精确目标

以下全部为**未来步骤，没有执行**。大脑审核后再整理为用户的一次明确授权 B；先解决上节容量和候选问题。授权 B 不包含生产、真实模型、飞书/报告发送、旧任务或 Hermes live skill 的修改。

| 对象 | 拟定范围 / 必须写进授权的内容 |
| --- | --- |
| 发布输入 | 固定 b9a89b6；Core/Charts各Python3.11，逐文件manifest/整体包hash；不从当前P3工作区取未跟踪文件 |
| release | `/root/zhiming-core-releases/b9a89b6f84f7bebb640de080548010859aae630c`，独立于7dbc；若改变SHA则整体重审 |
| 历史 stage | 5432 / `zhiming_core_stage` / `mingjing_core`，原owner与writer保持分离；只在停写状态备份、迁移到7、核账及受审owner回填，不启动该历史库Web |
| 合成验收库 | 新建 `core_test_b1`，只放合成数据，供测试DDL/临时schema使用，不给runtime提权 |
| 合成 Web 库 | 建议新建 `zhiming_core_b1_web` 与独立owner/writer，schema7、空队列、合成owner；不复制历史stage/live绑定、密钥或正文 |
| Web 进程 | 新 `zhiming-core-b1-stage.service`、回环8788、独立 `/root/zhiming-core-b1-stage/`工作/媒体目录及受保护 `stage-b1-runtime.env`；禁止复用live unit/env/media |
| 网络/渠道 | 无模型凭据、出站阻断、Feishu=false，不启动 stage报告/飞书服务，不新增公网反代；进程经审阅的临时隔离方式另列具体命令 |
| 备份/恢复 | 仅获准stage的一致dump和受保护元数据；恢复到新的 `zhiming_core_b1_restore`，不覆盖原stage/live；文件0700/0600、保留期限另定 |
| 回填owner | 建议先只针对历史stage的 primary；其他16个owner只计数不改，逐一列清范围后再获准。生产另有2个owner，不能默认同意全量回填 |

新库、新角色、新文件、隔离服务、出站规则、迁移、回填、备份恢复都属于写操作，必须包含在 B 中；这里列名不构成创建授权。若不批准合成Web库，则保持Web未启动，先做受审的PG/脚本业务验证，不把恢复历史队列当健康检查。

## 4. B 的分步操作与继续条件

| 次序 | 操作 / 精确输入 | 继续条件与证据 | 估时 |
| --- | --- | --- | --- |
| B0 | 复核SSH/主机、磁盘、实际live unit和schema4；确认授权目标只有stage与新合成/恢复库 | 容量方案已执行并获核验，发布SHA已裁定，live状态无非预期变化 | 10–20分钟 |
| B1 | 在干净固定SHA检出上bundle；经获准渠道传包，核hash，使用同版本部署工具prepare独立双环境 | manifest逐文件通过、pip check、合成Charts零skip；不执行install/publish | 20–45分钟 |
| B2 | 保持历史stage无writer；stage custom dump、schema账本/撤销/收据/配置摘要备份；不拷live | hash/权限/恢复目标核定；无queued/running/有效租约；恢复可用性随后演练 | 15–30分钟 |
| B3 | 连接身份预检→固定迁移集1..7→现有前缀1..4比对→只由stage owner迁0005–0007→重授新表 | schema7/七项checksum、runtime新三表CRUD、账本只读、无DDL/ownership/继承提权 | 5–20分钟 |
| B4 | 核指定primary范围：dry-run→审计安全计数→apply→再次apply | 第二次新增变化0；撤销/原文/revision/固定牌/Outbox均保持契约；任何异常停下 | 10–40分钟 |
| B5 | core_test_b1跑固定B1候选全部Core/v4/脚本及Charts；合成Web库迁schema7，固定版本PostgresSaver.setup及受审角色授权 | public checkpoint三表CRUD/其迁移账本只读；不运行P3/P1b测试树；逐套零skip，scripted80/80+48，隐私/回放/12356合成断言 | 30–60分钟 |
| B6 | 空队列、无凭据、出站隔离就绪后，只启动合成Web 8788，检登录/health/state/history/固定牌与DOM | 不访问生产HTTP；启动会创建worker，故须保持上述条件；不发chat真实模型请求 | 20–40分钟 |
| B7 | schema4 dump恢复到新恢复库，核原1–4前缀；由获准迁移角色在恢复库迁到7/重授，再演练受审撤销/收据重放及只读核验 | 不直接用b9的initialize=False把schema4验成7；已撤销不复活、sent/uncertain不重发，原有效变更可核对；不开恢复库Web | 20–45分钟 |
| B8 | 汇总安全证据、实际耗时、差异、剩余门，交大脑审核 | 不写stage accepted=true，直到必要门逐项有证据；不自动转生产或模型验收 | 10–20分钟 |

预计 stage 主动操作仍为2–4小时起；容量整改、安装排队和恢复缺口另计。B3–B7包含写入，**本次 A 全部未运行**。

### 已有命令与不能假设存在的命令

bundle/prepare 参数来自现有 `tools/deploy_core.py`。固定路径、包 SHA、源目录必须在实际执行前核准；下列变量不含密钥，迁移连接仍由受保护进程注入，不 source 任意env文件。

    REVIEWED_SHA=b9a89b6f84f7bebb640de080548010859aae630c
    RELEASE_DIR=/root/zhiming-core-releases/$REVIEWED_SHA
    python tools/deploy_core.py bundle --commit "$REVIEWED_SHA" --release-dir "$RELEASE_DIR" --source <干净固定SHA检出> --artifact <本机受保护目录>/B1.tar.gz
    python tools/deploy_core.py prepare --commit "$REVIEWED_SHA" --release-dir "$RELEASE_DIR" --artifact <获准传入目录>/B1.tar.gz --artifact-sha256 <核定SHA256>

历史stage备份使用5432、stage owner及PGPASSFILE，不把密码/完整DSN放argv：

    pg_dump --host=127.0.0.1 --port=5432 --username=zhiming_core_stage_owner --dbname=zhiming_core_stage --format=custom --file=<受保护B1目录>/stage-before.dump

迁移使用主计划S3的受审Python调用，只有初始化会执行全部缺失迁移；没有`--to 7`、`--stage`或`--incremental`。执行前必须显式失败判断数据库为stage/角色为stage owner/回环5432/PG15及manifest恰1–7，不能用可被优化关闭的assert代替护栏。runtime另连同库，`PostgresRepository(...,initialize=False)`+`verify_schema()`并核有效权限；不能通过给writer DDL解决启动失败。

    "$RELEASE_DIR/venv/core/bin/python" tools/backfill_v4.py --dsn-env CORE_MIGRATION_DSN --schema mingjing_core --owner primary --dry-run
    "$RELEASE_DIR/venv/core/bin/python" tools/backfill_v4.py --dsn-env CORE_MIGRATION_DSN --schema mingjing_core --owner primary --apply
    "$RELEASE_DIR/venv/core/bin/python" tools/backfill_v4.py --dsn-env CORE_MIGRATION_DSN --schema mingjing_core --owner primary --apply

上述三步须分开审阅，不一次批量执行。工具无resume/limit/rollback，整个owner事务锁持续到结束，中断整次回滚。不要对已有Core stage再次运行导入型 `verify_core_stage.py` 或 `migration_core.py`。

新合成Web库还需由迁移角色执行固定版本`PostgresSaver.setup()`，授public checkpoint三表CRUD和checkpoint_migrations只读；runtime以initialize=False运行，不会自动补这些表。不要调用包含live导入/启停的整套install来初始化。

恢复用原生 `pg_restore` 到另一个已核准的新库，不加 `--clean` 指向原stage/live。B2备份是schema4：恢复后先只核原前缀/计数，再用受审的恢复库身份护栏、迁移角色将恢复副本迁到7并重授，最后以b9执行受审撤销/收据重放及initialize=False只读核验；不能把B3硬stage目标模板不改护栏就用在恢复库。角色映射与配套代码另审。现有`restore-withdrawals`硬live，不能直接用于stage恢复；先准备受审的stage重放入口和真实PG测试，再执行B7，不伪造已有CLI。

## 5. 生产切换与回滚：仍待后续独立授权

生产候选、数据库和配置保持上文固定。大脑审过stage证据后，用户另选 **90–180分钟**维护窗口，避开所有报告准备/投递和咨询；stage授权不能代替生产授权。

生产执行顺序：最新只读复核→维护门与所有writer fence/排空→当前一致PG+撤销/收据/媒体清单备份并验可恢复→同样迁0005–0007/重授→逐个获准owner dry/apply/repeat→切Web/飞书/报告三个固定unit与CHART_PYTHON→受审Hermes Core wrapper固定入口→门内核验→另经批准恢复正常业务/渠道→观察30–60分钟。保留实际k3，新ModelPort仍off。维护门只挡网页，不阻止后台worker或Hermes CLI，不能漏后两者。

**切换工具缺口是明确的生产前置门。** 现有freeze/install/publish会动旧源/技能/任务和live，不能把它们拿来填上述增量入口缺口。先实现并审查小范围增量切换/故障止损方法，在合成stage演练；本轮只读，没有修改该工具或任何服务器skill。旧Hermes服务有其他用途，不能为本项目整体停启。

0005–0007无down；当前7dbc旧包只有1–4，不能直接回切schema7。迁移未提交时可保持维护核事务回滚；已提交后优先schema7兼容向前修复。若恢复备份，必须明确恢复目标/哈希/配套代码，重放最新撤销及sent/uncertain并处理有效增量，复验后才开门。止损目标5–10分钟、恢复30–120分钟起仅为待演练估计；当前备份元数据不证明RPO/RTO。

## 6. 交大脑的待决与授权顺序

| 待决 | 建议 / 未决定时默认 |
| --- | --- |
| 根分区容量整改 | 用户明天决定扩容或清理，今晚只写两方案对比；不访问服务器、不删除、搬移或新建备份，不开始B |
| 固定b9与新tzdata锁（已裁定） | B1保持b9，tzdata随B2，不临时补包；该项关闭，不再询问 |
| B的库/服务/数据范围 | 建议历史stage保持离线，仅primary回填；新合成Web/测试/恢复库隔离。未批准不建库、不碰任何stage进程 |
| 增量Hermes Core入口及恢复重放 | 审查具体实现与合成演练；本单指出缺口，不用硬live旧CLI或重启全部Hermes代替 |
| 生产窗口/2个owner与恢复权限 | stage签收后由用户选窗口并逐项授权，不在本轮申请，不默认全部owner获准 |

顺序为 **大脑审本操作单 → 处理上述前置项 → 向用户申请精确授权 B → stage证据再审 → 后续生产授权**。真实模型为独立开始授权，P1b后的k3-256k等价性也不搭车。无需用户重复提供已经可用的登录方式或把任何秘密发进聊天。

## 7. 授权 A 执行回执

已完成服务器身份/运行包/服务/模型非密钥配置、PG版本/两库账本/角色与有效权限、队列/Outbox状态、定时/飞书/CLI固定入口、磁盘与备份元数据盘点。所有SQL为`BEGIN READ ONLY`，5秒statement timeout；脚本经SSH stdin执行，未上传或保存远端脚本，没有导入应用。只有一次连接超时，之后一次相同只读重试成功；没有改登录配置。

主动远端修改、建库、备份、服务操作、应用启动、模型/HTTP请求、消息发送均为 **0**。未返回私钥、口令、完整DSN、token、出生资料或聊天正文。执行中两个字段投影查询失败，事务终止；后续按catalog修正只读查询补齐owner计数与报告设置，未采用写入修复。

未验证：备份内容/恢复能力、依赖与计算跨系统全套、stage迁移/回填、真实模型质量与新模型等价、生产切换/旧包schema7兼容、5433身份。它们不因A通过而变成已验收；后续按各自授权和证据门推进。
