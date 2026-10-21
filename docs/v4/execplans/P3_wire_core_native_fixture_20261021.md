# P3 wire：修复固定B1候选的Native测试夹具范围

本ExecPlan遵循`.agent/PLANS.md`，北京时间2026-10-21 09:15创建。独立目录`C:/Users/Administrator/Documents/Codex/zhiming-v4-p3-wire-p1b`，基准5b691475c41791b4df2166db96dd3db54cc78d2b。只改已授权测试夹具及本任务文档；不修改main、B1发布包、产品迁移校验、迁移文件、前端、排盘、P4计划或评分。无服务器/模型/飞书动作。

## Purpose / Big Picture

Native离线测试用合成目录模拟固定b9发布包，验证发布控制顺序和拒绝非法输入；它没有访问真实服务器。P1b新增0008后，夹具错误地复制当前目录所有迁移，使“固定b9”的合成包混入0008。产品严格校验正确拒绝，因此三个原安全测试尚未进入各自要验证的行为。本片修正夹具，使其包含且只包含b9批准的0001–0007，并新增“即使重算合成manifest也不能把0008混进b9”的反例。原安全断言全部保留。

## Context and Orientation

复用`tests/test_core_incremental_native.py:156`的`NativeAdapterTests._release`、`tools/core_incremental_files.py:76`的`HostFiles.release`与`tools/core_incremental_contracts.py:MIGRATIONS`。后者固定七项已批准checksum，不得扩成当前分支所有迁移。`HostFiles.release`逐文件核manifest、拒额外文件，再核规范化迁移集合；`NativePort.source_checks/quiesce`在写维护门/停服务前调用它。`FakeCommands/FakeDatabase/fake_fence`明确替代主机命令、PG、锁；本测试不得冒充真实Linux或stage部署。

原10个测试保护：固定源码/额外文件拒绝、非授权主机前置拒绝、受注入端口的备份/摘要检查、Hermes manifest最后更新且stub/原始备份/环境顺序保留、未知skill与旧备份篡改拒绝、关停失败仍尝试全部writer、任意shell/SSH/Python命令拒绝、systemd dropin/子进程策略拒绝、旧writer fence篡改拒绝、旧wrapper模板兼容。所有产品门和原断言保持原样。

## Progress

- [x] (2026-10-21 09:15 +08:00) 完整读取终态日志、Native测试、HostFiles.release及NativePort调用链；固定0900快照Core581项/792.303秒，errors=3、exit1。
- [x] (2026-10-21 09:15 +08:00) 三个已知node最小复现3failed/0.91秒；全部PACKAGE_MIGRATIONS。静态核对当前1–7规范化hash全部匹配，唯一多出8。
- [x] (2026-10-21 09:15 +08:00) root授权只改夹具和独立计划/证据；不放宽产品或改原失败档案。
- [x] (2026-10-21 09:17 +08:00) 仅原fixture增加固定七项枚举、单文件唯一性解包与精确checksum；原文件400行、所有安全断言未改。root另授新测试文件承载两条反例。
- [x] (2026-10-21 09:17 +08:00) Native原10项+新2项通过，12passed/5subtests/1.97秒；Ruff/格式/400与60/diff绿，冻结4件给root；未重复581全量。

## Surprises & Discoveries

`_release`从当前`mingjing_core/repositories/migrations/*.sql`复制每个文件并用合成manifest记录其hash；P1b合法0008因此进入了只该有七项的B1合成包。实际1–7完全匹配批准checksum，故不是旧迁移被改、换行差异、数据库失败或产品闸门错误。原Core总回归的三个ERROR在pytest窄复现下显示为failed，属于unittest/pytest呈现差异，错误原因相同。

固定0900线的v4 2732pass/1strict-xfail/1warning、M8原46/47及扩13/13不能替代这次Core失败；本片不改这些历史结果，也不把旧581回签为绿。Native原文件396行，最小fixture改动后恰400行；新增64行测试模块用模块导入与组合复用，避免unittest discover把旧TestCase再次导入到模块级而重复执行10项。目标组实测为预期12项。

## Decision Log

