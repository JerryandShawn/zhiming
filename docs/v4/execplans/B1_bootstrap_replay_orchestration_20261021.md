# B1：存储、checkpoint备份、恢复与应用重放的总编排

本ExecPlan遵循`.agent/PLANS.md`，北京时间2026-10-21 09:26创建。只读审计基准为main的38473401fdc124c00ed9ba117f79b4affb0c68ca；本片**仅新增这份计划**，没有改代码、现有文档、Git暂存区或其它线文件，没有运行pytest、PG、Docker/WSL、服务器、模型或飞书。指令板仍为v2，30号No-Go；两次Linux恢复尝试已耗尽，不因有新计划而重试。正式发布候选仍固定b9a89b6f84f7bebb640de080548010859aae630c，0008与tzdata均不进B1。

## Purpose / Big Picture

把已经分别验证的存储、B3恢复、应用回填与B7组件连成可审阅的本机演练，且证明它们使用同一真实Linux PG15、同一固定候选与同一套受审合成资料。当前组件不能机械串接：旧storage备份不含checkpoint，App只允许两条已知原话，B3另有事实/牌阵/撤销样本，Windows B3目标也不符合正式B7。总编排必须先建立共同fixture与备份来源，再调用现有恢复生成器；不能把一个布尔值或改schema后的Windows回执当作正式通过。本计划给出实现边界与最小入口，待root审阅、分配具体文件后再编码。

## Context and Orientation

复用函数和不可改变的契约如下；这里的“固定候选”指完整manifest原字节SHA256为49038f8c0dc6bb293ba688af91018cbe6339b319c388d290fd000a256e36b33c的b9代码，不是当前P3树。

| 已提交组件 | 复用入口 | 当前契约及不能直接串接之处 |
| --- | --- | --- |
| storage | `b1_linux_drill.execute(mode='storage-preparation')`、`b1_linux_application_drill_storage.preparation/source_state` | 固定本机Docker pipe/容器标签/PG镜像digest，创建schema4与空restore后停止；旧dump无public checkpoint，回执明确application_ready=false，不能重标为B2合格备份 |
| B3生成器 | `b1_restore_proof.generate`、`ProofRequest`、`restored_snapshot`、`run_worker` | 自己观察空库、实际pg_restore、核schema4完整state、固定b9迁5–7/授予、最新账本两遍及实际权限探针；正式仅Linux/5432/固定restore库，唯一可签正式恢复proof的现有组件 |
| B3 consumer | `core_incremental_contracts.validate_backup/validate_restore`、`core_incremental.native_apply` | 强制实际观察字段与backup/dump/operation/身份/权限/两次重放连续性，拒Windows local；在Native副作用前核proof。不为本机演练伪造审批或调用Native主机适配器 |
| App | `b1_linux_application_drill.execute`、`runtime_capability`、`backfill_primary`、`fence` | 已有真实锁包/import门、primary事务内dry/apply/repeat、旧行/其它owner保护；当前精确两原话/一个成功run集合会正确拒B3额外实体，不能删此保护来串接 |
| B7 | `tools.b1_restore_replay`、`RestoreRequest`、`b1_restore_replay_worker.replay` | 精确stage恢复库/owner、固定候选底层apply_withdrawals、无发送；现CLI没有proof参数，需编排器先核正式B3proof；原state hash算法不同于B3 |

已完整读取上述组件、storage SQL/transport、consumer契约、当前App六源文件，以及固定b9的LangGraphRuntime、B3样本和Outbox claim实现。读取B3样本以HEAD已提交内容为准；测试可移植性三文件的在途修改归另一代理，本片不改。B7/Native旧spawn缓存隔离也由另一代理处理，本计划仅列依赖，不抢其接点。

## Progress

- [x] (2026-10-21 09:26 +08:00) 重读指令板v2和已提交组件/调用方，确认当前只读任务范围及正式No-Go。
- [x] (2026-10-21 09:26 +08:00) 确认storage缺checkpoint、App/B3 fixture集合冲突、B3 local/B7目标不相容、B3/B7哈希算法不相同，设计各自明确门。
- [x] (2026-10-21 09:26 +08:00) 完成Linux原样入口、Windows部分路径、严格共享fixture与文件所有权建议；无新执行或通过数字。
- [ ] root审阅设计并分配具体源码/测试文件后，先实现schema4 bootstrap/fixture与App受信profile。
- [ ] Windows真实隔离PG验证可移植部分和正式拒绝边界；当前没有运行本任务测试。
- [ ] 外部环境恢复且获准重新进入后，在同一本机Linux PG15执行全部正式阶段，取得真实B3/B7/fcntl链。当前阻塞，不能等待或第三次探测。

