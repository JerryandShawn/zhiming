# P3：先关闭新服务准入，再采用同一维护标记完成 M1

本计划遵循 `.agent/PLANS.md`，时间均为北京时间。只在本机合成 PG15 中开发验证，不访问服务器或发送模型/渠道请求，不改变发布授权。

## Purpose / Big Picture

服务入口已经能持有同一数据库的文件/PG共享锁直到整个进程退出，但现 M1 必须先取得排他锁才能写维护标记，因此不能先阻新启动再排空旧服务。本片接通这两步：显式关闭新准入，旧服务可自然退出；之后显式采用原标记进行一次严格 M1 采集。默认不连接、不启动、不写文件，不能自动停止服务、等待重试、清除标记或恢复失败备份。

## Context and Orientation

工作树 `C:/Users/Administrator/Documents/Codex/zhiming-v4-release-prep`，从已推 `ac712c0` 建 `v4/p3-wire-admission-20261024`。复用 `tools/first_release_incremental.py::BackupInputs/connections/execute/main`、`first_release_incremental_pg.py::admin_identity/identity/backup/capture/write_private`、`first_release_writer_fence.py::file_lock/pg_lock` 及 `first_release_service.py` 已验启动协议。M1 的源严格是 `fr_upgrade_<operation>`、原 prefix4/7 和精确 SID/OID/角色，不开放源0008或正式库。源 marker 既有格式只有 operation_id 和 database_oid 两字段；`first_release_incremental_guard.py::maintenance_material` 同时核 marker 与 backup-started，必须继续兼容。

现 M1 先文件 EX、后 PG EX，再拒绝任何既有 marker，最后创建它。新服务则在双 SH 内检查 marker，不允许任意模块或多 worker。共享锁让已在途服务共存，排他锁才能排除它们。关闭准入不等于排空，更不能替代所有旧 unit、外部 CLI、Linux 和投递对账门。

## Progress

- [x] (2026-10-24 11:26 +08:00) 根与独立代理核实际断点，确定两阶段显式协议和原格式兼容边界。
- [x] (2026-10-24 11:34 +08:00) 实现关闭准入与 M1 显式采用，原默认及拒重入保持；源码、调用方与新测试均经根和独立代理完整审阅。
- [x] (2026-10-24 11:34 +08:00) 唯一首链3新+1受影响旧prefix4共4/4通过，96.53秒；根独立核metadata/XML/log。
- [x] (2026-10-24 11:37 +08:00) 两份操作单补完整本机两阶段命令、10控重审与停止规则；日报记录结果和独立CI修片。测试后提交推送按实际Git记录核，正式No-Go不变。

## Surprises & Discoveries

仅新增 marker 写入命令会让旧 M1 必然报 INCREMENTAL_MAINTENANCE_ALREADY_PRESENT，不能交付成已接通。必须同时增加精确 opt-in 采用分支，且保持失败产物拒绝重入。另一路评测分钟级绝对期限与五小时额度等待存在真实限制；本片不调整 deadline，不借冻结业务钟放行过期运行。

## Decision Log

选关闭准入→自然排空→单次 M1，而不先泛化正式 restore。原因是它直接接通上一片实际服务栅栏，仍可用同一现有合成源和严格备份验证；正式库/中央账本/授权契约保持关闭。新增辅助实现必须加入 M1 控制 hash 集，原九项扩展为十项须重新审核，不补写旧 pin 或让旧 pin 自动升级。决定人/时间：主线，2026-10-24 11:26 +08:00；不改变产品行为或既有预算。

## Plan of Work

新 `tools/first_release_admission.py` 只处理关闭准入和 marker 的严格身份/稳定性；按既有 M1 admin/owner/writer 实际身份核验，在 existing-only 文件 SH 与 owner PG SH 内 O_EXCL/fsync 写原格式 marker，前后核普通文件/路径及 inode、尺寸、时间、hash。关闭阶段不能调用精确 sessions=0 或 busy=0 门，因为旧 writer 正在运行；只写 marker，不做业务 SQL、授权或迁移。已有 marker 一律拒，失败保留现场，回执只表示 admission_closed=true，所有 drain/global/publication 位保持 false。

M1 增 `--close-admission-local` 和 `--backup-local --use-admission`，close 与 backup 互斥，use-admission 必须显式 backup。旧 `--backup-local` 继续拒既有 marker。采用分支只接受原两字段类型/值及同 operation/DBOID 的普通 marker，进 EX 前记录稳定身份，双 EX 内、实际严格检查后再核，采集后再核，不覆盖 marker。backup-started/dump/ledger/receipt 任一存在仍拒。全部原实际 PG 身份、精确会话集、busy、源码/迁移/owner/profile、同快照 dump/export、前后全态、错误优先级和输出保留门不放宽。

