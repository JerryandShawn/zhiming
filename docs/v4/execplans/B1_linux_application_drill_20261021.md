# B1：补齐Linux应用回填、重放与进程栅栏演练

本ExecPlan遵循`.agent/PLANS.md`，北京时间2026-10-21 08:44创建。只读审计后已获root具体工具授权，storage首片已提交，应用第二片在本机测试；没有运行Docker/WSL、服务器、模型或飞书。主树`C:/Users/Administrator/Documents/Codex/zhiming-v4`，审计基准c7d760addc63ea9c8a12d15d08123b32f6e17238。指令板v2与30号明确No-Go；两次环境尝试已耗尽，本计划不允许第三次启动/修复/探测。

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
- [x] (2026-10-21 09:00 +08:00) root已推storage首片a2adc40→63776ecc/tree933a50be，并独立复跑26目标；source_state与B3/core_incremental_pg._state确为相同算法，后续仍需真实输入对照。
- [x] (2026-10-21 09:00 +08:00) 应用runtime/backfill/fence/worker与默认计划入口已实现首轮；38目标/21.51秒包括随机Windows PG真实固定b9回填，不是Linux。新增依赖extras、null-passfile和整事务回滚反例等待共享窄位复验。
- [x] (2026-10-21 09:12 +08:00) 最终应用组合48pass/126.25秒（session94954），40本机契约/实际Python目标与8真实随机Windows PG；包括真实污染pyc对照、实际critical imports、固定b9回填三步、原子回滚和额外原话拒绝。无Linux/PG容器/实际fcntl通过证据。
- [x] (2026-10-21 09:12 +08:00) 传输替身首片26目标与应用本机48目标分别通过；Windows随机PG证明应用业务和失败回滚，明确不签Linux通过或正式proof。
- [ ] Linux能力门恢复后，在同一真实PG15取得回填、B7与跨exec fence证据；环境仍阻塞，不等待或反复重试。

## Surprises & Discoveries

`b1_linux_drill.plan()`已经明确application_backfill=not-exercised-by-this-SQL-drill，结果又写native_host_switch=not-verified和B7_replay=separate-reviewed-entry-required。脚本没有运行候选Python的步骤，镜像只核postgres:15的Linux身份/digest；不能据此断言其中存在Core 3.11或锁定psycopg/LangGraph等。Windowsvenv不能当Linux运行环境。缺解释器或依赖应报独立能力门，不自动安装新依赖、改锁或下载新runtime。

SQL fixture只有primary/secondary原消息、一个result为空的succeeded run和已sent/uncertain收据。它可触发消息元数据/搜索token回填，却不能证明成功旧回复补写，更不能证明“备份后新增撤销/送达状态”在旧dump中被重新应用。应用fixture须真实固定b9业务创建事实、待撤销原话、draw/tombstone、旧回复及checkpoint，且输出只给hash和计数。

旧execute会先restore到zhiming_core_b1_restore并迁7；B3新生成器正当拒非空目标。重复跑旧execute又拒任一既有目标库，且新输出不可覆盖。因此不能将两条现有命令机械顺接，不能drop/clean/reset解决。root明确先提供storage-preparation新阶段，将正式恢复库保留空，由B3成为唯一恢复写入者。

Native publication有NATIVE_PRODUCTION_RESTORE_UNAVAILABLE硬门；它不是stage应用演练后可顺带解除的门。PG镜像也未提供systemd/native主机环境。小范围真实fcntl证明不能冒充三个unit、实际Hermes安装、/proc会话归属或生产Native restore通过。

真实本机Core解释器通过固定b9全部锁包版本核对，但没有pip模块，初次能力测试31pass/1fail，失败码CORE_LOCKED_DEPENDENCIES_INVALID发生在任何PG写入前。pip本身不在Core锁中，因此改用已锁定packaging==26.3与importlib.metadata逐项核Requires-Dist、版本、平台marker和传递extras；不安装pip，不把这一检查称pip check。默认DSN同时显式指定空passfile，禁止读取用户home的隐式凭据。

