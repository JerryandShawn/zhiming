# B1：观察并明确两处 schema 有效 USAGE 门

本 ExecPlan 遵循 `.agent/PLANS.md`，北京时间记录。工作树 `C:/Users/Administrator/Documents/Codex/zhiming-v4`，root拥有提交和发布；本任务先只新增计划与真实PG反例，已冻结ACL文件待root提交后再按获准方案修改。

## Purpose / Big Picture

运行writer必须能实际使用mingjing_core及public schema，单有表CRUD并不能代替有效schema访问权。先真实检查缺USAGE时现两门是误报安全还是已因SQL名称解析失败关闭，再决定最小显式拒绝门；不能把错误类型变化包装成修复误放行。正式权限不自动变更，receipt字段及五个探针数不改。

## Progress

- [x] (2026-10-21 09:51 +08:00) root授权ACL冻结后独立USAGE片，保留10:00第四测试位；10:12若仍在途报实际状态，不扩组。
- [x] (2026-10-21 09:51 +08:00) 设计两schema×直接writer/PUBLIC唯一有效来源四种真实绑定，撤权后须实际has_schema_privilege=false；记录旧结果而不预判误放行。
- [x] (2026-10-21 09:52 +08:00) 四种真实绑定实测39.46秒；两门全部为sql_insufficient_privilege，已经失败关闭，无误报true。4 failed仅来自新增诊断期望稳定False/固定业务码，不能称安全误放行红；已报root，生产文件无新改动。
- [x] (2026-10-21 09:54 +08:00) root释放并批准明确分类后，两门新增单独只读USAGE前置检查；缺失时native返回False，B3固定WRITER_OWNERSHIP_OR_DDL。10 passed+4 subtests/39.71秒（4真实PG+原port5+新stub1），0失败/错误/跳过/警告；没有重复ACL/PG11。
- [x] (2026-10-21 09:54 +08:00) 原5个测试函数AST与HEAD逐项完全相同，假连接仅加SELECT响应和正常默认；Ruff/format/尺寸/diff通过。原5probe及receipt ABI不变。
- [ ] 六件冻结交root统一提交/推送；不自行git add/commit/push。10:00测试位已释放。
- [ ] Linux/服务器正式权限验证仍未执行，不能解除No-Go。

## Surprises & Discoveries

ACL两门没有独立USAGE检查，但text关系名称解析可能先拒绝缺schema权限，因此静态漏检查不等于真实误放行。必须把有效USAGE确实撤成false后观察两门；基线若writer有直接授权，单撤PUBLIC不构成反例。

真实四例确认后者：有效USAGE实际为false时，两门均因关系名称查权抛InsufficientPrivilege，已失败关闭。不存在本轮观察到的安全放行漏洞。是否加明确False/固定错误码属于错误分类与诊断完善；现4个失败断言是新期望而非旧行为回归，不能用修改叙述冒称修了权限放行。

明确分类后四例观察为native False/B3固定拒绝，恢复唯一有效USAGE来源后重新通过且B3五probe仍为5。检查提前于任何table privilege查询，新stub显式保护这一次序；USAGE检查正常通过后仍走原ACL/TEMP/ownership/账本与CRUD流程，不代替它们。JUnit tests=14包含4子断言，pytest主计数为10。

## Decision Log

2026-10-21 09:51 +08:00 / root、Codex：当前先保持ACL五件冻结，USAGE四例独立不混28/4指标；用明确状态记录旧查询结果。若生产需要单独USAGE查询来稳定拒绝码，先报旧PG port假连接新增响应方案，保留原五项行为断言；不改consumer ABI或把实际DML成功写成手填true。

2026-10-21 09:52 +08:00 / Codex：已向root报告真实结果和最小显式分类方案：两门查询关系名前单独核两个schema USAGE；native返回False，B3用已有固定拒绝码。旧假连接只能新增该SELECT的正常授权响应，五项原断言全留；在root确认前不改旧fixture或生产代码，也不把本轮称安全漏洞。