## Concrete Steps

先完成源码与新测试静态审阅，再由根授一个测试名额使用已有安全 runner 明确运行新节点。源样本来自既有真实 prefix7 夹具，实际受限 writer 的最小 DML 只限新测试库；正常新旧服务用真实子进程/锁/MemoryService，模型与外部传输禁止。

## Validation and Acceptance

相邻场景是 `docs/v4/07_评测场景集.md` 的 R 类恢复、Q 类发送边界，本片不改变评分标准或重复整套脚本。三个必要行为：旧服务持 SH 且原生提交时可关闭准入，新服务零业务拒；旧服务自然退出后唯一 M1 捕获真实 dump/export 并与原 guard marker 材料兼容。默认零 IO、错误实际身份、异 operation/坏 marker、缺 use-admission 和标记漂移均拒且原业务保持。M1 在已写 backup-started 后出现受控实际故障，marker/产物保留、新服务继续拒，后续调用不能自动重入或清理。不得 mock PG、锁或 os._exit，也不能把源 writer 只作假返回。

## Idempotence and Recovery

关闭准入重复调用拒绝既有 marker；采用只消费尚无备份产物的当前同操作 marker，不能把失败 M1 变成可重入。任何不确定写入保持维护标记，交审核；没有自动删 marker、产物、旧库或 role 的路径。测试 teardown 仅清理自己创建的唯一库/角色/子进程。

## Artifacts and Notes

唯一原件在本树 `private/safe-narrow-6ae10cc7e04d4f5db2fc9fed0093beb0/`，只有该目录的 metadata.json、pytest.xml、pytest.log 为本片依据。实际开始/结束为2026-10-24 11:31:24.875687–11:33:02.287750 +08:00；JUnit96.516秒，pytest96.53秒，4 passed/0 failures/0 errors/0 skipped，无警告。3个新节点和唯一受影响的原prefix4成功节点同次运行，没有重复整个4/7矩阵、宽回归或稳定性轮。模型/外发/服务器调用0，runner清凭据/关追踪/TZ Tokyo；断言不依赖本机时区。

实际源业务archive由夹具在当时HEAD ac712c0生成，控制程序是本片未提交时的精确10控hash，不能把后续提交SHA称为已经冻结验收的应用候选。新源prefix7的writer由测试准备阶段仅在该新库给现grant_runtime_tables最小DML，记录test_only_writer_runtime_grant=True且0008不存在；SID EXECUTE原有，未新增SID授权。真实原生主/后台两条原话提交后关闭新准入成功，旧进程仍活，新的服务0业务拒；旧自然退出后M1实际生成同快照dump和原生旁账，marker字节及原guard三个材料兼容、前后源全态不变。错误实际OID、缺采用、异operation/坏JSON和真实mtime漂移在正确门拒。

故障节点只给原dump传不存在的snapshotID，仍实际运行原PG15 pg_dump，记录真实一次非零返回；backup-started/ledger/实际dump和marker保留，无receipt，新服务拒，重入为EXISTING_OUTPUT_REJECTED且全部既有材料保持。没有mock PG、锁、业务返回或os._exit，也没有自动补偿。四文件Ruff E/F/I/B/UP/SIM、120列format、AST/尺寸及diff通过：new helper115行/new test270行，旧M1365行/旧pg460行（原已超400，最小接缝改、低于600），最长函数57行。上一服务片3/3独立，不与这里相加。

## Interfaces and Dependencies

不新增 proof/pin 格式、数据库表或依赖。新 helper 加入既有 CONTROL_NAMES，并保显式审核和 hash 全闭包；其他独立 Forward/replay 控制 pin 不能自动改写。只修改原 M1 两文件的必要接口和采用接缝，不改服务入口、原 guard/Forward、业务记忆、暂停树或真实 unit。

## Outcomes & Retrospective

本机“关闭新准入→旧服务自然退出→显式采用原marker完成M1”已真实接通，首次4/4；旧默认捕获也保持兼容。四个目标直接调用execute API并运行真实服务子进程，main参数分支经静态审阅，未另作CLI新进程整链。正式global/publication等位始终false，控制器不停止真实unit、不清标记或自动重入。Linux、全入口纳管、外部投递排空、源0008、正式恢复/切换及用户新授权均未解除，不能据组件链将五个发布门放行。

## 修订记录

- 2026-10-24 11:26 +08:00：记录两阶段真实接线、M1严格显式采用及失败保留边界，先写计划再实施。
- 2026-10-24 11:34 +08:00：根核唯一4/4原件、实际故障与权限前提，保正式关闭和新候选未冻结边界。
- 2026-10-24 11:37 +08:00：完成两份操作单和日报收尾；M1两阶段本片证据与PR18修片及新CI分别登记，不混合验收。
