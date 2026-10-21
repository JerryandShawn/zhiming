# B1：补齐Linux应用回填、重放与进程栅栏演练

本ExecPlan遵循`.agent/PLANS.md`，北京时间2026-10-21 08:44创建。当前只读审计与设计；未运行测试、Docker/WSL、服务器、模型或飞书。主树`C:/Users/Administrator/Documents/Codex/zhiming-v4`，审计基准c7d760addc63ea9c8a12d15d08123b32f6e17238。指令板v2与30号明确No-Go；两次环境尝试已耗尽，本计划不允许第三次启动/修复/探测。root另行授权具体工具文件后才能实施。

## Purpose / Big Picture

恢复可用Linux环境后，一套真实证据应能分别说明：固定b9的primary回填dry-run不写、首次apply做了预期变更、再次apply三个写入计数为0；B3实际恢复后，精确B7入口重复重放保持状态不变；Linux共享/排他writer锁穿过真实进程及exec仍有效。现有SQL演练只覆盖PG备份恢复和迁移，不能自动代表这些应用行为已测。本计划把缺口、空恢复目标所有权和Linux解释器前提先固定，避免环境恢复后才发现仍无可运行应用入口。

## Context and Orientation

复用现有`tools/b1_linux_drill.py:39/256`的计划和SQL演练、`b1_linux_drill_transport.py:LocalDocker`的固定本机pipe/镜像digest/标签/端口护栏、`b1_linux_drill_sql.py:fixture_sql/apply_sql`的合成存储。固定发布包为b9a89b6f84f7bebb640de080548010859aae630c，manifest原始SHA256为49038f8c0dc6bb293ba688af91018cbe6339b319c388d290fd000a256e36b33c；0008另轨，不改包和0001–0007。

应用回填复用固定b9的`tools/backfill_v4.py`与`mingjing_core.memory.backfill.backfill`，外部控制器参考当前`tools/core_incremental_pg.py:214`的原文不可变检查和`core_incremental.py:45`的dry/apply/repeat计数门。B7复用现有`tools.b1_restore_replay`和`b1_restore_replay_worker.preflight/replay`，不改其stage恢复库allowlist。writer fence复用固定b9的`tools.deploy_core.skill_writer_lock/execute_hermes_core`及当前`core_incremental_host.local_fence`，必须真实fcntl/多进程/exec，不能换成线程布尔值。

恢复证明由另一代理独占`tools/b1_restore_proof*`，其正式入口要求空`zhiming_core_b1_restore`、Linux/PG15、独立owner/writer，自己pg_restore→schema4精确状态校验→固定b9迁7→最新账本两次回放→权限核验；本计划不重造或手填proof。B6的Web库/unit/env/出站规则也归另一代理。源代码与“已写工具”不等于“已通过Linux演练”。

## Progress

- [x] (2026-10-21 08:44 +08:00) 完整读指令板v2、30号、SQL演练三文件、publication/Native fence、增量PG/backfill、B7和固定b9回填/锁代码；未执行任何应用或环境探测。
- [x] (2026-10-21 08:44 +08:00) 确认SQL演练未接应用回填/B7/fcntl，也未提供或核验Linux Core Python与锁定依赖。
- [x] (2026-10-21 08:44 +08:00) 确认旧完整SQL演练占用正式restore库，与B3空库门冲突；root裁定拟加storage-preparation阶段，把空目标交B3，保留原完整模式且不自动清库。
- [x] (2026-10-21 08:44 +08:00) 完成独立差额证据与最小接口/文件建议，冻结交root；本任务只拥有两份新文档。
- [x] (2026-10-21 08:49 +08:00) root授权main的b1_linux_drill.py/_sql.py、b1_linux_application_drill*.py、对应release测试和这两份文档；先实现storage显式模式，默认与原full-SQL不改。
- [x] (2026-10-21 08:49 +08:00) storage-preparation新模式首片已实现；保留空restore、拒非空、默认不构造transport，纯SQL备份明确application_ready/admissible_restore_proof=false。4新目标+原22传输目标26pass/0.31秒，未运行Docker。
- [ ] root分配具体tools/test所有权后实现默认无副作用的应用drill及storage-preparation接点。
- [ ] 用传输替身与既有Windows隔离PG做必要接口/负例；明确不签Linux通过或正式proof。
- [ ] Linux能力门恢复后，在同一真实PG15取得回填、B7与跨exec fence证据；环境仍阻塞，不等待或反复重试。