## Surprises & Discoveries

storage-preparation在checkpoint或meaningful旧助手结果建立前已经产生schema4.dump，且没有导出B2旁账。必须保留旧dump/回执，再生成一个新的合格应用备份，不能覆盖旧文件或把application_ready改true。其state算法与B3/core_incremental_pg._state一致，但相同算法不代表旧输入已经包含checkpoint。

B3样本含额外source/fact/case/draw、失败run、checkpoint私有合成值及pending收据；App当前两条已知message和一个成功run的精确集合不接受这些。仅增加“有synthetic-run marker”或接受调用方任意expected_rows会重新产生吞入额外原话的风险，必须建立有版本、完整集合与逐项来源约束的共同fixture。

B3的全状态hash是每张Core表及四张public checkpoint表的SQL SHA256，再digest有序map；旧B7是Core-only的MD5行聚合再SHA256。两者都叫state_before/after_sha256，**不能相互直接比较**。总编排保留原回执，另在B7前后独立计算B3 canonical全状态，显式记录算法名和范围。旧B7回执本身不能证明public checkpoint未复活。

B7现有CLI没有--proof或--restore-proof参数。其local仍固定数据库zhiming_core_b1_restore，允许的临时schema与B3 local的随机数据库/public checkpoint布局不是同一个目标。Windows上把B3 local回执改为formal、复制schema或放宽任一allowlist都不成立。

固定b9的`LangGraphRuntime(repo)`会在构造时setup真实PostgresSaver表，但不执行模型；若repo用默认initialize=True会同时升级Core。bootstrap必须用initialize=False，先核Core仅1–4，setup后再核仍仅1–4。已有B3测试的latest辅助会默认初始化repo；总编排不能照搬这一默认值后声称源库仍停留schema4。

## Decision Log

2026-10-21 09:26 +08:00 / root：本片只新计划，不编码、不pytest/PG/环境探测；完整设计后再分配具体实现。B3/consumer/App/storage原件保留；B3测试可移植性和旧spawn缓存归现有代理，不覆盖。

2026-10-21 09:26 +08:00 / Codex建议：采用一套版本化共同fixture、明确phase快照与有限工具动作。App原两消息profile默认保留；新增共同profile只接受编译在受审controller里的规范，不能传任意SQL、正文、实体白名单或“忽略额外原话”开关。正式B3与B7的目标/平台/权限/consumer护栏完全不变。该实现方案待root审阅，尚非代码事实。

2026-10-21 09:26 +08:00 / Codex建议：所有真实Linux应用阶段在PG容器的同一网络/文件命名空间运行，内部回环5432；Windows的55481只是外部观测端口。固定release/venv必须真实存在于Linux；PG镜像digest不等于具备Python，Windowsvenv不能复制充当Linux环境。缺环境时返回明确阻塞，不安装包、不造capability、不改镜像/挂载护栏。

## Plan of Work

### 1. 固定执行拓扑与入口

拟新增的总入口为`python -m tools.b1_bootstrap_replay_orchestration`，**当前不存在，不可当作已可运行命令**。缺省只读受审descriptor并输出有限phase计划，0PG/0Docker/0子进程。未来--apply必须同时有--quiesced、全新operation与全新output；--local-drill只选择已有限定的Windows部分路径，不能自报--platform或--admissible。

正式Linux侧的拟议调用为：

    cd "$CONTROL_DIR"
    "$CONTROL_PYTHON" -B -X pycache_prefix=/dev/null -m tools.b1_bootstrap_replay_orchestration --request "$OP/orchestration.json"
    "$CONTROL_PYTHON" -B -X pycache_prefix=/dev/null -m tools.b1_bootstrap_replay_orchestration --request "$OP/orchestration.json" --apply --quiesced --output "$OP/orchestration-result.json"