2026-10-21 09:15 +08:00 / root：确认只修测试“固定b9”的输入构造；仅批准MIGRATIONS 1–7且精确checksum，不修改`HostFiles.release`、固定b9/manifest、迁移文件或评分。新的反例须重算合成manifest以证明迁移集合门独立生效；不能只依靠文件未登记而被另一层提前拒绝。

2026-10-21 09:15 +08:00 / Codex：夹具先选择批准版本，再断言批准键完整且checksum一致；缺文件/批准文件内容改变会明确失败，不静默过滤为成功。用真实HostFiles逻辑验证合成包，外部命令/网络/exec始终被测试阻断。本片无产品待决。

2026-10-21 09:17 +08:00 / root：授权独立`tests/test_core_incremental_native_fixture.py`承载两条新反例；原文件仅小改fixture与checksum，保持≤400行，不改产品或其它wire待归档文件。

## Plan of Work

在`_release`增加固定批准版本筛选及checksum断言。复制数据仍用现有`private_write`和合成manifest；忽略当前分支合法但不属于b9的0008。补正向夹具精确1–7/哈希检查，以及负向将0008加入合成包并同时登记新manifest/hash，产品仍必须以PACKAGE_MIGRATIONS拒绝；不更改任何既有安全断言。

## Validation and Acceptance

仅在独立wire目录、Core3.11解释器、TZ=Asia/Tokyo、关闭追踪/飞书且清凭据后运行目标Native组，至多一个pytest进程。本组是假主机/假PG控制流测试，真实PG只允许本机55480；不会读取服务器或产生模型请求。默认不重复581全量；root于下一10:00固定新源后另行做Core宽复验。

    python -m pytest tests/test_core_incremental_native.py tests/test_core_incremental_native_fixture.py -q --tb=short

验收观察为原三个node能够执行各自原断言、原10项安全行为保留；增加0008并重算manifest仍拒，不能只让正向夹具变绿。`docs/v4/07_评测场景集.md`的R02/F01等评分均未运行或修改，本片只恢复离线发布控制前提，不能声称模型/历史语义评测改善。

## Idempotence and Recovery

每个测试仅使用自己创建的TemporaryDirectory并由既有清理回收；没有数据库迁移、真实服务、发布或外部写操作。修复可用普通Git回退；测试失败保留原断言和失败证据，不自动改变产品MIGRATIONS。root统一提交/推送，PR保持草稿且不合并。

## Artifacts and Notes

原完整失败日志留在task的`private/regression-20261021-0900-wire-5b691475/core.log`与`core_metadata.json`，不可覆盖。新证据单独写`docs/v4/evidence/P3_wire/2026-10-21-core-native-fixture.md`；新窄组结果与旧581结果分开。其它未跟踪M8/P4文件不属于本片。

## Interfaces and Dependencies

没有公共API、数据库schema或依赖变化；只使用已有MIGRATIONS常量、hashlib和测试辅助。固定候选仍为b9a89b6f84f7bebb640de080548010859aae630c，P1b0008保留在开发树，绝不加入B1包。

## Outcomes & Retrospective

原因定位、夹具最小修复和窄验收完成。原文件只增hashlib/MIGRATIONS导入并改固定枚举、单个文件解包/精确checksum，全部原断言保留。两条新增测试用真实HostFiles逻辑证明正确七项可以验证，改已批准SQL且重算manifest仍拒，混入真实P1b0008且重算manifest也拒；均在任何主机命令/维护门前停止。Native原10项+新2项共12passed、5个原subtests通过、1.97秒，Ruff/格式/尺寸/diff绿。

历史固定0900 Core仍为581项、errors3、exit1；未重跑或改写。四文件冻结交root后，等待10:00固定新源的独立Core宽回归。没有生产/服务/模型/消息或真实PG行为被此组验证，亦未把新B1应用片带入wire。

## 修订记录

- 2026-10-21 09:15 +08:00 创建：固定原始三ERROR、实际复现、夹具唯一多出0008及不放宽产品门的实现与验收边界。
- 2026-10-21 09:17 +08:00 记录root追加新测试文件授权、原文件400行最小diff及12项/5subtests真实窄验收；旧581失败保持，冻结4件待统一发布。