## Surprises & Discoveries

`b1_linux_drill.plan()`已经明确application_backfill=not-exercised-by-this-SQL-drill，结果又写native_host_switch=not-verified和B7_replay=separate-reviewed-entry-required。脚本没有运行候选Python的步骤，镜像只核postgres:15的Linux身份/digest；不能据此断言其中存在Core 3.11或锁定psycopg/LangGraph等。Windowsvenv不能当Linux运行环境。缺解释器或依赖应报独立能力门，不自动安装新依赖、改锁或下载新runtime。

SQL fixture只有primary/secondary原消息、一个result为空的succeeded run和已sent/uncertain收据。它可触发消息元数据/搜索token回填，却不能证明成功旧回复补写，更不能证明“备份后新增撤销/送达状态”在旧dump中被重新应用。应用fixture须真实固定b9业务创建事实、待撤销原话、draw/tombstone、旧回复及checkpoint，且输出只给hash和计数。

旧execute会先restore到zhiming_core_b1_restore并迁7；B3新生成器正当拒非空目标。重复跑旧execute又拒任一既有目标库，且新输出不可覆盖。因此不能将两条现有命令机械顺接，不能drop/clean/reset解决。root明确先提供storage-preparation新阶段，将正式恢复库保留空，由B3成为唯一恢复写入者。

Native publication有NATIVE_PRODUCTION_RESTORE_UNAVAILABLE硬门；它不是stage应用演练后可顺带解除的门。PG镜像也未提供systemd/native主机环境。小范围真实fcntl证明不能冒充三个unit、实际Hermes安装、/proc会话归属或生产Native restore通过。

## Decision Log

2026-10-21 08:44 +08:00 / root：先新增可独立审阅的storage-preparation阶段，原完整SQL模式可保留，但不得重复使用/覆盖B3正式目标；不改B3空库护栏。B3自行恢复、回放和权限签proof，应用回填与跨exec fence另留证据。工具所有权待root明确，本任务现在不改tools。

2026-10-21 08:44 +08:00 / Codex：B7在B3已经实际回放的恢复状态上跑两次可以首次false；必须绑定B3的真实输入ledger、dump、目标、前后状态和首次语义变更证据，不能伪造changed=true或将B3变更记成B7变更。第二次必须changed=false且状态hash相等；源账本保持同字节、连接全部关闭后再起B7子进程。

2026-10-21 08:44 +08:00 / Codex：先验证既有Linux Core3.11、锁文件/包清单/import能力和候选导入路径。缺时保持独立阻塞，不apt/pip安装、不扩镜像、不拿Windows测试代替。应用controller放固定发布包之外，候选目录完整manifest不变。

## Plan of Work

第一片在旧drill中新增显式storage-preparation计划与回执：固定专属资源/镜像/角色、schema4合成源、真实dump和0700/0600、完整源状态hash、备份账本、空恢复目标；遇既有资源冲突仍停。旧SQL完整演练模式不默认改变；两种模式必须明确互斥，不让旧模式预先消费B3目标。backup对象用既有validate_backup契约，由实际观察生成，不手填source_state_sha256或body_free标记。

第二片新增外部应用drill的preflight。只读校验storage回执、固定b9 manifest、同一PG15镜像/库/角色/端口、Linux解释器realpath/hash/3.11版本、锁文件及锁定包清单和实际导入位置。应用过程只运行在明确Linux worker中；PG镜像若不含解释器则阻塞。控制器不能以--platform参数声称Linux，不能把host Windows Python放进Linux证明。

第三片按受审顺序由B3完成正式空目标恢复/迁移/最新账本两次回放/角色校验；源stage只迁5–7后执行primary回填。回填参考原文摘要算法，dry-run前后状态必须相同，首次apply三个写入计数至少有预期非零值，第二apply的message_metadata/search_tokens/assistant_created全部严格整数0。assistant_existing/assistant_skipped/invalid_time等诊断不是“变更”，不错误要求其全为0。secondary及其它owner计数/摘要不变；原文/原revision/既有回执、draw不被改写。

第四片在B3已关闭所有连接的恢复库上用精确现有B7 CLI跑两次，各写独立新0600回执，绑定相同ledger/dump/候选/proof。检查不复活原话/事实/draw、sent/uncertain不再被Outbox claim，第二次changed=false且前后hash相同。没有sender，不创建真实模型或飞书入口。B3本地演练schema与正式schema不得互相冒充。