2026-10-21 09:53 +08:00 / root：批准明确分类独立片。原五个PG port用例的函数体与断言完整保留，只给FakeConnection新增正常schema_usage响应、Factory默认true，并另增false时不进入table privilege查询的新用例。两门单独只读SELECT在任何表名查权前拒绝缺USAGE；原本已SQL失败关闭的历史必须保留，不能称修复误放行。只跑新4真实PG与旧port/新stub，不重复ACL或PG11。

2026-10-21 09:54 +08:00 / Codex：完成10主用例/4子断言窄验后立即释放测试位，不启动更多目标或全库，root可在10:00分配四条宽链。原4诊断与明确分类结果独立保留，不累计为14个主用例；固定b9/正式门、五probe和ABI不改。

## Context and Orientation / Plan of Work

复用 `PostgresPort._runtime_safe`、B3 `writer_permissions`、真实 `proof_db` 与准备/恢复生成器。每个反例在自己的随机恢复库先执行固定b9完整schema4备份恢复/迁7/重放/安全基线，再使对应schema仅一种来源有效：direct路径保writer USAGE并撤PUBLIC，PUBLIC路径保PUBLIC USAGE并撤writer直接权。只有有效USAGE=true后才撤该唯一来源，必须实查false；随后调用两真实门并安全记录拒绝类别。finally恢复本例受控来源并核基线。

生产检查可改变拒绝行为，但没有授权自行修改正式ACL。两门的严格权限/ACL/TEMP/ownership/账本检查均不能回退。目标是明确、可诊断的拒绝，而非给原本SQL拒绝的情况添加虚假的误放行历史。

## Concrete Steps / Validation and Acceptance

在清除模型/渠道与隐式PG环境、关闭追踪的锁定Core Python下，显式传入本机受审PG15工具/管理DSN/固定b9候选：

    python -m pytest tests/v4/release/test_b1_incremental_runtime_usage_pg.py -q

07 R02/F01权限和安全停写不变量不变。团队≤4进程，本任务只1窄进程，10:00三条宽链保留第4位；不扩为全库。模型/飞书/服务器均0。

## Idempotence and Recovery / Interfaces and Dependencies

无新依赖、迁移、外部访问或正式授权。测试仅更改本例新随机库中的writer/PUBLIC schema ACL，恢复本例有效来源后由既有夹具清理精确数据库/角色。正式失败保持现状停审，无自动REVOKE/GRANT。既有5探针和receipt ABI不变。

## Artifacts and Notes

私有 `private/b1-restore-proof-20261021/runtime-usage-*.xml`，公开 `docs/v4/evidence/B1/2026-10-21-runtime-usage.md`。原时区元数据保留，不打印DSN、正文或凭据。

## Outcomes & Retrospective

已完成四例真实诊断与获批明确分类：旧两门均SQL失败关闭，无误放行；新门在表名查权前明确返回False/固定码。4真实PG、5原port和1新stub共10主用例/4子断言通过，原五个测试函数AST完全相同，原5probe/ABI保留，正式ACL没有自动修复。六件冻结交root统一提交；无在途测试，10:00位已释放。Linux/正式五门仍No-Go，模型/飞书/服务器0；不能把此片称安全漏洞修复或正式权限放行。

## 修订记录

- 2026-10-21 09:51 +08:00 创建；按root授权先判有效USAGE与真实旧拒绝类别，区分权限误放行和固定错误门，保护冻结ACL片与10:00测试槽。
- 2026-10-21 09:52 +08:00 记录四例真实诊断均SQL失败关闭及39.46秒结果；报告稳定错误分类的最小方案，未改生产或旧假连接，未把新期望失败冒称安全漏洞。
- 2026-10-21 09:54 +08:00 按root批准完成单独USAGE只读门和最小假连接响应，10主用例/4子断言通过，五旧函数AST不变；记录分类性质、原始证据和六件冻结，释放10点测试位。
