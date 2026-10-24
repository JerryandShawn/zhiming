# P3：让统一服务入口持有数据库写栅栏直到进程退出

本 ExecPlan 是活文档，遵循 `.agent/PLANS.md`。全部时间为北京时间，实际模型、服务器和消息请求保持零；此工作不是部署授权。

## Purpose / Big Picture

网页、飞书接收、报告和 Hermes 当前直接启动 Core，各自还可能有后台线程和投递过程。只锁一次仓库事务不能证明维护时已停写。本片增加固定的同进程入口，在调用原生入口之前取得文件及 PostgreSQL 共享锁，并把锁保留到操作系统结束整个进程。默认只校验配置，不导入业务、连接 PG 或启动服务；显式运行才进入。未更换的旧 unit、其他 CLI、Linux 运行时及正式配置继续阻塞全局停写门。

## Context and Orientation

工作树是 `C:/Users/Administrator/Documents/Codex/zhiming-v4-release-prep`，本片从 `447aa17` 创建 `v4/p3-wire-service-fence-20261024`。复用 `tools/first_release_writer_fence.py::file_lock/pg_lock` 的真实跨进程共享/排他锁，以及 `tools/first_release_incremental.py::BackupInputs.fence_path/fence_key/maintenance` 的既有协议：路径是同一 workspace 的 `private/first-release-writers/<system_identifier>-<database_oid>.lock`，PG key 是 `first-release-writer:<system_identifier>:<database_oid>`。原 M1/Forward 已按这两个身份固定命名，不是按操作编号命名；旧控制程序及其 hash 契约不改。

固定业务入口分别是 uvicorn `main:app`（单 worker、无 reload）、`mingjing_core.adapters.feishu_gateway.main`、`mingjing_core.adapters.core_report_worker.main(argv)` 与候选内 `hermes/core_consultation.py::main(argv)`。原 Hermes 的 stdout 是业务结果，包装器不得追加成功 JSON。身份仅通过实际 `ZHIMING_DATABASE_URL` 的受限 writer 连接核对，不加载管理员/owner DSN，不自动建角色、授权或开中央账户。

共享锁让同时运行的服务彼此共存，维护控制器必须取得两个排他锁。维护标记阻止新服务启动；它不自动停止已经运行的进程。`pg_control_system()` 若无 EXECUTE，入口必须拒绝，部署前的精确授权另行审查，不能自动扩大到 pg_monitor。

## Progress

- [x] (2026-10-24 11:07 +08:00) 核对实际固定入口、原双栅栏及 M1 命名，选择同进程、持锁内真实退出方案。
- [x] (2026-10-24 11:16 +08:00) 增加独立 launcher 和受限 writer 绑定 helper；根与独立代理通读，四个新 Python 文件的 120 列 Ruff/格式通过，未改旧控制程序、业务/记忆服务或 unit。
- [x] (2026-10-24 11:18 +08:00) 独立审核后的唯一首链三个新节点全部通过，pytest 6.39 秒；根独立核 metadata、JUnit 和日志。
- [x] (2026-10-24 11:19 +08:00) 两份操作单补实际组件参数、同进程锁策略和剩余门，日报记录真实两小时进度。已具备测试后提交推送的完整可复核结果；提交/远端状态以实际 Git 记录为准。

## Surprises & Discoveries

Feishu 入口用 daemon 线程且原清理只等待五秒，函数返回不能当作进程停止。因此不能采用 `with guard: entry(); return`。Docker 只读缓存查询仅见 postgres:15 与现有矿工镜像，未见可确认的 Linux Python 3.11，未运行或拉取任何镜像；本片不能据 Windows 测试解除 Linux 门。

## Decision Log

选择在双锁作用域内部调用原生入口，完成其原有 finally 后刷新 stdout/stderr，并直接 `os._exit`，由内核在整个进程退出时释放文件锁和连接。异常也在持锁内固定非零退出，KeyboardInterrupt 为 130，整数 SystemExit 保留；输出刷新失败不先解锁。专用 PG 连接丢失时文件共享锁继续阻止同 workspace 维护入口。这个最小实现不采用跨进程 supervisor，避免父死子活；不接受任意模块、web 多 worker 或 reload。外部子进程 writer 仍未纳管，不能宣称整个系统停写。决定日期/作者：2026-10-24 11:07 +08:00，主线；不改变产品或原生业务意图。

## Plan of Work

增加 `tools/first_release_service.py`，必要时把明确边界的身份校验拆至一个小 helper。固定参数描述候选根、共享 workspace、实际系统标识、数据库及 writer 的名称/OID，DSN 只从环境读取。默认验证路径及配置形状，运行时实际核 PG15、地址/端口、数据库/OID、session/current role/OID、受限角色与非数据库 owner，再获取同一双锁、检查维护标记、调用固定原生入口。错误仅给固定无正文代码。独立新测试文件覆盖真实子进程退出，不在测试中替换 os._exit；外部模型/传输禁用，业务只用本机合成资料。

## Concrete Steps

