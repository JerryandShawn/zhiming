# MOD 晨报当前来源门禁独立阶段回执

- 分支 / 最后提交：归属v4/mod-organize；本子任务未操作Git，提交与PR状态由root回填。
- ExecPlan：[8项独立计划](../../execplans/MOD_briefing_manifest_independent_calendar_20261021.md)。

## 完成了什么

- [x] 完整读九晨报源及原30独立辅助/矩阵，再冻结8项PUBLIC compose期望。
- [x] 单目标首轮8/8通过0.63秒，北京时间完成于2026-10-21T10:15:11.1850946+08:00；没有产品失败或断言调整。
- [x] 订阅与item、完全绑定且已撤回P8与item的同源矛盾均拒绝；不能先省略撤回状态再接受局部active证明。
- [x] 重复相同状态正常允许；坏/错绑定P8省略而保留正常历法与item；关闭订阅早退、两种items顺序同拒绝均通过。
- [x] 九产品、原30辅助/测试/矩阵及两份合成fixture不变；含原冻结计划17快照执行前后相同。

## 评测分数

独立PUBLIC规则场景8/8；未运行评测runner或真实模型。本任务未追加兼容、覆盖或性能，不把Core既有观察计为本次结果。
模型、网络、PG、通知均0；规则通过不证明真实来源查询、数据库授权或实际投递。

## 改了哪些关键文件

仅新增独立helper/test及证据，更新本轮活计划；未改产品、原30矩阵或旧测试。

| 新文件 | SHA256 |
| --- | --- |
| manifest_calendar_support_mod.py | `d5d1654543b079c004ef13c0e9599aca4683597c9b5c0142f66cfe5e56123551` |
| test_manifest_calendar_mod.py | `0d5244974fa7ed35ac78825fce5ca0e646696a95c74ca276830426ceb5b2d6aa` |

前者85行/最长函数25行，后者112行/最长函数11行；Ruff/120格式、AST尺寸与类型标注检查通过。
期望只用独立标准JSON/SHA与原公开合成样例；没有导入Core新helper、current_manifest、validate_transit或subscription_basis造黄金。

[首轮证据](BRIEF_manifest_calendar_verification_20261021.json)显式UTF-8 LF，
SHA256 `f9506e59447f8313112415fe909fdfb7b062ca07c4b35c51b9943b9aff95ccc1`。
报告保留16份运行代码/测试/材料前后摘要及原计划冻结SHA；计划状态随后更新，原8行期望不变。
Git发布后的blob字节核验交root，本任务没有提交或推送声明。

## 数据库迁移与回滚方式

无迁移或运行态修改，不需要数据回滚。

## 偏离设计的地方

无。只走公开compose、正常公开类型和FrozenClock，不调用私有门禁入口，也不绕过构造器或改产品态。

## 未验证 / 已知风险

有限8项不构成穷尽证明或整个PR覆盖。host当前投影的一致性不能自证实际读取了PG；真实epoch/CAS、
发送前freshness、外部通知、UI、跨进程并发与CI不由本次验收证明。

## 需要用户或大脑决定的问题

无即时阻塞；不等待离线用户。本轮测试和证据交root后冻结。

## 建议后续

主线接线继续以当前来源授权和事务账本为权威，不能用某条有效局部证明覆盖同源撤回。
本轮不追加兼容、覆盖、性能或真实服务操作。