第五片用同一Linux runtime的专属临时路径做真实多进程fcntl：writer取共享锁→真实exec进无DB/模型的合成惰性CLI→另一进程取排他锁应在deadline内失败→writer退出后排他成功→维护门在配置/DB前拒绝。只替换受审临时路径与无业务配置边界，不mock fcntl、os.exec或进程结果；记录pid/exit/monotonic耗时，不靠固定sleep判定成功。此片仅证明锁/exec，不签systemd/生产切换通过。

## Interfaces and Dependencies

拟议入口为`python -m tools.b1_linux_application_drill`，不是现有可执行命令。默认只给计划且无Docker/PG/子进程；未来显式apply输入包括operation_id、storage-preparation回执、固定candidate-source、Linuxcandidate-python、B3proof/账本/哈希、phase=preflight|backfill|replay|fence和新output。全部目标由固定allowlist推导，不能给任意SQL/命令/远端DSN/平台布尔值。回执拟为b1-linux-application-drill-v1，逐phase记录observed/blocked，默认publication=false、models=0、sends=0；它不是stage Go或B3proof。

root已授权新文件统一为`tools/b1_linux_application_drill*.py`前缀，按runtime/backfill/fence/worker分拆及对应`tests/v4/release/test_b1_linux_application*.py`；另授权现有`b1_linux_drill.py/_sql.py`的storage-preparation最小接点。transport仍不改；`tools/b1_restore_proof*`、B6及既有replay/publication工具不占用、不覆盖。无新增依赖、迁移或固定包变更。B3要求dump前真实初始化public四张checkpoint表，纯SQL旧dump不能冒充合格B3备份；缺应用runtime时只能留明确不可admit的存储切片。

## Validation and Acceptance

对应指令板v2第2/3项、B1 B3/B4/B7，以及07评测R02的旧助手回复存储基础和F01的事实撤销传播前提；本片不宣R02完整模型语义评测已通过。默认零连接；源/candidate/runtime/digest/角色/端口/目录/私有权限任一不符先拒绝；非空restore拒绝且无删除。全新storage→真实B3恢复proof可绑定，primary dry-run不写/首次apply有意义/第二次三个变更计数0，其它owner原摘要不变。B7两次状态hash一致、第二次false，原文/draw/撤销和sent/uncertain不复活。真实多进程及exec覆盖共享fd保留、排他阻塞/超时/退出后可用、维护门先拒；失败均无DB/模型/外发。

纯测试/Windows PG结果须独立schema与admissible=false，不给Linuxactual.json填通过值。完整B1通过需要固定镜像及LinuxPG、Core锁定runtime、B3、应用回填、B7和fcntl全部实测，并另有B6等门；本计划现在没有任何新测试通过数字。

## Idempotence and Recovery

默认校验可重跑；apply不自动重试。备份、库、目录、回执已存在时保留并停，不覆盖、不drop、不清卷。回填第二次apply和账本第二次重放是受审的正向幂等验证步骤，不是异常后重试。DB提交后写证据失败可能留下已变更状态，须停止供审查，不能为了取得绿回执再执行。环境恢复次数已耗尽，本计划阶段不触发任何新探测。

## Artifacts and Notes

差额证据为`docs/v4/evidence/B1/2026-10-21-linux-application-gap.md`。未来Linux应用回执可独立置`2026-10-21-linux-application-actual.json`，与旧SQL的`linux-actual.json`和B3正式proof分开，不在未运行时创建成功文件。私有dump/账本/配置留受保护目录，不进Git。

## Outcomes & Retrospective

只读审计和设计完成后获root具体工具授权，已实现storage-preparation首片：空恢复目标预留与实际schema4校验、纯SQL回执明确不能admit，4新目标加22既有传输目标26pass/0.27秒。应用runtime、真实checkpoint/bootstrap、primary回填、B7接线和跨exec worker继续实施，均未宣Linux通过。两次Docker/WSL额度不会再使用；31号生产Native恢复按指令板排stage之后，不在本片解除。首片3源码/测及更新文档交root，下一片不覆盖已冻首片。

## 修订记录

- 2026-10-21 08:44 +08:00 创建：固定真实代码差额、root的storage-preparation裁定、B3/B7重复false的证据归属及Linuxruntime能力门；仅文档，无执行。
- 2026-10-21 08:49 +08:00 获root具体代码授权，按指定前缀实施；storage模式首片26个替身目标通过，补B3必须包含public checkpoint的前提，维持无第三次环境尝试。
