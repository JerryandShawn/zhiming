# B1 第一批上线计划：P1 + P2，保持 v3 运行时

日期：2026-10-18，Asia/Taipei。状态：**部署计划；授权A只读盘点已执行，授权B尚未申请或执行。** 已观察事实、容量No-Go及待审参数见 [B1具体操作单](B1_operation_sheet.md)。未执行部署、迁移、回填、备份、服务操作、模型请求或消息投递。预计耗时仍为待stage实测修正的排期估计，本文不构成后续写操作授权。

## 1. 发布内容与固定输入

候选代码固定为 `b9a89b6f84f7bebb640de080548010859aae630c`（P1、P2 合并后的 v4/main），不能使用持续变化的分支名或当前 P3 工作区打包。P1 合并为 `7b45a781921e6fa2e875319a12af433f0cf505b4`；P2 候选 `1444a493be5e2d26646073780d36b27570f99cb2` 与合并提交的 tree 均为 `8ed180539f655124fc76d8981df318a337292ff1`。若修复运行时代码，必须换新候选 SHA、重新 CI 和 stage 验证。

已具备的本地/CI证据：P1 [CI](https://github.com/JerryandShawn/zhiming/actions/runs/39110688435)、P2 [CI](https://github.com/JerryandShawn/zhiming/actions/runs/39114527541)；P2组合回归旧Core553、v4 615、模型208、脚本80/80及48自检。它们支持进入stage准备，**不能代替stage、真实模型或生产验收**。具体证据见 `docs/v4/evidence/P1/2026-10-18-validation.md`、`docs/v4/evidence/P2/2026-10-18-combined-validation.md`。

| B1包含 | stage应证明的行为 |
| --- | --- |
| P1模型端口及额度诊断基础 | 默认仍走v3旧适配器；只有获准的独立试验才启用P1端口。403诊断、物理POST计数等以合成传输验证 |
| 0005_agent_runtime | 新运行列、steps/events表存在；runtime默认v3；应用fast/standard/deep预算仍为2/6/10，不能因数据库移除calls上限而放开业务预算 |
| 0006_threads | 消息线程与at_ms索引有效；保留原始conversation_id、正文和来源revision |
| 0007_search | search生成列/GIN、core_embeddings与删除触发器有效；建立表不等于启用向量检索或P3 Agent |
| 历史回填 | 补线程/时间/搜索tokens，合规成功答案回填为助手消息；重复apply无新增效果，撤销来源不复活 |
| v3速赢 | intake/synthesis获得此刻、双向带日期/渠道历史；跨session接续；记忆误伤修复；报告含真实selection.date和period |
| 12356 | crisis配置与v3安全策略一致，S01危机处理优先支持、不做命理，不出现旧热线；不进行真实电话测试 |

B1不包含P3循环/调度/无痕、P1b的0008/U38/U39、P4流式、P5b分区、P8新命理算法或P10新前端；不把这些分支的文件或未跟踪文件夹带入发布包。

新增候选待决：23号要求的Charts tzdata2026.5锁修复不在b9a89b6包内。保持本候选不变；由大脑裁定修复单列后续，或明确新SHA后重跑CI/stage，不能临时补包或从P3树打包。

### 当前用户决定与模型闸门

D1继续使用Kimi Code会员；只有主线可以发真实请求。每批须用户在线并在本聊天明确开始，≤10场景，目标/评审/探针/HTTP重试合计滚动5小时≤80，批间≥20分钟；夜间零真实模型请求。`concurrency_limited`、`Access terminated`立即全停；周/月额度按最新决定停止并提示。旧文档的自动续跑、切开放平台或并发降为1后继续，不适用于本批。

D2主模型与评审目标均为k3-256k，切换前需单独获准的≤20次等价性子集；不能把未运行的k3快照改名成新模型基线。按23号第一节已确认的分批决定，B1保持盘点实际的Kimi Code端点与`KIMI_MODEL=k3`，不设置`MODELS_CONFIG`、不设置`MINGJING_MODEL_PORT=v2`，不更换端点/模型/思考配置。k3-256k等价性及切换放在P1b合并后单独执行，不作为保留旧模型的零模型B1无条件阻塞门；真实请求、守卫与开始授权仍须各自满足，不能临时绕过。

两个新端口开关需同时核对：仅有非空MODELS_CONFIG也会启用新端口。候选默认YAML仍含k3主模型和其他供应商降级链，不能拿该默认配置直接视为符合最新D1/D2；任何获准的端口试验须审阅实际解析的角色链、有效模型与会员来源，不能依赖“没有填备用Key”碰运气。

候选P1+P2尚不具备P1b完整跨进程U38。任何B1真实验收入口都须先核其实际保护能力并经审核；若最新D1要求未被满足，就保留“未验证”，先完成零模型stage步骤，不提供绕过守卫的临时入口。E1仍须单独的“开始 E1 第N批”，stage授权不能替代评测开始指令。D4不登记紧急联系人、不开使用时长提醒；配置中的危机支持保留。

## 2. 开始前必须确认的服务器现状

授权后的第一次操作只做盘点：服务器身份/系统、当前服务WorkingDirectory/ExecStart与提交、反代/端口、实际数据权威、PG15版本/数据库/schema_migrations/角色、当前模型非密钥配置、队列/CLI/定时任务/飞书入口、磁盘余量及可用备份。**不根据本机仓库或历史文档推断生产已经运行Core v3。** 盘点不输出口令、完整DSN、token或聊天正文。

| 发现的现状 | 本批采用的路径 |
| --- | --- |
| 已运行Core v3，PG账本为合法0001–0004或已知部分前缀 | 增量升级：维护停写→备份→固定包迁到7→重新授权→回填→验证→切固定版本 |
| 已是候选代码及schema 7 | 核哈希和证据；回填先dry-run，需要时幂等apply，不重复导入旧来源 |
| 仍是旧Hermes/SQLite/JSON权威，或首次建立Core PG | 先执行既有Core v3完整迁移演练及最终冻结，不能只跑backfill_v4；独立列明旧入口退役、绑定与投递账本迁移，重新确认窗口与授权 |
| 未来迁移、校验和漂移、未知混合写入、数据库/服务身份不符 | 停止后续写操作，记录差异；不得删账本、跳校验或临时改历史迁移继续 |

授权A已核实：当前7dbc951包为Core v3，stage/live同机5432、PG15.18、schema mingjing_core、账本均为1–4且与b9前缀四项hash一致，采用增量路径。实际模型k3、新端口环境变量未设置；根分区仅余约0.737GiB，容量整改是B前置门。角色、队列、备份及Hermes Core固定入口详见操作单，不把本机或历史文档当当前事实。

stage禁止把运行DSN指向live；独立数据库、角色、媒体目录、服务名和端口。8788在盘点时未监听，但执行前须复核；不改生产8787代理。历史stage已有17个owner和历史收据，建议保持离线；合成Web另用新库/新服务，具体名字与允许范围以操作单经审阅的授权B为准。所有连接详情由受保护配置注入。

## 3. Stage验证步骤与放行证据

先获得第8节中的stage访问/执行范围授权，再逐步执行；每步保存安全计数、版本、哈希、退出码和耗时到服务器受保护证据目录。发现数量异常、隐私/权限失败或超窗风险就保持隔离并报告，不自动继续生产。

### S1 固定包与隔离环境（20–45分钟，可离线准备）

先执行操作单的容量门：核定扩容/整理权限与新包、双环境、缓存、备份恢复副本的空间预算。当前0.737GiB不得直接开始服务器prepare；不自动删除cache/log/旧release或创建备份。

在干净的独立检出中固定候选SHA，按`tools/deploy_core.py bundle`生成原始Git blob包与逐文件清单，核整体SHA256。当前P3目录含未跟踪源，不用于bundle；不得为了打包删除别的工作。

以下均是**未来获准后**的模板，没有在本次执行。`REVIEWED_SHA`、`RELEASE_DIR`等只含非密钥值；`--release-dir`必须是工具要求的精确路径。

    REVIEWED_SHA=b9a89b6f84f7bebb640de080548010859aae630c
    RELEASE_DIR=/root/zhiming-core-releases/$REVIEWED_SHA
    python tools/deploy_core.py bundle --commit "$REVIEWED_SHA" --release-dir "$RELEASE_DIR" --source <干净的固定SHA检出目录> --artifact <本机受保护产物目录>/B1.tar.gz

包经获准渠道传到stage后，用同一候选的工具核包并准备独立Core/Charts Python3.11环境：

    python tools/deploy_core.py prepare --commit "$REVIEWED_SHA" --release-dir "$RELEASE_DIR" --artifact <stage包路径>/B1.tar.gz --artifact-sha256 <已核验64位SHA256>

`prepare`需授权Linux root，写release目录/安装依赖/运行合成计算验收，但不替代stage部署。Core与Charts分别按锁安装并pip check，计算验收零skip；测试依赖只放独立验收环境。禁止假定`prepare`、`plan`会迁移stage，或把`install`用于stage：现有`install/publish/maintenance/restore-withdrawals`有live目标和真实服务副作用。

prepare本身从同一候选的可信部署工具目录启动，不能用未知旧版本脚本。此后在获准服务器的同一操作环境中固定目录与解释器，迁移/授权/回填均使用它；`prepare`不安装Test锁，S5另用独立验收环境。

    cd "$RELEASE_DIR"
    CORE_PY="$RELEASE_DIR/venv/core/bin/python"

### S2 停写、盘点与备份（15–30分钟；大库另估）

只停止stage自己的Web、后台worker、报告、飞书及其他写入口并排空运行；不操作生产服务。确认没有活跃租约、排队任务或外部CLI在修改stage。回填测试前保存PG custom dump、schema账本/校验和、业务计数、owner/授权/绑定摘要、无正文撤销账本、sent/uncertain收据及运行配置版本；文件0600、目录0700，记录SHA256，绝不放进Git/公开日志。

认证来自受保护PGPASSFILE/进程环境；命令参数不得出现密码或完整带凭据DSN：

    pg_dump --host=127.0.0.1 --port=<已核验stage端口> --username=<stage迁移角色> --dbname=zhiming_core_stage --format=custom --file=<受保护目录>/B1-before.dump

迁移前只读检查active消息的`data.at_ms`：0006会把它转bigint建索引，非法/溢出旧值可能使迁移失败；也核约束名、长事务、空闲磁盘、表规模、索引构建时间。遇异常先报告具体数量/ID哈希，不能自动清洗原文、删除记录或用回填掩盖迁移前问题。

### S3 迁移0005–0007并重新授权（5–20分钟）

只使用固定候选包中的迁移，先核`migration_manifest()`与现有连续已知前缀。现有API会执行包内**全部缺失迁移**，没有`--to 7`开关；因此绝不能从含0008或P3变更的工作树运行。迁移在一个事务中完成，失败整体回滚，禁止手工删schema_migrations重试。原0001–0004保持原字节。

由stage迁移角色在隔离进程中注入`CORE_MIGRATION_DSN`、`CORE_RUNTIME_ROLE`及非密钥`CORE_STAGE_PG_PORT`；先验证dbname为stage、host/port已核、schema正确，再执行下述等价操作。环境文件由受控进程加载，不作为shell脚本`source`执行。

    "$CORE_PY" - <<'PY'
    import os
    import psycopg
    from mingjing_core.repositories.postgres import PostgresRepository, migration_manifest
    from mingjing_core.repositories.permissions import grant_runtime_tables
    if set(migration_manifest()) != set(range(1, 8)):
        raise RuntimeError('B1 package must contain exactly migrations 1..7')
    with psycopg.connect(os.environ['CORE_MIGRATION_DSN']) as preflight:
        preflight.execute('SET TRANSACTION READ ONLY')
        identity = preflight.execute(
            'SELECT current_database(), current_user, host(inet_server_addr()), '
            "current_setting('server_version_num')::int, inet_server_port()"
        ).fetchone()
        if not (identity[0] == 'zhiming_core_stage'
                and identity[1] == 'zhiming_core_stage_owner'
                and os.environ['CORE_RUNTIME_ROLE'] == 'zhiming_core_stage_writer'
                and identity[2] in ('127.0.0.1', '::1', '::ffff:127.0.0.1')
                and 150000 <= identity[3] < 160000
                and identity[4] == int(os.environ['CORE_STAGE_PG_PORT']) == 5432):
            raise RuntimeError('B1 stage database/role/server identity mismatch')
    repo = PostgresRepository(os.environ['CORE_MIGRATION_DSN'], schema='mingjing_core')
    try:
        if repo.verify_schema()['version'] != 7:
            raise RuntimeError('B1 migration version mismatch')
        with repo.connection() as connection:
            grant_runtime_tables(connection, os.environ['CORE_RUNTIME_ROLE'])
    finally:
        repo.close()
    PY

DML运行角色与迁移角色不同、非superuser/无CREATEDB/CREATEROLE、无数据库或schema CREATE、不是迁移角色成员，也不拥有业务表；新三表CRUD和序列权限存在，schema_migrations只读。既有LangGraph public checkpoint表CRUD和checkpoint_migrations只读仍保留，不执行退役LangGraph。启动应用必须`initialize=False`并通过只读verify_schema，不临时给运行角色DDL权限。

上述grant helper不是完整降权器。还需通过真实runtime连接只读核同库/host/port/schema7与有效权限，检查PUBLIC/成员继承/表ownership；不能只凭返回新三表名字判权限门通过。前缀checksum不符时在初始化前停止。

### S4 回填dry-run、apply和第二次幂等检查（10–40分钟）

先仅针对已核验的一个owner运行；多个owner逐个审阅。`backfill_v4.py`没有stage/live自动隔离护栏，调用前必须人工核数据库身份，不能只相信变量名。首次Core路径先完成受保护旧来源导入与owner建立，再由迁移角色执行`PostgresSaver.setup()`及public checkpoint授权，最后做P2回填和DML角色核验；不能对没有owner/旧来源的空库直接套用下面命令。增量路径则核实既有owner/checkpoint即可，不重跑全量导入。

    "$CORE_PY" tools/backfill_v4.py --dsn-env CORE_MIGRATION_DSN --schema mingjing_core --owner <已核验owner> --dry-run

审核dry-run后才执行下面两条apply；不要不经审阅一次性运行全部步骤。

    "$CORE_PY" tools/backfill_v4.py --dsn-env CORE_MIGRATION_DSN --schema mingjing_core --owner <已核验owner> --apply
    "$CORE_PY" tools/backfill_v4.py --dsn-env CORE_MIGRATION_DSN --schema mingjing_core --owner <同一owner> --apply

dry-run通过后才执行apply，第二次新增助手/元数据/tokens变更应为0；已有/被跳过计数可以非0。未知原时刻按created_at补元数据但保留原at文本，因此invalid_time可仍非0，应逐项解释。核对成功run、已有助手、撤销/删除/缺失来源的解释，不能简单要求“助手数=所有成功run数”。核正文与原source/revision/time、conversation_id不变；新增life线程、UTC at_ms、来源/血缘与搜索tokens符合投影规则；助手原话不能转成用户事实。异常数量保持停写，报告后再决定，不用修改稳定ID强行重复导入。工具内部每页1000条不代表分批提交：dry-run/apply均占整个owner事务锁；中断整次回滚，没有resume/limit/rollback参数。全量耗时须在stage先测。

增量Core PG路径不重跑旧SQLite导入；首次Core路径才按已批准的冻结副本/显式bindings运行`migration_core.py`与`verify_core_stage.py`。后者会执行真实迁移、旧来源导入及合成恢复测试，**不是通用只读检查**，不能随手对已有stage数据重复执行。

### S5 零模型回归与v3速赢（30–60分钟）

旧Core及pytest写测试数据，必须另用可丢弃的`core_test_b1`验收库及合成owner/schema，绝不将CORE_TEST_DSN设为live或含实际历史的stage库。独立测试进程的CORE_TEST_DSN、ZHIMING_TEST_DSN和ZHIMING_DATABASE_URL全部指向验收库；需DDL/临时角色的测试使用隔离验收权限，不提升stage运行角色。Core/Charts分离，清空模型密钥与追踪；外部传输只用替身。

    python -m unittest discover -s tests -p 'test_core*.py' -v
    python -m pytest tests/v4 -q
    python tools/eval/runner.py --mode scripted --target fake --self-test --output <受保护B1证据目录>/scripted

上述命令在**干净固定B1候选的验收环境**执行，不在当前P3目录执行。另运行既有npm/DOM/构建检查和真实Charts合成计算，零skip；不更改web源码。验收矩阵如下，记录真实业务结果/PG计数/安全payload断言，不只记录HTTP200。

| 验证 | 可观察结果 |
| --- | --- |
| 此刻/跨日/时区 | intake与synthesis均有now；同epoch程序时刻稳定，新的用户轮/日期会更新；日历、调休、节气口径及未公布年份标记正确 |
| T01–T08/T10/T11/T13 | 对照07和P2时间金标；在脚本/合成业务中核具体日期/星期，不用模型评审覆盖硬事实错误 |
| R02/R03/R06 | 用户与助手历史带at/channel，跨session及渠道同life线程接续；默认最近30条消息，不冒称P3完整30轮引擎；旧/api/history结构/cursor不变、不双份助手；异owner/subject和事项范围不泄漏 |
| M03/M09/M10与误伤反例 | “别忘了记住”不误拒；明确拒存仍拒；分句假设/第三人/授权后置按原话验证，敏感信息仍先确认 |
| 来源撤销、固定牌与投递 | 删除/更正后历史/搜索/派生/向量不残留；助手不能变事实；失败恢复不重抽，outbox sent/uncertain不重发；备份恢复先重放最新撤销/收据 |
| 报告 | 固定Clock核selection.date、period.start/end、准备/投递日期与时区；dry-run不真实发送，也不改既有日程 |
| S01/12356 | config/crisis.yaml与v3 SYSTEM_POLICY逐项一致；真实业务+脚本模型验证指定support路线、提示词号码注入与交付契约；脚本回答包含号码不证明真实危机识别、措辞或供应商安全质量 |
| 一万消息查询 | 同硬件测snapshot p95<150ms并取到最新消息，预热10次、正式采样≥30次，记录样本量/p50/p95；不把snapshot成绩扩称整个history API性能保证 |

相对时间验证要保留原话said_at与本轮now供模型辨别，不能把P3 U4的event_at自动绝对化、U7跨事项24小时防反复列为B1已实现。12356当前是严格配置审核与`core3-policy-p2.1`系统提示接线；P3 U41确定性模板/20秒故障兜底不在本候选中，不能声称模型不可用时也保证交付热线。

### S6 Stage Web/API与恢复演练（20–40分钟）

stage进程使用独立空队列的合成应用库/合成owner、独立媒体/基础目录、独立认证，不加载生产.env或真实渠道绑定；`CORE_FEISHU_ENABLED=false`，不启动任何stage或live报告/飞书投递服务，阻断模型与渠道出站，确认无模型密钥。带真实历史的stage副本先做停写状态下的数据验证，不能未经审阅就启动Web。

原因：候选Web lifespan会自动recover并领取queued_run；即使只查health，也可能在后台恢复旧模型任务。没有已实现的“只读启动/禁worker”开关可在此冒用。启动前要求队列/活跃run为0；若无法满足，就保持Web未启动，改用真实PG+ScriptedModel业务测试，待另行明确恢复授权。

启动获准的隔离stage Web后，检查登录、授权/未授权`/api/health`、`/api/state`、`/api/history`、固定牌读取与旧前端DOM；只读请求不携私密正文到公开日志。健康应显示core3.0/PostgreSQL/LangGraph；其model字段在新端口shim下可能显示test，不能单凭它证明provider/model，实际身份核安全model_call/run元数据。所有网络请求仅限获准stage回环/域名，不指向生产。

在一次性stage恢复副本演练custom dump恢复、最新无正文撤销/送达收据重放、权限重授及`PostgresRepository(initialize=False)`只读核验和离线PG断言，不启动恢复副本Web；证明已撤销来源不复活、sent/uncertain不自动重发、原始正文哈希/有效变更可核对。若还需启动Web，重新满足空队列、无凭据、出站阻断与本节授权边界；不能把带恢复队列的Web称为“只读启动”。不能只列出备份文件而不验证可恢复性。

### S7 模型验收与stage签收（另行授权，时间不计入零模型步骤）

真实模型质量、k3/k3-256k等价及E1有效基线目前没有新证据，均保持待验证。用户对本次stage部署的授权不允许自动发探针；须先审核守卫入口，再由用户在主线明确开始限定场景、模型、实际POST上限和时间窗，主线串行/受控执行。计入同一80次窗口，额度/风控错误即停，不用其他模型/Key绕过；没有开始指令就继续其他零模型项目，不挂定时器。

签收分别列出零模型验证、真实模型验证、回滚演练三组结果；缺项不得写stage_accepted=true或live_provider_smoke_passed=true。`deploy_core.evidence()`及incremental_acceptance要求当前SHA/包哈希匹配，并可能依赖服务器保护目录中的冻结验收器与多份证据。盘点时确认这些文件及固定哈希；历史发布的布尔JSON或旧SHA实测不能直接作为B1验收，不为放行改工具/跳门。

## 4. 生产切换步骤（单独授权后执行）

前置：大脑审核B1 stage报告；全部必要门通过；用户批准精确SHA/配置/数据库/维护窗口、备份与回填范围、恢复正常业务模型调用及需要的渠道/定时服务。仅“同意stage”或“只读盘点”不含这些权限。没有批准时生产保持原状。

| 步骤 | 动作与继续条件 | 估计 |
| --- | --- | --- |
| P0 窗口前准备 | 固定同一个已验收包、双环境/素材哈希、受保护env顺序、原版本与兼容schema7恢复候选；检查磁盘/备份容量。所有生产准备写操作也须授权 | 20–40分钟，尽量窗外 |
| P1 关闭全部写入口 | 生产维护页/反代门、Web/飞书/报告/CLI逐一排空，核无运行/外部写者；保存原启停状态与精确任务ID，不停无关Hermes任务 | 5–15分钟 |
| P2 最终一致备份 | PG custom dump+最新撤销账本+sent/uncertain/绑定/配置/媒体清单，核SHA与可恢复性；首次Core再用SQLite backup API冻结旧源和Hermes状态，不能直接复制live WAL文件 | 10–30分钟 |
| P3 迁移与授权 | 同stage受审步骤仅将目标核为live，0005–0007/manifest→版本7、新表CRUD/账本只读、LangGraph权限。任何失败保留维护门 | 5–20分钟 |
| P4 回填与核账 | 同一owner dry-run→审核计数→apply→repeat；核原文/来源revision、撤销/助手去重、送达收据。首次Core先完整旧来源迁移再做P2回填 | 10–40分钟 |
| P5 切固定版本 | 经审阅的systemd WorkingDirectory/ExecStart/CHART_PYTHON/env均指向固定release，单Uvicorn worker/池4、仍v3、新端口默认off；维护门内只启动已授权入口 | 5–10分钟 |
| P6 门内验收与最终Go/No-Go | schema只读核验、health/state/history、固定牌、隐私/授权/计数、页面与旧版本读取。不得未经开始指令发模型探针或真实飞书测试消息 | 10–20分钟 |
| P7 恢复正常业务 | 用户批准后恢复原已核验的唯一渠道/报告writer，再开放Web；核服务和下一次正常日程，不因发布补发报告；记录开放时刻与回滚阈值 | 5–10分钟 |
| P8 观察 | 观察错误/延迟/队列/失鲜/重复投递/模型停止状态30–60分钟；只有计数、状态、哈希进入公开回执 | 30–60分钟，窗后 |

P5即使仍在维护门内，Web启动也可能恢复队列并发真实模型请求；只有具体恢复范围及相应模型执行权限已覆盖时才能启动。若只获准只读健康盘点、或模型恢复尚未批准，就先用repo只读核验并保持Web关闭，不能依赖nginx维护页阻止后台调用。

**现有部署工具的适用限制：** `freeze/install/publish`针对既有完整Core切换流程：freeze会改nginx、停旧任务、退役Hermes技能并重启服务；install会重跑旧来源导入；publish会开启真实飞书gateway与reports.timer。对于“已有Core PG的P1/P2增量升级”，不能盲目执行该三步当成升级快捷键。授权盘点后若需适配增量部署工具，先单独做可审查实现/替身与stage验证，再批准生产；本计划不伪造一个现有的`deploy --stage/--incremental`命令，也不扩大B1权限到未获准的技能或cron改动。

首次Core路径的具体`freeze/install/publish`参数参见`docs/CORE_V3_RELEASE.md`，必须保留其固定SHA、验收门、受信bindings、4个精确旧job ID和保护目录约束；生产有正常渠道投递的副作用，需明确列入授权。所有路径均不恢复旧Hermes解释循环或SQLite/JSON权威。

## 5. 回滚、止损与数据恢复

| 触发/状态 | 方法 | 完成标志与估计 |
| --- | --- | --- |
| 仅P1可选端口/模型配置异常，schema已7 | 恢复已备份的原受保护配置；撤去MODELS_CONFIG/MINGJING_MODEL_PORT=v2，继续使用**兼容schema7**的v3代码；模型身份按已批准配置核验 | 5–15分钟；health/API正常、固定操作ID重放不产生新业务请求。它不是P2数据库回滚 |
| 迁移事务未提交 | 保持停写，确认事务回滚、账本及schema仍与原代码匹配；恢复原兼容服务/配置前先核对状态 | 10–30分钟；不删迁移账本/手改历史SQL |
| 已提交schema7，应用失败 | 先恢复维护门、停全部writer并导出最新PG/撤销/收据；优先在schema7上切经过stage验证的兼容修复版本 | 止损目标5–10分钟；兼容版本恢复20–60分钟，取决于是否预备候选 |
| 需恢复PG备份 | 只向明确授权的恢复目标恢复已校验custom dump；全部入口仍关闭；先重放**最新**撤销/塔罗墓碑和sent/uncertain收据，再核恢复点后的其他有效写入、绑定、权限、schema与配套代码，复验后才开门 | 30–120分钟起，随库/媒体规模增加；没有演练数据不能承诺RTO |
| 无最新可靠备份、无法重放撤销/对账或缺兼容版本 | 保持维护，不开旧代码碰新库、不复活旧解释器、不清空库。记录缺口，申请具体恢复/修复方案 | 恢复时间未知，不以“服务能启动”宣布回滚成功 |

0005–0007没有受支持的向下迁移；schema7直接切回只认识schema4的旧包会拒绝启动。若确需旧schema备份+旧代码成对恢复，必须另做stage演练并处理恢复点后合法新增数据及最新版撤销/收据；当前`restore-withdrawals`也有live目标与版本校验，不能假定它能跨schema自动完成降级。默认采用维护保护和schema7向前修复，**不承诺一键无损降库**。

回滚触发包括：跨owner/撤销泄露、原文/revision异常变化、重复抽牌/发送、权限放大、迁移/回填不可解释差异、health或关键API持续失败、模型风控/额度停止。先停写/停投递保存证据，再排查；不通过重建request_id/business ID、重置预算或强制重发修复状态。

RPO目标为不丢已确认有效写入、不复活已撤销正文。计划停写后应立即形成最新一致备份；恢复较旧备份时若缺后续有效变更/WAL，RPO无法保证，必须明确报告并由用户批准恢复方案，不能把“备份在”当作零丢失证明。媒体/附件/配置与数据库恢复点也须一致。

## 6. 预计耗时与排期

以下以已存在PG15、依赖可安装、数据量中小且盘点无异常为前提；没有测过服务器吞吐，估计置信度低。stage记录dump/restore、索引和全量回填耗时后，以实测×1.5加30分钟恢复缓冲重估生产窗口。

| 范围 | 预计主动操作时间 | 额外等待/停机 |
| --- | --- | --- |
| 只读访问盘点与范围确认 | 20–40分钟 | 等用户提供访问方式/批准，不给固定日期 |
| Stage零模型准备、迁移、回填、功能与恢复演练 | 2–4小时 | 大库、补依赖、权限/旧脏数据可延长到半天；全程不影响生产 |
| 获准模型/等价性验收 | 30–90分钟起 | 逐批开始、20分钟批间隔/80次窗口/额度停止另计；未授权时不排自动任务 |
| 已有Core PG的生产增量 | 90–180分钟维护窗口 | 覆盖分步50–145分钟及约30分钟恢复缓冲；包/环境准备尽量窗外，窗后观察30–60分钟 |
| 首次从旧Hermes迁Core | 2–4小时维护窗口起 | 绑定、旧源规模、4个任务和隐私对账可能要求重新排期 |
| 失败止损 / 备份恢复 | 止损5–10分钟；恢复30–120分钟起 | 缺可靠备份、合法增量或跨schema降级时不承诺恢复时间 |

避开既有Asia/Shanghai 06:45准备/07:00晨报及其他实际报告窗口，具体窗口由用户确认；不为了B1修改报告日程。夜间可以在获准范围做非模型操作，但本计划本身不授权夜间stage/生产操作。

## 7. 交付与执行前Go/No-Go

每个环境分别记录：服务器身份摘要、固定SHA/tree/包哈希、数据库身份与迁移校验和、角色权限、备份/恢复演练哈希与耗时、回填dry/apply/repeat计数、原文与撤销/投递核对、零模型测试/DOM、真实模型另行报告、配置版本、服务WorkingDirectory、放行人/时间与回滚负责人。包含真实历史的样例、快照和凭据仅留服务器保护目录；仓库回执只放安全摘要。

任何必要门未完成即No-Go：容量整改/预算未通过、数据/权限异常、备份未验证、该批实际要求的验收/守卫缺证、维护/渠道恢复未授权、增量入口路径仍未验证。B1保留实际k3，P1b后新模型等价性单列；不因缺新模型实测而伪造B1零模型结果，也不发未经开始的请求。本轮只完成A，不填写“stage通过”或“生产上线”。

## 8. 用户需要提供的信息与逐次授权清单

| 类别 | 需要提供/确认 | 边界 |
| --- | --- | --- |
| 服务器访问 | stage/生产是否同机，主机标识/IP或域名、SSH端口、登录用户名、跳板机/VPN、已有SSH agent或受保护私钥文件路径、主机指纹核验方式、故障联系途径 | 只提供非密钥说明；私钥、口令、API Key由用户在本机/服务器受保护渠道配置，不贴聊天/文档 |
| 权限 | 只读盘点账号；执行时Linux root/sudo可用范围；PG管理员建库/建角色权限、独立migration/runtime角色；nginx/systemd和备份目录可操作范围 | 运行角色不授DDL；不因需要部署就索取或打印所有环境变量 |
| 目标配置 | 实际stage/live库和端口、schema、owner列表/时区、发布与媒体路径、服务/反代路径、原有效模型非密钥配置、受保护env文件位置/加载顺序、磁盘/备份保留策略 | 本机值不当作服务器值；不复制生产配置到测试环境 |
| 数据副本 | 是否允许在服务器保护目录创建生产PG/旧源一致备份，以及将哪一份复制到隔离stage；脱敏/访问人员/保留期限；回填指定owner范围 | “可连接stage”不等于“可复制生产私有数据”；批准前只用合成数据 |
| 授权A：只读盘点 | 明确允许访问哪台主机、读取哪些非密钥配置/服务/schema/计数 | 不建库、不备份、不修改、不启动服务、不发模型或消息 |
| 授权B：stage部署与演练 | 精确SHA、stage库/合成验收库、新角色/端口/目录/服务、备份→迁移→回填apply→恢复演练的允许范围 | 与生产分开；默认模型与渠道零外发，不允许自动执行生产 |
| 授权C：真实模型开始 | 用户在线，在主线明确开始具体stage模型/等价性批次及场景、≤10/批、实际POST上限、共享守卫/账本与时间窗 | 独立于B；E1/E2另需各自明确批次开始，夜间零模型 |
| 授权D：生产维护与切换 | 大脑stage验收后，批准精确SHA/配置、维护时段、live备份/0005–0007/回填owner、服务/反代/CLI操作、正常模型/渠道/定时任务恢复及应急止损范围 | 旧Hermes完整切换副作用逐项列出；不发额外飞书测试消息、不自动补报 |
| 授权E：数据恢复（需要时） | 明确恢复的库/备份哈希、配套代码、最新撤销/收据和有效增量重放、可接受RPO及最终开门人 | D可预先包含维护止损，破坏性恢复/旧库替换须明确批准具体目标，不能默许 |

本轮无需用户现在交付密钥或决定上线时间；信息和授权未齐时继续P3及其他本地工作，B1保持计划状态。执行前根据实际盘点把上述待确认项写成具体操作单，再申请对应一次授权。

## 9. 依据与本轮核验

依据为候选提交中的AGENTS.md、README.md、docs/CLOUD_DEVELOPMENT.md、docs/CORE_V3_RELEASE.md、P1_B1_stage_plan.md、P2_stage_plan.md、P2提示词，以及repositories/postgres.py/foundation.py/permissions.py、0005–0007、tools/backfill_v4.py、memory/backfill.py、adapters/web.py、tools/deploy_core.py、tools/verify_core_stage.py。现有旧计划中开放平台切换/自动续跑等内容被本文件第1节的最新用户决定覆盖；不改写旧历史证据。

初版仅本机准备；2026-10-18授权A后已完成只读盘点，详见B1_operation_sheet.md及evidence/B1安全JSON。其余部署/迁移/回填/备份/服务命令均未执行，模型和飞书请求0。未来B执行结果另写B1_stage_receipt.md，不能把本计划或A操作单改名冒充stage验收。