CONTROL_PYTHON与controller代码在固定b9包外的受保护目录，实际指向通过锁定依赖门的Linux Core3.11。控制器先由受信loader清环境，拒PYTHONPATH等任意导入覆盖，并在已核CONTROL_DIR启动；不能给尚未安装的controller使用-I -m后假设cwd仍在模块搜索路径。所有候选业务子进程仍精确调用`/root/zhiming-core-releases/b9a89b6f84f7bebb640de080548010859aae630c/venv/core/bin/python`，清环境、-I/-B/null pycache prefix和受信显式导入路径校验保持；不接受任意shell/body字符串输入。

本机Windows驱动层只复用已审LocalDocker的固定pipe、容器/volume标签和PG镜像digest核验，将受审controller/候选原件交给Linux侧固定phase。当前transport只允许pgdata与/b1两卷，不因本计划新增第三挂载或换衍生image。若容器里缺固定位置的Linux解释器/候选，P1及以后必须停；P0可能已创建专属存储/SQL合成初态，应如实保留其不可admit回执，而不能说整个apply零PG副作用。今后准备已锁Linux环境的具体本机动作需单独形成受审步骤，不能在总编排中偷偷下载、pip安装、重建Docker或“修好后再试”。此轮两次环境尝试额度仍用尽。

descriptor拟为严格`b1-bootstrap-replay-request-v1`：operation_id、scope=local_rehearsal、固定target/manifest、controller文件hash、fixture_profile及规范hash、原storage回执hash、本机Docker容器/镜像/volume身份、Linux侧各受保护路径、pg_dump/pg_restore绝对路径/hash、logical stage request。只允许固定字段；DSN、口令、token不进JSON/argv。source/restore owner与writer仅由专用loader传env。所有Linux路径限定同一新/b1/operation目录，release路径单独固定；symlink、旧输出、已有目标冲突即停。

Docker层观测的容器ID/image/labels/端口与每个Linux phase的实际sys.platform、PG15 Linux build/回环5432/库角色必须共同进入body-free链；不能只复制上个phase的platform布尔值。源stage和restore须在同一已核容器、同一PG端点；如有可用只读cluster identity一并绑定，无权读取则不靠grant新系统权限伪造该观察。

### 2. 共同fixture与不可放宽的App边界

共同规范拟名`b1-bootstrap-replay-fixture-v1`，含三组固定目的的资料。第一组保留App的两条legacy原话、一个succeeded旧run及固定SYNTHETIC_B1_LEGACY_REPLY，旧原话不预加thread/search元数据，以确保首次三类回填都有实际变化。第二组为B3专用、与旧助手run依赖分离的已知合成source、授权fact、单个case/draw、终态失败run与该run:e0的真实checkpoint。第三组为两条初始pending/0attempt的旧收据，最新阶段改为sent+合成receipt及sending/uncertain可单调导出的状态。secondary只作保持原样的对照。

规范规定**全部**owner/subject/entity/run/outbox/draw/operation集合、已知合成文本模板、source/ref/revision关系和各phase允许的状态变化；所有正文都来自受审代码常量，不从用户输入、服务器或任意JSON读入。随机业务ID由固定b9实际服务返回，绑定到精确operation输入和repo已落operation结果；不是由调用方任意列出一批“允许ID”。真实生成的seed receipt只留ID/摘要，绑定controller/规范/b9/库身份及canonical schema4快照，审阅时固定其整件hash。新增原话/owner/run、同ID改正文、伪operation、错来源或额外draw，即使有人重算外层manifest也在写前拒。

App将新增受信的共同profile委托，旧两消息profile及原48目标保持。共同profile在回填前必须同时核编译规范、seed/transition回执的输入链、当前完整集合与phase快照；不能删掉现synthetic_fixture、只检查一个marker或接受调用方自报passed。回填事务/表锁/旧原文与revision/非回填表/secondary保持、primary owner revision只按新助手数量增长的现有约束继续有效。这里是明确待实现的App桥，**现有App CLI不能直接处理共同fixture**。

### 3. 分阶段执行与观察