## Decision Log

2026-10-21 08:44 +08:00 / root：先新增可独立审阅的storage-preparation阶段，原完整SQL模式可保留，但不得重复使用/覆盖B3正式目标；不改B3空库护栏。B3自行恢复、回放和权限签proof，应用回填与跨exec fence另留证据。工具所有权待root明确，本任务现在不改tools。

2026-10-21 08:44 +08:00 / Codex：B7在B3已经实际回放的恢复状态上跑两次可以首次false；必须绑定B3的真实输入ledger、dump、目标、前后状态和首次语义变更证据，不能伪造changed=true或将B3变更记成B7变更。第二次必须changed=false且状态hash相等；源账本保持同字节、连接全部关闭后再起B7子进程。

2026-10-21 08:44 +08:00 / Codex：先验证既有Linux Core3.11、锁文件/包清单/import能力和候选导入路径。缺时保持独立阻塞，本工具不apt/pip安装或扩镜像，不拿Windows测试代替。准备已锁运行环境本身不构成新增仓库依赖，但本轮两次Linux探测额度不会因此恢复。应用controller放固定发布包之外，候选目录完整manifest不变。

2026-10-21 09:09 +08:00 / root、Codex：Core锁本来不要求pip，能力门使用已锁packaging与实际包metadata验证传递依赖和extras，并真实import psycopg/LangGraph/PostgresSaver/Pydantic及候选repo/memory/runtime，绝不构造连接或供应商。root实测指出-I/-B仍可读污染pyc；本片所有应用worker与fence writer子进程统一加-X pycache_prefix=<abspath(os.devnull)>，候选缓存不读取、不删改包。实际Linux锁/exec仍待环境；本机合成污染缓存对照单独留证。

## Plan of Work

2026-10-21 09:00 +08:00 / 当前应用第二片将受信CLI收窄为phase=runtime|backfill|fence，精确输入为--operation-id、--candidate-source、--candidate-python和全新--output，只有--apply才启动固定解释器。--local-drill始终签独立非Linux回执；backfill只接受新随机b1_application_/b1_restore_proof_库的独立owner与55480/55481，正式仅固定stage/5432且还要真实Linux身份和精确synthetic marker。B1_APPLICATION_OWNER_DSN仅进入backfill子进程，其它phase无DSN；不继承PG/供应商/飞书密钥或追踪设置。bootstrap/checkpoint/B2和B7总编排尚未接入，本片不接受相应phase伪称完成。

第一片在旧drill中新增显式storage-preparation计划与回执：固定专属资源/镜像/角色、schema4合成源、真实dump和0700/0600、完整源状态hash、备份账本、空恢复目标；遇既有资源冲突仍停。旧SQL完整演练模式不默认改变；两种模式必须明确互斥，不让旧模式预先消费B3目标。backup对象用既有validate_backup契约，由实际观察生成，不手填source_state_sha256或body_free标记。

第二片新增外部应用drill的preflight。只读校验storage回执、固定b9 manifest、同一PG15镜像/库/角色/端口、Linux解释器realpath/hash/3.11版本、锁文件及锁定包清单和实际导入位置。应用过程只运行在明确Linux worker中；PG镜像若不含解释器则阻塞。控制器不能以--platform参数声称Linux，不能把host Windows Python放进Linux证明。

第三片按受审顺序由B3完成正式空目标恢复/迁移/最新账本两次回放/角色校验；源stage只迁5–7后执行primary回填。回填参考原文摘要算法，dry-run前后状态必须相同，首次apply三个写入计数至少有预期非零值，第二apply的message_metadata/search_tokens/assistant_created全部严格整数0。assistant_existing/assistant_skipped/invalid_time等诊断不是“变更”，不错误要求其全为0。secondary及其它owner计数/摘要不变；原文/原revision/既有回执、draw不被改写。

