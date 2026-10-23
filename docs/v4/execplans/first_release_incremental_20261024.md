# 核心首发：已有合成本机库停写备份入口

本活计划遵循`.agent/PLANS.md`与AGENTS。所有时间用北京时间；不访问服务器，不调用真实模型或外发，由主线审阅后提交并推送自己的分支。恢复effects与原恢复计划由另一代理维护，本片不改。

## Context and Orientation

已提交起点为144b81eeed3e792221393673bd611637fbaae01f，当前实际测试包选686213f（包含真实候选双重放基础、e8幂等及后续legacy擦除修复）；不是冻结发布包。本片复用`first_release_source.verify_source`核审核源码，复用受hash pin的`first_release_replay_worker.py`中纯stdlib导入来源及实际Python/活动依赖核验函数，实际旁账只调用候选`tools.deploy_core.export_withdrawals`。不构造旧B1输入，不借freeze/install/publish，不改变fr_restore creator硬门。

“合作性writer栅栏”指参与者写入前共同取得同一文件/PG共享锁并检查持久维护标记；本工具取得独占锁。现有应用未接此协议，因此本片不能证明全局停写或生产安全。源库严格为已存在的fr_upgrade_<operation>合成库，精确审核OID/角色/owner/连续prefix4或7，0008关系必须不存在。

## Purpose / Big Picture

新增显式本机停写备份命令，对已存在合成Core库生成真实custom dump、真实候选最新撤销/收据及不含正文的完整源状态摘要。默认只读文件校验，零PG连接、零子进程、零文件写。显式backup成功也只表示本机备份阶段完成；源库不迁移、不回填，恢复前原始内容对照、Linux、中央身份、正式发布继续关闭。

## Progress

- [x] (2026-10-24 02:00 +08:00) 实现显式backup-local与真实双栅栏、候选prefix4/7原生导出、实际PG15 dump、完整状态不变及失败保留。
- [x] (2026-10-24 02:00 +08:00) 首链8/8真实PG/实际程序/跨进程目标通过，96.61秒；清凭据关追踪，仅1测试进程，无失败、无补跑，已释放测试令牌。
- [x] (2026-10-24 02:02 +08:00) 根审新增1/1真实跨进程cooperative_writer目标通过，16.79秒：同child先实际写合成行，备份释放OS/PG锁后仍由持久marker阻止第二行；仅运行此目标，未重复8项。
- [ ] 后续在用户已授权的本机开发范围内另做新fr_restore目标源摘要对照、真实候选双重放门，再前向源库与回填；不属于本M1已验范围。

## Surprises & Discoveries

当前候选export_withdrawals所读owners/revocations/tarot_requests/mutation_requests/outbox及列均存在于prefix4。导出阶段只能先核连续历史后直接调用真实候选导出，不调用要求完整8的repo.verify_schema或initialize。恢复144回执还不是“备份时源库全状态==恢复后升级前原始状态”的证明，这一接缝后续由恢复owner实现，不能用任意JSON放行源库升级。

实际PG15验证：worker在只读RR事务内先IMPORT父snapshot，再查询PID握手，候选原生export内嵌同值SET RR/RO正常工作。测试在snapshot导出后由不合作连接写入新撤销并推进sequence：真实候选旁账与真实pg_dump均看不到新撤销；新快照检查实际看到源变化并拒绝完成，保留dump/旁账/维护标记。序列也独立检测，未假称受MVCC保护。

## Decision Log

主线裁定M1只证明阶段前/后精确无额外会话，不做脆弱OS/TCP PID追踪，不按application_name放行，也不声称dump期间全局排除连接。回执global_quiescence_verified=false、session_checks=before_after。父owner只读REPEATABLE READ事务导出snapshot并保持存活，实际pg_dump --snapshot和候选worker在业务读前IMPORT同一snapshot；阶段后另开新快照比较当前源数据，漂移则失败保留。sequence不受MVCC保护，单独前后核last_value/log_cnt/is_called；未来跨恢复对照只按last_value/is_called作语义比较，log_cnt原证据保留用于同库漂移，不能删除或伪造一致。

本片仅新增四个tool、一个PG测试与本计划。新输入绑定候选/manifest/三锁、程序与解释器、新worker及被复用控制worker真实hash、实际系统/数据库/角色OID及owner全集。文件/PG锁以实际库稳定身份绑定，固定先文件后PG；维护标记和部分输出在失败后保留，既有输出或已进入的operation不自动接管/重试。不会修改角色LOGIN/权限、杀会话或停服务。

公开成功回执仅为backup_captured。正常工具链实际连接为admin控制库只读身份盘点1、writer只读身份1、owner锁与snapshot1、候选只读worker1、pg_dump1，共5个；admin连接不读pg_authid，阶段结束即关闭，不作为额外源会话豁免。测试额外创建/恢复的观察库只证明导出行为，不自动放行源库升级。外部审核pin是可信输入前提，不认证审核者，也不证明wheel/.pth或Linux供应链。

根审授权测试文件445行的局部软目标例外（硬上限600、函数最长47行）：保持“同一真实child实际写入→真实backup→marker拒绝第二写”协议证明集中，不为这一个新增目标另造测试support。业务tool未改，原8项不重跑；新增目标必须单列证据，不称一次9/9。