在上述树静态检查新文件，再由根授权单个安全 runner 对显式新节点执行；主线测试进程不超过两个。只有原件 metadata、JUnit 和日志共同确认后才记录通过数。新参数调用形状将以实现为准写入两份首发操作单，绝不直接运行网页、飞书或真实 Hermes 问事。

## Validation and Acceptance

相邻验收背景是 `docs/v4/07_评测场景集.md` 的 R 类运行恢复、Q 类发送/额度边界；本片不改原场景 gold 或冒称完整脚本通过。独立实际 PG15 节点需观察：同一受限 writer 的原生业务真实提交、后台仍活期间两个 EX 都失败、进程退出后两锁都能取得；维护标记、任一锁占用及身份错误均不进入业务；业务异常和 PG 会话被终止时，文件锁仍保持直到进程真正退出，退出码与 stdout 契约不泄露正文。默认验证零 PG、零业务导入、零启动及零文件写。替身只用于固定 native 调用接缝和外部传输，不能替代 PG 或仓库写入。

## Idempotence and Recovery

launcher 不做迁移、授权、删除、回填或维护标记清除；重复运行仍先取双锁并检查标记。失败保持原标记和已提交业务，运行中的未提交事务由断连回滚，不能假称自动恢复业务。测试只创建及清理自己唯一的本机合成库/角色，不修改其他服务或权限。

## Artifacts and Notes

原始测试证据只登记本计划一个来源，不复制到多份日报。唯一目录为本工作树 `private/safe-narrow-c6661049e14b4b98a2d66640604b6b15/`，内有 `metadata.json`、`pytest.xml`、`pytest.log`。实际开始/结束为 2026-10-24 11:17:37.166670–11:17:44.475080 +08:00，JUnit 6.377 秒，pytest 6.39 秒，3 passed/0 failures/0 errors/0 skipped，无警告。安全 runner 使用 K3 venv、真实隔离 Windows PG15 和本次 prefix7 原生恢复至8；测试 TZ=Asia/Tokyo，时间/状态断言不依赖本机时区。模型/外发/服务器调用均0。

正常子进程实际由主线程及后台分别提交一条 MemoryService 原话，native 返回后真实 stdout.flush 同步点仍观察到非 daemon 后台存活，两个 EX 均失败，真实 os._exit(0) 后两锁可得。异常子进程只精确终止本库/本 writer/application_name 唯一 PG backend；PG EX 已可得时文件 EX 仍拒，native 返回后的窗口仍如此，再真实 os._exit(2)，固定错误码且无正文/DSN，已提交的两条原话保持。默认分支、维护标记、任一 EX 占用和实际错误 SID 都未进入业务，完整源状态/原文件和维护标记保持。SID 的 EXECUTE 原已具备，`sid_test_grant_added=False`，没有实际新增权限。

四文件的 Ruff E/F/I/B/UP/SIM、120列格式及语法/尺寸检查通过；launcher 138行、binding 163行，新测试273行、support170行，最长函数41行，旧文件源码没有改动。只跑这三个新目标，没有重复旧矩阵、全量回归或稳定性轮。PR18 在11:13最后一次只读核对仍处 v4 步骤，Core/前端通过、ModelPort尚待；未取到实际 checkout SHA 与最终结论，不能据此前 base 绿灯推进正式集成。

## Interfaces and Dependencies

不新增 JSON proof/pin 协议、数据库表、依赖锁或任意入口插件。复用 psycopg、uvicorn 与既有锁。中央额度的四项 MEMBER 配置由原业务原样继承，launcher 不读取为授权、复制、provision 或清除账本。所有 unit 与 Hermes 安装切换必须在未来同一候选、同一 workspace、精确 writer 配置和用户新授权下再审查。

## Outcomes & Retrospective

固定入口和身份绑定代码已完成静态审阅，唯一首链3/3通过。测试只替换固定 native 接缝和 stdout 的同步协调，真实原生 MemoryService 写入、PG、两个栅栏及 os._exit 不替换；默认分支的零业务导入证明限于当前测试进程的新导入尝试，不称干净新进程依赖证明。这也不是四个完整应用的联合运行或 fresh 不可变候选验证。正式全局停写、Linux 应用链、三 unit/Hermes 安装及发布门仍未解除，不能写首发候选就绪。硬退出防止进程未死先解锁，但可能中断尚未排空的任务或投递；是否已在远端发生的结果仍须原业务对账，不能宣称取消或自动重发安全。

## 修订记录

- 2026-10-24 11:07 +08:00：先登记原生固定入口和真实进程生命周期方案，保持原 M1/Forward 协议与正式 No-Go。
- 2026-10-24 11:16 +08:00：记录固定入口/身份实现和静态审阅、测试接缝及在途投递边界；实际 PG/子进程验证尚待执行。
- 2026-10-24 11:18 +08:00：根核首次3/3真实PG与子进程原件、记录无新增权限/零外发及未覆盖项，不放行正式门。
- 2026-10-24 11:19 +08:00：完成操作单与日报收尾，根重核四文件语法/尺寸、Ruff和差异；准备测试后的自身分支提交推送。
