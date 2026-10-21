# 当前原话→反思/八节画像→报告：主线接线说明

本轮是独立组合验收，不提供运行时服务。入口均为已有公开API，未改产品。

## 当前来源与写入

用认证scope构造当前 `MemorySnapshot` 和连续 `SourceAnchor`；`plan_write` 的拒绝计划不执行apply，
更不能用计划文本伪造saved回执。允许的计划用 `apply_plan`，同operation原载荷重放不增加事实。
assistant_claim按合法note形状处理，仍不得进入用户事实/画像/用户报告。

## 反思和画像

`schedule_reflection` 只返回enqueue意图；主线还须当前permit、后台额度、同线程事务锁与运行租约。
`plan_reflection_work` 在执行前重核输入指纹、当前原话和来源ledger；本轮既检查旧intent失效，也检查零副作用。

八节 `ProfileDocument` 是合成host明确构造的当前已批准画像，不把反思proposal自动保存。
`render_about_me` 保留来源锚、分析标签与当前来源过滤，pin/用户编辑不豁免撤源。

## 报告投影和缓存失效

`compose_period_report`不查询记忆库；主线须将画像中的当前事实映射为 `ReportRecord`，
并在同一授权范围读取当前 `BriefSourceState`。测试保持旧ReportRecord正文/旧BasisRef不变，
只替换实际当前source state，确认报告自行拒绝不匹配输入，而非helper预先丢掉所有坏记录。

本轮合成host的来源值SHA绑定 owner、subject、原话全文、角色、origin、revision、原话时间和source epoch。
正文/role变化即使漏bump revision/epoch也不能继续匹配旧hash；撤销/无痕/optout有显式当前flags。
仅传消息ID、仅传revision或沿用旧hash不满足这个组合契约。真实PG如何原子投影和并发撤销仍待主线验证。

epoch变化表示缓存代次已变，不意味着删除仍有效的源事实；当前原话相同的事实可以在新授权快照重新投影。
本测试拒绝旧intent/旧画像文档和旧报告依据，不把它们当成永久数据删除。

报告按显式owner时区和 `[start,end)`；测试用独立的2026-10-19至10-26周界跨六区校对，
不是从错误实现读取一个边界再把它当gold。安排/提案仍不是已完成结果或提醒送达证明。

## 边界与证据

- 41条冻结语义场景、64个目标；1000随机六时区完整正向链再撤源。
- 随机正向链限定原话仍在目标期间；当地午夜前后20分钟的正向样例作显式调整。
  真正起止边界的包含/排除另由六区独立民用周界矩阵验证，不把有条件随机样例当成全部边界分布。
- 120完整链性能样本包含断言和tracemalloc开销，不能当生产延迟SLA。
- D4只验证此链没有主动提醒/发送入口和副作用，默认后台permit关闭；没有验证真实使用提醒调度开关。
- 没有PG、HTTP、模型、真实用户资料、飞书或服务器调用；没有读取Q5 B或75校准材料正文。
- 验收见 `docs/v4/evidence/MOD_2026-10-21/MOD_final_pipeline_verification.json` 与同目录阶段回执。
