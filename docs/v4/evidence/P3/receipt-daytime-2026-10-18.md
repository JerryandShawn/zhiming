# P3 阶段回执（开工与M3a离线首切片，阶段未完成）
- 分支 / 最后代码提交：v4/p3-agent-runtime @ e9ad78b98e61a3d48e11253b7670f52701a8adff（本机等价97f656cd177d573a0eb9c11a668ea0d13a40881d）；PR：https://github.com/JerryandShawn/zhiming/pull/8（草稿，不自行合并）。
- 基底：P1/P2均CI绿合并后的v4/main@b9a89b6f84f7bebb640de080548010859aae630c。
- ExecPlan：docs/v4/execplans/P3_agent_runtime.md。

## 完成了什么（对照阶段提示词的验收标准逐条）
- [x] 正式计划纳入18索引D1/D2/D4/D5、U4/U7和P5b B后续F1；F1严格依赖完整ContextEngine，不提前实现A/C。
- [x] 可独立调用真实PG ContextEngine离线原型：有界历史/事实/撤销目录、源revision/span、owner/subject/case隔离及首轮全局约束。
- [x] 完整规范化请求policy_units预算/压缩/溢出拒绝；同epoch tag与工具ID配对、reasoning/signature保留、受信摘要不丢receipt/receipts/operation_id/status。
- [x] 63项目标测试通过73.30秒；R07 300轮600条真实PG、300次ScriptedPort、最大18494策略单位；10000条真实服务写入，多窗口候选81，压缩142968→2389，required溢出拒绝，原文hash不变。证据：同目录validation-summary.json及两份压力JSON。
- [x] B1固定候选上线/授权计划已准备于docs/v4/release/B1_stage_plan.md；只写计划，服务器连接/迁移/部署/消息请求0。
- [ ] 完整M3a token守卫与实际usage/3×60k持久提醒：尚无可信会员framing与P1b账本接线。
- [ ] M1/M2/M3b/M4/M5/M6/M7：循环恢复、U4/U7、完整分层/无痕/检索、提交/dispatcher/工具/提示词与真实验收均未完成。
- [ ] P5b B实体/迁移/API/topic_route/分区上下文：按用户要求排在完整M3后；A模块线、C前端线，主线未做。

## 评测分数
- 新切片63/63；原脚本80/80、框架48/48（11.77秒）。全部v4 678/678、208.35秒、零skip；旧Core本P3未重跑，沿用P2基底553回归证据（P1b同轮另跑553通过），不冒充同命令重跑。最终CI状态见每日汇总。
- 真实模型模式未运行，真实请求0；这些原型测试不等于完整P3的47场景或真实R07质量成绩。

## 改了哪些关键文件
新增agent/context_types.py、context_sources.py、context_budget.py、context.py及包文件；tests/v4/agent三文件。四个主要生产文件共670行、各≤400行、函数≤60行。未接旧runtime/ModelRegistry。

## 数据库迁移与回滚方式
无新迁移；测试只用本机55480/core_test_main独立合成schema，测试后清理。业务实现只读上下文，不改存储原文。回滚可移除未接线的新模块，默认v3不受影响；未碰stage/生产。

## 偏离设计的地方（及理由）
计量明确policy_units（离线规范化JSON UTF-8量），estimated/upper_bound/actual token均未伪造；未知会员framing拒绝live。先交独立原型，不能宣称完整ContextEngine/token门完成。为避免共享helper静默截断设目录支持域；同双时间戳歧义拒绝，后续运行时序列契约再扩展。原L5按轮预算移出，30轮/40轮块推进与稳定前缀留M3b。

## 未验证 / 已知风险
没有真实180k token保证、缓存命中或调用后账本；单工具>8k但总预算未超30k尚不单独预压缩。当前仅主线程最新user，事实默认≤256/撤销≤512，超限拒绝；不支持完整无痕/任意规模事实。build后发生撤销的发送/提交闸门待M4。MemoryService有效期与此刻需同Clock对象。新代码最终CI尚待发布后核验，草稿未合并。上游anyio告警不在本轮扩范围升级。

## 需要用户或大脑决定的问题
大脑：L5追加与“前五层整体不变”验收冲突、P5b具体迁移编号协调、可信会员framing/有界支持域转正方案。用户：仅将来每批E1/E2或探针的明确开始；当前不请求重复D1/D2/D4/D5。B1 stage/生产执行另需那一次具体授权。

## 建议后续
按ExecPlan完成实际循环/工具与完整M3，消费模块线relative_dates等交付；P1b合并后统一guard/usage，不造假守卫。完整M3后才启动P5b B。真实请求逐批用户在线开始，每批≤10、共享80/5h、间隔20分钟、夜间0；concurrency_limited/Access terminated持久全停。