| phase | 真实动作与继续门 | 新的不可覆盖产物 |
| --- | --- | --- |
| P0 storage | 显式storage-preparation；保留正式restore空，Core仅1–4。旧完整SQL模式不得先运行消耗目标 | 原storage回执与旧纯SQLdump，明确不可作为合格B2 |
| P1 bootstrap/seed | 核旧fixture为精确存储初态，再用固定b9、initialize=False建立共同fixture和真实LangGraph checkpoint；前后Core仍只1–4，无queued/running/有效lease | 版本化seed receipt、Core/public四表canonical快照 |
| P2 qualified B2 | 所有业务writer缺席；固定pg_dump真实导出schema4全库，包含public四表；固定b9真实export_withdrawals导出backup-ledger | 新application/schema4-checkpoint.dump、backup-ledger.json、b1-quiesced-backup-v1 backup对象 |
| P3 latest delta | 在源schema4用固定b9实际执行fact/source撤销、draw删除、收据状态单调更新；仍initialize=False、前后核1–4；导出完整owner集合latest-ledger | transition receipt、最新ledger原字节hash、源phase快照；不是手写撤销JSON |
| P4 B3唯一恢复 | 再核正式目标为空；由原B3 CLI独自pg_restore→schema4全状态→迁5–7/授予→实际最新账本两遍→权限/无复活核验 | 正式Linux B3proof；原consumer完整validate_restore通过 |
| P5 source migrate/backfill | 在同一容器源stage真实固定b9迁5–7，核七checksum/owner/权限；共同profile primary dry/apply/repeat，保持其余owner/撤销/牌阵/收据 | 独立source migration receipt、App回填回执及三项repeat严格0 |
| P6 exact B7 twice | 所有B3/observer连接已关闭；在原正式restore库上调用原B7 CLI两遍，每次新输出并核原账本/候选/目标 | 原B7两回执与独立canonical前后观察，第二次changed=false |
| P7 fence/rollback/control | 同一Linux runtime执行已有App真实fcntl/exec；另在独立空b1_drill_rollback恢复同一合格dump并核schema4/全状态 | 独立fence回执、schema4回滚对照；不触正式restore、不宣Native生产恢复 |

P1在已有storage目录内新增application子目录0700，合格dump/ledger/receipt均0600。旧schema4.dump和storage回执保留，不覆盖或重签。P2用同一一致快照/锁保护生成dump、backup-ledger与canonical source_state_sha256；例如以受信owner连接持有只读repeatable-read快照，pg_dump使用该导出snapshot，ledger读取同一快照，并在关闭后复核无漂移。dump所需自己的临时连接按精确PID/阶段识别，不把任意外部会话当成“备份连接”；其它writer或队列一律停。

P3的schema4业务兼容性必须先用Windows真实PG窄测证明，不能从现有latest辅助的默认initialize=True推断。如果固定b9的撤销路径确实需要5–7，先记录阻塞再向root提有独立delta副本的替代设计；不得为得到latest ledger提前偷迁源库、修改b9、手填撤销或谎称源库仍是4。本片只提出这一验证门，没有声称兼容已证。

backup对象严格复用consumer字段：operation_id、database=zhiming_core_stage、target/manifest、source_state_sha256、dump_sha256、withdrawals_sha256、mode=0600、body_free_withdrawals=true。这些值均来自实际文件/连接；backup-ledger是实际body-free exporter结果，不能仅由调用方把body_free标true。最晚在B3前后重算全部输入hash；最新账本必须包含旧owner/撤销/draw/收据的单调集合。

P4调用现有B3真实CLI参数，不增加“已恢复/已通过”开关：

    "$CONTROL_PYTHON" -m tools.b1_restore_proof --request "$OP/request-stage.json" --backup "$OP/application/backup.json" --dump "$OP/application/schema4-checkpoint.dump" --backup-ledger "$OP/application/backup-ledger.json" --ledger "$OP/application/latest-ledger.json" --ledger-sha256 "$LATEST_SHA" --database zhiming_core_b1_restore --candidate-source "$B9_RELEASE" --candidate-python "$B9_PYTHON" --pg-restore "$PG_RESTORE" --pg-restore-sha256 "$PG_RESTORE_SHA" --apply --quiesced --output "$OP/application/restore-proof.json"

source-owner、restore-owner/writer连接全分开；空恢复目标连enum/domain/非默认namespace/extension也不能有。B3归原生成器所有，外部编排不抢其pg_restore或权限签收，不用state=true合成proof。完成后consumer核正式origin与所有字段，并把该proof/dump/ledger/source实例的整件hash锁进后续phase，不能用其它已绿proof替换。

### 4. 精确B7与两种哈希的正确绑定