第四片在B3已关闭所有连接的恢复库上用精确现有B7 CLI跑两次，各写独立新0600回执，绑定相同ledger/dump/候选/proof。检查不复活原话/事实/draw、sent/uncertain不再被Outbox claim，第二次changed=false且前后hash相同。没有sender，不创建真实模型或飞书入口。B3本地演练schema与正式schema不得互相冒充。

第五片用同一Linux runtime的专属临时路径做真实多进程fcntl：writer取共享锁→真实exec进无DB/模型的合成惰性CLI→另一进程取排他锁应在deadline内失败→writer退出后排他成功→维护门在配置/DB前拒绝。只替换受审临时路径与无业务配置边界，不mock fcntl、os.exec或进程结果；记录pid/exit/monotonic耗时，不靠固定sleep判定成功。此片仅证明锁/exec，不签systemd/生产切换通过。

## Interfaces and Dependencies

已实现入口为`python -m tools.b1_linux_application_drill`，默认仅计划、无Docker/PG/子进程；显式--apply还须--operation-id、--phase runtime|backfill|fence、--candidate-source、--candidate-python、全新绝对--output，可选--local-drill。B1_APPLICATION_OWNER_DSN只用于backfill；先拒隐式libpq覆盖、非回环/端口/库/owner及未知DSN键，再加入hostaddr、5秒连接超时与空passfile。正式固定b9 release/venv、Linux/PG15 Linux build/stage库；本机只新随机b1_application_/b1_restore_proof_库且回执b1-local-application-drill-v1、admissible_linux=false。没有任意SQL/命令/远端DSN输入。

backfill只处理精确primary/secondary合成原话、单个synthetic-run及确定的助手ID，未知额外实体/run在写前拒；实际业务来自完整manifest不变的b9。外层PG事务覆盖dry/apply/repeat与验收，所有相关表锁定；dry前后完整状态hash不变，首次三项均正数、repeat三项0；旧实体/secondary/非回填表不变，primary owner revision只允许按新增助手数精确增加。验收失败整事务回滚。fence复用真实固定deploy_core锁与exec，只替换专属临时路径/惰性CLI/无业务配置，不假冒systemd或已安装Hermes。回执始终stage_acceptance/publication=false、models/sends=0，正式Linux回执也不是B3proof或stage Go。storage/B2 bootstrap、B3/B7总编排仍须下一片，不接受未实现phase。

root已授权新文件统一为`tools/b1_linux_application_drill*.py`前缀，按runtime/backfill/fence/worker分拆及对应`tests/v4/release/test_b1_linux_application*.py`；另授权现有`b1_linux_drill.py/_sql.py`的storage-preparation最小接点。transport仍不改；`tools/b1_restore_proof*`、B6及既有replay/publication工具不占用、不覆盖。无新增依赖、迁移或固定包变更。B3要求dump前真实初始化public四张checkpoint表，纯SQL旧dump不能冒充合格B3备份；缺应用runtime时只能留明确不可admit的存储切片。

## Validation and Acceptance

对应指令板v2第2/3项、B1 B3/B4/B7，以及07评测R02的旧助手回复存储基础和F01的事实撤销传播前提；本片不宣R02完整模型语义评测已通过。默认零连接；源/candidate/runtime/digest/角色/端口/目录/私有权限任一不符先拒绝；非空restore拒绝且无删除。全新storage→真实B3恢复proof可绑定，primary dry-run不写/首次apply有意义/第二次三个变更计数0，其它owner原摘要不变。B7两次状态hash一致、第二次false，原文/draw/撤销和sent/uncertain不复活。真实多进程及exec覆盖共享fd保留、排他阻塞/超时/退出后可用、维护门先拒；失败均无DB/模型/外发。

纯测试/Windows PG结果须独立schema与admissible_linux=false，不给Linuxactual.json填通过值。完整B1通过需要固定镜像及LinuxPG、Core锁定runtime、B3、应用回填、B7和fcntl全部实测，并另有B6等门。新增测试数字只说明下方精确本机切片；不能拿44项或后续组合替代Linux证据。

