# MOD 调度公开边界阶段回执

- 分支 / 最后提交：归属v4/mod-organize；本子任务未运行Git，提交号与PR状态由root回填。
- ExecPlan：[28项独立计划](../../execplans/MOD_scheduling_public_boundaries_calendar_20261021.md)。

## 完成了什么

- [x] 按冻结真值新增28个公开案例：坏P2端口8项、农历资源7项、合同6项、公历上界3项、时区4项。
- [x] 首轮28/28通过0.11秒，没有产品失败、修复或真值调整。
- [x] 经root单独批准，完整scheduling一次插桩兼容1268/1268通过2.79秒，包含原1240和新28；不是跨项目全量。
- [x] 13相关源和9份完整套件测试/样例前后摘要均相同；FrozenClock、空key、tracing关闭及socket禁止保持。
- [x] 新测试Ruff/120格式通过；203行、最长函数9行、最长行116字符。四活计划及新接线补充已更新。

## 评测分数

本轮是纯测试补充，未运行模型或评测runner；真实模型、网络、PG、通知均0。

| 目标 | 行覆盖 | 分支覆盖 | 综合覆盖 |
| --- | ---: | ---: | ---: |
| recurrence_calendar.py | 46/46，100% | 21/22，95.4545% | 67/68，98.5294% |
| recurrence_civil.py | 35/35，100% | 12/14，85.7143% | 47/49，95.9184% |
| recurrence_contracts.py | 80/80，100% | 36/36，100% | 116/116，100% |

综合为行与分支计数合并，不是两百分比均值；不把civil分支写成90%以上。
原09:45完整三轮是历史快照，不包含此后新增28项；本轮不能追溯补入旧数字。

## 改了哪些关键文件

唯一新增测试：[test_calendar_boundaries_calendar_mod.py](C:/Users/Administrator/Documents/Codex/zhiming-v4-mod/tests/v4/scheduling/test_calendar_boundaries_calendar_mod.py)，
首跑前后SHA256均为`9b17b923b1ad3334931c092fdee37be629121b8621afc24d19f45c270c93aaab`，显式LF。
没有改产品或既有测试/黄金。新证据分别保留：

- [独立首轮](SCHEDULING_calendar_independent_first_20261021.json)，SHA256 `b23418c86960feba00e5a706557f02fd243e34477d212da8a59374b6409ddfdb`。
- [模块兼容与覆盖](SCHEDULING_calendar_coverage_20261021.json)，SHA256 `003b9a0534782acb9045d63774b4c4af712250425c884b8886ad0ec79eea7043`。
- [新接线补充](../../integration/mod/SCHEDULING_calendar_boundaries_20261021.md)；原Q4指南不修改。

JSON全部显式UTF-8 LF；提交后的Git blob字节核验由root发布时执行，本子任务没有Git操作或推送声明。

## 数据库迁移与回滚方式

无迁移、无运行态改动，不需要数据回滚。

## 偏离设计的地方

无。测试仅使用公开构造器、next_trigger、显式FrozenClock及注入本地端口；没有私有态、猴子补丁或生产替换。

## 未验证 / 已知风险

calendar剩余分支为39→函数退出；civil剩余21→函数退出、46→41，共3条未执行arc原样保存。
没有为100%追加镜像案例。当前结果不证明真实cron、PG并发、外部排程/通知、CI、全PR覆盖或生产上线。
合成P2端口不认证实际来源授权；主线仍需当前scope、来源/订阅版本及投递前重新核验。

## 需要用户或大脑决定的问题

无即时阻塞；不需要离线用户回答。本轮证据齐后冻结，由root统一发布。

## 建议后续

将本轮测试纳入后续正常模块回归；实际接线按Q4当前来源、原due和Outbox规则验证。
本轮不再追加覆盖或性能运行，也不改变原P2/baseline。