B7前先核正式B3proof与backup绑定、latest原字节hash、固定candidate及完整owner集合。在restore库用B3 canonical observer测当前状态必须等于proof.replay_second.state_after_sha256，关闭连接，再运行精确CLI；**不向现有B7杜撰--proof参数**：

    "$CONTROL_PYTHON" -m tools.b1_restore_replay --operation-id "$B7_FIRST_OPERATION" --scope stage --database zhiming_core_b1_restore --schema mingjing_core --candidate-source "$B9_RELEASE" --candidate-python "$B9_PYTHON" --ledger "$OP/application/latest-ledger.json" --ledger-sha256 "$LATEST_SHA" --apply --quiesced --output "$OP/application/b7-first.json"

第二遍使用另一个稳定operation_id与全新b7-repeat.json，其余输入原样。B3已真实应用最新ledger，故B7首次可能false；必须要求B3的真实fixture变化/撤销/收据证据完整，不伪造B7首次true。第二遍必须false，其B7私有算法的before/after相同、两遍连续；外层canonical全状态前后也全部相同。每遍前后检查已撤回实体/事实/draw、对应checkpoint为空，sent/uncertain实际状态/receipt/attempts保持。

回执明确分列`canonical_state_algorithm=core-public-checkpoint-sha256-map-v1`与`b7_state_algorithm=legacy-core-md5-aggregate-sha256-v1`，各自原值保留，不改旧回执或给它增加假的全状态hash。固定b9的`OutboxService(repo).claim_delivery(owner=..., outbox_id=...)`对已sent应拒领取、uncertain应DeliveryUncertain，前后canonical摘要不变；只调用claim，不创建sender或绑定真实消息出口。

### 5. Windows能证明与不能证明的边界

| 可在Windows真实隔离PG15覆盖 | 绝不能据此宣称 |
| --- | --- |
| 新随机source b1_application_<32hex>及restore b1_restore_proof_<32hex>、各自独立owner/writer；固定b9 schema4 seed/checkpoint、真实dump/restore与迁7 | 固定正式stage/restore库被验证、Linux PG build或5432拓扑已通过 |
| 共同profile完整集合/来源/篡改/额外原话反例，primary dry/apply/repeat与原子回滚 | 仅一个marker可以授权其它用户资料或任意实体 |
| 原B3 --local-drill生成local回执、consumer必须拒绝它，backup/ledger/restore绑定与权限探针 | 把local schema改formal、admissible改true或复制临时schema即可交给正式B7 |
| B7 argv构造/输入绑定/算法分列的纯契约测试；已有旧B7独立组件测试仍是独立测试 | 在B3随机restore上跑了精确B7正式库路径或整个Linux链已绿 |
| Windows拒绝实际fcntl、真实b9维护门先拒配置、子进程缓存隔离 | Linux共享fd穿exec、POSIX0700/0600/systemd/已安装Hermes或生产恢复通过 |

Windows总编排到B3 local/共同profile回填即可输出**部分回执**，schema拟为b1-local-bootstrap-replay-v1、admissible=false、B7/fence=not-executed-contract-incompatible。不得自动创建固定B7库、改allowlist或换schema来补一条假全程绿。已有专用固定B7库/临时schema测试不并入这条随机目标链。测试可移植性正由另一代理独立解决，本计划不复制其环境准备实现。

## Validation and Acceptance

本计划没有新增执行结果。未来先以有限动作替身验证默认零连接、阶段顺序、失败停止、hash/目标绑定和不重复消耗空目标，再用真实Windows随机PG验证P1–P5可行部分；替身只能代替工具/供应商边界，不冒充PG业务通过。新增额外原话/owner/operation、把其它fixture回执贴入、缺checkpoint、错误schema前缀、旧/错ledger、换dump、外部连接、writer TEMP/DDL或账本写权限、输出已存在都必须拒绝且不留下未声明写入。

共同profile原文/修订/secondary/撤销/牌阵/Outbox不变量、dry零写、repeat三项严格整数0及后置验收失败整事务回滚要保留App原48目标，再新增真实共同fixture反例。P3源schema4撤销兼容单列真实测试，不复用会自动迁7的辅助函数。原B3正式/local边界、consumer所有proof拒绝和B7 allowlist测试原样保留。

最终Linux验收必须来自同一实际容器/image digest、Linux Core3.11/锁包/正确候选导入、PG15 Linux build/内部回环5432：合格schema4+四checkpoint全库dump、B3唯一路径真实restore并迁5–7/权限、primary三步回填、精确B7两遍+canonical无复活/不重发、真实fcntl/exec与独立schema4回滚。body-free总回执逐项链接原件hash；任何not-executed/blocked都不签完整通过。对照`docs/v4/07_评测场景集.md`的R02/F01等旧历史/撤销基础不变量，本任务不运行或改任何模型评测、基线/评分。