## Idempotence and Recovery

默认校验可重跑；apply不自动重试。备份、库、目录、回执已存在时保留并停，不覆盖、不drop、不清卷。回填第二次apply和账本第二次重放是受审的正向幂等验证步骤，不是异常后重试。DB提交后写证据失败可能留下已变更状态，须停止供审查，不能为了取得绿回执再执行。环境恢复次数已耗尽，本计划阶段不触发任何新探测。

## Artifacts and Notes

差额证据为`docs/v4/evidence/B1/2026-10-21-linux-application-gap.md`。未来Linux应用回执可独立置`2026-10-21-linux-application-actual.json`，与旧SQL的`linux-actual.json`和B3正式proof分开，不在未运行时创建成功文件。私有dump/账本/配置留受保护目录，不进Git。

## Outcomes & Retrospective

只读审计和设计完成后获root具体工具授权，已实现storage-preparation首片：空恢复目标预留与实际schema4校验、纯SQL回执明确不能admit，4新目标加22既有传输目标26pass/0.27秒。应用runtime、真实checkpoint/bootstrap、primary回填、B7接线和跨exec worker继续实施，均未宣Linux通过。两次Docker/WSL额度不会再使用；31号生产Native恢复按指令板排stage之后，不在本片解除。首片3源码/测及更新文档交root，下一片不覆盖已冻首片。

09:00应用第二片首轮38pass/21.51秒，真实Windows随机PG证明固定b9 primary干跑状态不变、首次三项变更非零、二次三项0，旧原文/修订和secondary摘要不变；已sent/uncertain不变。并发连接、schema checksum、合成marker、重复整体入口均拒绝。Linux flock/exec源码已提供而实际Linux仍未运行，不能把Windows平台拒绝用例写作真实fcntl通过；补充回滚/依赖负例复验后再冻结。

09:12最终48pass/126.25秒：新controller六源文件与两个测试文件可独立审阅；运行计划零连接，真实Core锁包/依赖/关键import只读核验通过，未安装包。污染pyc反例在真实本机Python上证明null prefix读取源码；所有worker与fence writer统一使用此参数。8个PG用例使用全新随机库、固定b9完整manifest与真实MemoryService/backfill；额外primary原话前置拒、验收失败整事务回滚、二次首次标签不冒充新变化均通过。Ruff/格式、400/60、diff检查通过。此片不更改schema、b9或已有drill默认路径；依赖B3的只读state_hash/测试fixture，需其同批或先提交。

剩余明确为：实际Linux解释器/PG15容器与fcntl/exec实跑；固定schema4的checkpoint/bootstrap及合格B2账本/dump生成；B3正式恢复后精确B7两遍与proof输入绑定；完整SQL/storage→应用阶段的总编排。现有CLI不能代替上述未接部分，不能发布B1 Go或解除任何Native生产硬门。失败后停审、不自动重跑、不删除候选/缓存/备份。

## 修订记录

- 2026-10-21 08:44 +08:00 创建：固定真实代码差额、root的storage-preparation裁定、B3/B7重复false的证据归属及Linuxruntime能力门；仅文档，无执行。
- 2026-10-21 08:49 +08:00 获root具体代码授权，按指定前缀实施；storage模式首片26个替身目标通过，补B3必须包含public checkpoint的前提，维持无第三次环境尝试。
- 2026-10-21 09:00 +08:00 storage首片发布后记实际应用入口和38目标首轮，记录无pip环境的真实能力门修正；Linux、checkpoint/B2和B7仍分别未验/未接，不扩大完成声明。
- 2026-10-21 09:09 +08:00 按审计收紧精确合成集合、回填原子回滚、旧表/secondary与owner修订保护；44目标绿后纳critical imports与root裁定的null-prefix污染pyc隔离，待最后组合冻结。
- 2026-10-21 09:12 +08:00 记录最终48目标与精确本机边界，冻结六源/两测试/两文档交root，Linux/B2/B7总编排继续明确未完成。
