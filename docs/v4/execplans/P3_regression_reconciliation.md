# P3 新调度与隐私契约的回归收口

遵循 `.agent/PLANS.md`，全部时间为北京时间。本计划不改变冻结评测 corpus 或原始 legacy 文件。

## Purpose / Big Picture

让新线程串行与隐私保护接入后，旧组件测试仍保护原本的来源、回执、撤销和不重复洗牌行为，并明确新增限制。不能靠放松运行闸门或跳过失败来绿灯。

## Progress

- [x] (2026-10-21 01:07) 固定76c62b8全v4实测42失败/1484通过，完整失败记录保留。
- [x] (2026-10-21 01:09) 定位7项排盘失败的外层事务错误；将隐私检查移到计算前/真正写入前短事务，2项排盘及3项隐私目标连同规则共62项通过。
- [x] (2026-10-21 01:22) 串行组件及原注册排盘相关目标138通过，原42失败中的41个nodeid逐项映射；不全局结束其他run，M04由root目标另证。
- [x] (2026-10-21 01:17) v3 corpus连接测试保留普通真实服务断言，明示无痕强化零落盘；发现并修正eval原话预写缺少原子回滚，完整该模块和排盘目标57 passed/32.28s。
- [ ] 新固定头全量、Core与精确头CI全部复核；尚不能宣称P3完成。

## Surprises & Discoveries

Root新增长期副作用总闸门时把chart_compute放进事务，既有计算模块明确要求无外层锁，原注册排盘测试正确暴露缺口。这是生产代码错误，修生产代码，不改这些断言。串行闸门则是28号/M7明确新契约；旧组件测试多次setup而未结束前一轮并不是用户并发请求，须给合成轮次显式终态。真正并发测试保留第二轮queued和首轮结束后的同deck验证。

强化M04断言又发现V3Target先由seeder写原话，再调用service.submit；隐私闸门抛错时已留下孤立life原话。将这两个数据库步骤包在同一owner事务，模型执行仍在事务外，拒绝会回滚全部预写。没有为通过测试放松隐私，也没有更改冻结M04。

新增无痕保护使当前v3入口遇到明确无痕请求时在任何原话/运行持久化前拒绝；原M04连接测试只要求模型成功，没有验证此保护。这一行为变化须在P3发布审阅中单列，不应宣称所有v3输入行为完全未变。B1固定b9包没有此改动。E1历史评分和v2.1冻结 corpus/指定源码不因本候选改写；不能用新源的隐私拒绝去覆盖历史基线分数。

## Decision Log

保留注册排盘的无长事务断言，检查放在实际持久化事务里，并新增计算过程中真实用户拒存的PG反例。测试辅助finish仅处理本场景持有的run，未执行完整Runtime的组件轮次用显式合成取消/失败收尾，不能伪造成功core4。

v3 corpus连接测试对明示无痕强化为EvidenceError、零新原话、零排队、零模型、原seed/修订不变，普通场景仍沿原先真实服务成功断言；只改未冻结连接测试，绝不改M04内容、评分或legacy清单。默认v3的这项限制保留为P3验收需大脑复核的行为变化；本夜不将其部署。

## Outcomes & Retrospective

当前仍在修复，62项目标不能替代失败全量。完整新头验证和风险复核前，P3保持Draft/No-Go。

## Context and Orientation

复用 `repositories/postgres.py::claim_run/fail_run`、`application/agent_tools_charts.py::execute_chart` 和原提交证明；不改变lease/epoch/owner/来源/Outbox不变量。原组件入口为 `tests/v4/agent/test_toolkit_pg.py::setup`；v3连接测试为 `tests/v4/test_v3_seed_corpus.py`。

## Plan of Work / Concrete Steps

先目标原失败场景，再在北京时间00–15分钟启动新固定Git快照完整回归。仅隔离PG与脚本模型，测试凭据清空、追踪关闭、TZ=Asia/Tokyo。

    python -m pytest tests/v4/agent/test_computation_wiring_pg.py tests/v4/agent/test_turn_privacy_barrier_pg.py -q
    python -m pytest tests/v4/test_v3_seed_corpus.py -q

## Validation and Acceptance

M04拒存、TA01–03不重复洗牌、X03–05恢复/串行/取消，以及R类来源撤销仍须真实PG证明。无跳过或降低既有来源授权断言；真实模型质量未测。

## Idempotence and Recovery

无新迁移或依赖。修复可回退代码；不清理真实用户数据，不停止共享PG。测试只清自己的schema。

## Artifacts / Interfaces

失败记录 `docs/v4/evidence/P3/2026-10-21-0100-pinned-regression.md`；后续真实结果追加独立证据。公共事件Schema不变，日期记录全部+08:00。

## 修订记录

- 2026-10-21 01:13 +08:00：创建，明确生产缺陷、合法测试契约变化与待验证边界。
