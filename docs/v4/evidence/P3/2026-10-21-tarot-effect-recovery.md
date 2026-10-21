# tarot_start 已提交、Journal 确认前退出证据

记录：2026-10-21 07:39（北京时间 UTC+08）。本片只新增真实 PG 测试、ExecPlan 与此证据，没有修改业务源码或已冻结通用恢复矩阵。真实模型请求、服务器访问、飞书发送均为 0，未提交/推送/合并；由主代理统一发布候选。

`tests/v4/agent/test_tarot_effect_recovery_pg.py` 使用实际 AgentRuntime、ToolRegistry、TarotService、原 mutation_request 与独立本机 PG schema。ScriptedPort 只代替模型；夹具清凭据、禁追踪并拒绝 HTTP/子进程。包裹的 `_shuffle` 只计数并调用原实现，没有设置假牌或替换抽牌结果。

目标 Journal.complete 首次确认 tarot_start 前，另一 pool 连接不用 owner advisory lock、只做非锁 SELECT，确认原 agent_tarot_start mutation 收据、原 native draw 和以相同 operation_id 建立的 create 请求都已可见，然后恰好一次抛 SystemExit。步骤保持 started，output/finished_at 为空，usage={}。这是效果确已提交的崩溃窗口，确认事务的存在不被误作效果未提交。

执行：

    python -m pytest tests/v4/agent/test_tarot_effect_recovery_pg.py -q --tb=short

最终结果：**6 passed in 3.58s**。最小 auto 单例先为 1 passed / 1.57 秒；首次完整组 6 passed / 3.63 秒，随后补稳定收据/operation/完整事项比较再运行得最终结果，不相加计数。

通过的两种恢复：auto 已固定三张未揭示选牌，以及 pick 已固定隐藏牌堆等待选择。只过期旧 lease，在同 epoch 取得不同 lease token 后恢复；原 78 张牌的完整牌堆、唯一牌 ID/牌背、方向、已选状态、draw/native request、mutation/operation、事项及用户来源均逐字段相同，洗牌计数始终 1。首脚本模型步骤重放，只产生最后一条新脚本模型回答；完成 Journal 输出仍等于崩溃前真实输出。模型只收到既有脱敏 viewer，未泄漏 private_deck 或未揭牌 ID。

通过的四种拒绝：真实 DispatcherCancellation 取消运行、TarotService 取消固定牌阵、真实 repo.delete 撤销当前消息、真实 source_span 撤销问题区间。安全操作后再进入旧运行均抛领域错误；新脚本模型请求为 0，draw/request/deck 状态保持安全操作完成时的原样，没有重复洗牌、复活牌阵或发布 assistant/final。待确认步骤没有被伪造为 completed。

Ruff（E,F,I,B,UP,SIM，120 列）、format 与尺寸检查通过；新测试 166 行、最长函数 37 行。本片没有暴露或写出实际牌堆内容；以上为合成输入下的一致性证明。

未覆盖：选牌或揭牌与恢复同时发生的额外并发窗口、真实供应商、正式 stage、整库回归。没有发现本窗口需要改生产实现的缺口；不能据此宣称所有塔罗/发布场景已验收。