## Plan of Work

first_release_incremental负责不可变输入与CLI；first_release_incremental_pg核实际PG身份、其他会话/active/lease、源完整表/sequence摘要并执行受pin pg_dump；first_release_writer_fence提供Windows LockFileEx/POSIX flock及PG锁的合作协议；first_release_incremental_worker以纯stdlib bootstrap加载已核控制基础，固定实际候选导入后只读导出。prefix4/7源数据只读，不新增迁移或依赖。

## Concrete Steps

在release-prep运行显式pin的first_release_incremental默认校验应无连接/进程/文件写；加--backup-local才取双栅栏并写该operation私有目录。PG与文件独占锁须真实跨进程互斥，不按application_name识别可信会话。只读worker在IMPORT SNAPSHOT后才握手回报实际PG PID，由controller精确允许；pg_dump没有可信backend握手，不假造关联，只在其前后核没有额外源会话。前后检查不是dump期间全局静默证明。

## Validation and Acceptance

沿用F01–F04、X03“不复活、不重发、owner隔离”约束：实际prefix4/7已有库生成可由PG15读取的custom dump和真实候选非空旁账，源全部字段/时间戳/sequence摘要不变。错误OID、活跃run/lease、其他会话、文件或PG锁冲突停止；不修改源行或修权限。默认与缺显式授权入口必须零副作用。首链≤8必要组；本机Windows结果不算Linux。

## Idempotence and Recovery

失败保留维护标记、已写输出和实际阶段，不删除、自动重试或清理。OS/PG锁随进程退出释放，不等于解除维护；参与协议的writer仍须检查标记。本片没有清除维护或恢复旧目标的命令，没有源库迁移/回退动作。

## Artifacts and Notes

唯一窄链在`C:/Users/Administrator/Documents/Codex/zhiming-v4-release-prep`运行：

    C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe C:/Users/Administrator/Documents/Codex/2026-10-17/v4-ai-claude-c-users-administrator-4/work/b1_readonly/run_narrow_safe.py C:/Users/Administrator/Documents/Codex/zhiming-v4-release-prep tests/v4/release/test_first_release_incremental_backup_pg.py

私有证据为`private/safe-narrow-8674777b249649a1a896d97a214faef8/metadata.json`（2026-10-24 01:58:48–02:00:26 +08:00），同目录pytest.log/XML；8 passed in 96.61s，模型/外发/服务器均0。两个prefix正例、默认零副作用与错OID、冒用pg_dump名称的额外会话、live lease、跨进程共享文件锁/PG锁、同快照与新鲜源漂移共8目标。Ruff E/F/I/B/UP/SIM及120列format通过，五个Python文件346/398/206/114/383行，最长函数57行；无全量或重复已通过目标。

根审补充安全目标单独证据为`private/safe-narrow-c177329d63294615be127f8e0d638c15/metadata.json`（2026-10-24 02:02:36–02:02:53 +08:00），1 passed in 16.79s。单一child先经真实cooperative_writer共享锁写入synthetic-writer-before并关闭会话；真实backup完成且释放文件/PG锁后，同child再经相同协议获得共享锁，因保留marker受控拒绝第二行。直接PG确认完整表/sequence状态不变、只存在首行且marker仍保留。此为8/8之外的1/1，不合并宣称一次9/9；测试文件现445行，已记录根审软目标例外。

## Interfaces and Dependencies

显式FIRST_INCREMENTAL_OWNER_DSN/WRITER_DSN只允许本机55480/55481和本次fr_upgrade库、精确角色；FIRST_INCREMENTAL_ADMIN_DSN限同一服务器的postgres/core_test_main控制库；所有PG隐式环境拒绝。子进程有限环境，密码只在内存，不进入argv/回执/日志；只调用已pin真实PG15 pg_dump与Python3.11 venv。源状态摘要不是原始恢复内容核验，backup_captured也不构成升级/恢复/native/Linux/供应链/发布授权。

## Outcomes & Retrospective

本机合成已有库M1备份入口已获8/8实际证据；只证明合作性栅栏、共用MVCC导出点和阶段前后状态检查。现应用未接栅栏，global_quiescence_verified=false；before_after不排除dump期间瞬时非合作连接。工具尚未实现“源备份完整摘要→新目标原始恢复对照→重放→升级源库”的放行链，source_restore_content_verified/source_upgraded=false；源prefix8/中央账本身份保全、正式恢复、Linux与发布均仍No-Go。测试自产审核pin不认证审核人或完整供应链。没有业务迁移、依赖、既有权限或原b9变更。

## 修订记录

- 2026-10-24 01:39 +08:00：创建独立增量M1计划，先于编码明确实际备份与合作性栅栏边界。
- 2026-10-24 02:00 +08:00：记录唯一真实8目标链全通过与snapshot/序列实证；保留全局停写、原始恢复绑定及正式发布关闭，冻结六路径待根审阅。
- 2026-10-24 02:02 +08:00：单独补根审要求的marker持续防实际写入1/1证明，不重跑旧8项；业务实现不变，再次冻结六路径。
