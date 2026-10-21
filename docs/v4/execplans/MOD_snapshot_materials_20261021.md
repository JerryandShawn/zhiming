# MOD：补全完整回归的显式输入快照

## Purpose / Context

回归快照用于发现测试运行中输入变化，不是授权或质量证明。09:45历史报告明确列举511源/测试/样例；
检查新增晨报测试时发现冻结矩阵在docs中，原快照规则不会自动登记它。P2只读日历表及部分既有合成fixture也应显式登记。
只改本轮新runner，不改原报告、基底文件、P2数据或冻结盲集；不遍历全部JSON或private。

## Progress

- [x] (2026-10-21 10:11 +08:00) 阅读runner、SSE/晨报新测试的数据读取点及P2默认日历路径；确认8个合成fixture和Schema路径。
- [x] 固定名单补8合成fixture、SSE Schema与晨报冻结矩阵，共10已知输入；P2日历只读目录集合保留动态新增检测。
- [x] 4项快照边界通过；追加2项子进程环境隔离测试，mod_week原21+新6=27通过0.18秒，7代码文件前后相同。
- [ ] 下一45–59分全量使用新快照，旧511报告保持原范围，不倒填为更强证据。

## Surprises & Discoveries

旧511证明只约束实际列举文件，不能称覆盖其外所有动态输入；基底未改与依赖锁仍是独立证据。
P2默认config/holidays当前没有可枚举JSON，但今后新增表应进入路径集合，才能识别运行中新增或删除。
新增晨报冻结矩阵为公开合成metadata，不是B集或私有75条材料。

## Decision Log

2026-10-21 10:21 +08:00：补齐12类provider key子环境剥离及两追踪开关false；仅用合成token测试，父环境不变，不打印凭据。
先25通过报告原样保留，新增环境隔离后另报27通过，不回写旧测量。
显式列举timeparse/memory2/streaming/scheduling/briefing的已读fixture与SSE Schema，不自动遍历未知数据。
P2只读已约定config/holidays/*.json；不改表、不做日历计算副本、不打印内容。
测试用临时合成仓库及替身Git列表验证快照，不创建服务、调用模型或触碰实际B/private材料。

## Validation / Recovery

新增唯一tests/v4/mod_week/test_snapshot_materials_root_mod.py。运行前后不得改业务源；仅工具目标不受全量时段限制。
文件内容改变必须改变hash；新增日历表必须新增快照键；盲B与私有材料的read_bytes设置硬拒绝，测试仍能完成。
运行环境清provider keys、关trace、时区不取本机。所有报告用+08:00及UTF-8 LF，旧报告不覆盖。

## Outcomes & Retrospective

已实现并定向27通过，Ruff/format及两变更文件AST≤400/60通过。source前后相同、公开JSON为LF。
此增强不会使旧报告追溯获得新材料身份，也不能证明依赖包或外部运行状态。

## 修订记录

- 2026-10-21 10:11 +08:00 创建：在新增JSON读取点出现时补快照范围，避免零漂移证明超过实际分母。

- 2026-10-21 10:21 +08:00 更新10显式材料、6新边界/27工具测试、子环境隔离及历史范围限制。