## Idempotence and Recovery

每个phase的请求输入hash、前置快照、实际退出码、产物hash和北京时间由程序只追加记录，时刻用get_clock+Asia/Shanghai，耗时用monotonic。新输出独占创建/0600/fsync；任何失败或写证据失败都停止并保留PG/文件/容器/维护状态，不自动清空目标、覆盖文件、重放整个operation或删除卷。已消费的B3目标不能重试生成proof；需要重新演练时交root审阅新的独立资源方案，不能自行drop/reset。

唯一预定的“重复”是同输入backfill第二apply、B3自身第二replay及精确B7第二遍，它们是计划内幂等验收，不是错误后重试。P7回滚只恢复独立空对照库，不回退源库或重启旧包，不解除Native生产恢复硬门。本机全链也不等于获准SSH/stage部署；30仍No-Go就不触服务器。

## Interfaces and Dependencies

以下仅为建议所有权，root批准后才创建/修改。每源码≤400行、函数≤60行，无新仓库依赖/迁移，固定b9不变。

| 建议文件范围 | 责任 | 边界 |
| --- | --- | --- |
| 新tools/b1_bootstrap_replay_orchestration.py、_contracts.py、_process.py | 有限phase入口/descriptor/不可覆盖链、固定本机资源与Linux子进程 | 不接受任意SQL/command/body/platform；不改Docker pipe/挂载/镜像护栏 |
| 新tools/b1_bootstrap_replay_seed.py、_backup.py、_observe.py | 编译共同规范、schema4 checkpoint/实际B2、source latest/迁移观察及canonical/B7绑定 | 固定b9真实业务；只产生合成资料；不能造proof或修改候选 |
| App _contracts.py/_backfill.py最小桥及专属profile helper | 保留legacy profile并增加受信共同profile/seed链校验 | root明确授权后再碰；原身份/原文/并发/回滚负例不删 |
| storage-preparation最小显式接点 | 只为新编排预留/引用资源，旧dump回执不可重写 | 默认与原完整SQL路径保持；不先恢复B3目标 |
| 新tests/v4/release/test_b1_bootstrap_replay*.py及独立合成fixture支持 | 零副作用/共同profile/真实PG/正式拒绝/算法错绑反例 | Windows部分与Linux完整验收分组，禁止用替身宣正式通过 |

`tools/b1_restore_proof*`及其可移植测试、consumer、B7/Native spawn缓存修复、B6/runbook、前端/排盘/模块均保留既有代理所有权；本计划不要求与他们同时改文件。正式B3/consumer/B7原CLI与schema保持原样，由编排器调用/验证。拟议总回执是body-free观察聚合，不是新的restore-proof schema，也不自动把执行单五门改为解除。

## Artifacts and Notes

原storage/App/B3及旧失败/通过证据均保留。未来私有dump、账本、seed细节留Linux/b1/operation下受保护目录，不入Git；公开`docs/v4/evidence/B1/<date>-bootstrap-replay*.json/md`只含固定版本、hash、身份摘要、安全计数、门状态和真实耗时。没有Linux实跑就不创建成功linux-actual.json，也不把Windows部分回执复制到该名称。

## Outcomes & Retrospective

本片仅完成完整源码审计和总编排设计，新增此一计划；无测试/PG/容器/服务器/模型/消息动作，亦无新通过数字。已消除设计上的机械串接假设，明确共同fixture、合格B2、B3唯一空目标、两种hash、Windows不可接正式B7与Linux运行环境前提。仍待root分配实现和真实环境；指令板v2/30号No-Go、两次环境尝试用尽及全部正式护栏不变。

## 修订记录

- 2026-10-21 09:26 +08:00 创建：仅计划，固定已提交源码基准、共同fixture/App桥、B2/B3/B7真实输入链、哈希算法差异、Linux拓扑与Windows不可覆盖项，提出分文件所有权待root审阅。
- 2026-10-21 09:28 +08:00 冻结前纠正：初稿误填09:24，已按文件CreationTimeUtc=2026-10-21T01:26:03.3041005Z改为实际09:26；同时修正未安装controller不能-I -m读取cwd的示例，固定候选子进程-I/-B/-X不变，并明确P0可能已写合成存储但后续runtime缺失仍须停。
