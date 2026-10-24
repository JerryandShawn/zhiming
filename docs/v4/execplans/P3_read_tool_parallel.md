# P3：同轮独立只读工具并行

本子计划遵循`.agent/PLANS.md`及原P3循环要求。北京时间2026-10-21 01:52建立；root委派同一协作代理独占`agent/loop_batch.py`、`agent/loop_cycle.py`、`application/agent_tools.py`、新增纯读授权适配和测试，不碰并行代理的codec/Runtime/config/tarot文件。

## Purpose / Big Picture

同一次模型响应中的独立只读工具可并行计算，写入、ask_user、options与带缓存副作用的tarot_read仍按模型顺序处理。跨run Dispatcher线程池不算同轮并行。不得改变工具参数指纹、稳定step/operation、崩溃恢复、回执、来源/取消最终闸门或模型收到的结果顺序。

## Progress

- [x] 审查Journal游标/完成事务、原LoopCycle._tool和ToolRegistry.read_only。Journal可以按模型顺序先reserve多个step，完成仍受原lease/epoch保护。
- [x] (2026-10-21 07:33 +08:00) 实施共享prepare/invoke/accept路径；串行/并行均消费同一逻辑，原工具执行入口不复制。
- [x] (2026-10-21 07:33 +08:00) 本机隔离PG的9项独立目标通过6.11秒；在真实日历handler计算区屏障证明两worker重叠、反序完成仍原序回收，覆盖写/ask屏障、重复限制、取消/撤销迟到丢弃及部分完成崩溃重放。
- [x] (2026-10-21 07:34 +08:00) 并行目标与原Loop/controls/ToolRegistry/AgentRuntime组合74项通过25.73秒；7个源码/测试文件Ruff E,F,I,B,UP,SIM、120格式及尺寸通过。
- [x] (2026-10-21 07:36 +08:00) 交叉恢复组合由协作代理复验：矩阵/pending证明/原own_revisions共41项通过20.32秒；Snapshot/Runtime/Journal/case_versions另47项通过17.16秒。原真实memory_update stale与完成证明负例保留。
- [ ] root统一提交推送；后续固定tree全回归。上述目标有重叠，不以合计数当唯一测试数量。

## Plan of Work

只并行连续、实际exposed且registry定义read_only的保守白名单：time_context、calendar_lookup、profile_get、memory_search、case_list，date_calc仅在获准披露后参与。只读工具不能接收本响应其他工具新生成的别名作为依赖；遇写入或控制工具必须先完成前组。所有future只执行原registry.execute，不碰Journal、alias、events、messages或cycle计数。

主线程按原顺序poll、发tool_call、验证fingerprint/暴露/重复上限、reserve步骤并复制ToolContext。已完成步骤不再执行，非法/未暴露/重复/turn_ended结果在主线程确定。只读新步骤至多两个worker，结果按原模型顺序在同owner事务内complete→register，再写messages/发tool_result。重复导致停止时之后的call仍按原契约记turn_ended；ask_user与无痕提醒一次确认继续原串行逻辑。

等待future用短timeout反复poll取消/续租，不跨I/O持有PG事务；取消时cancel未开始future、shutdown(wait=False)，迟到的纯读结果不回写步骤或发事件。物理应用读仍执行现有权限检查。不得并行任何真实有副作用的工具，仅标read_only不足以判断tarot_read等持久缓存工具。

## Validation and Acceptance

真实PG与事件/屏障断言重叠，不靠脆弱绝对睡眠测吞吐；强制第二个先完成仍保留原序；已完成步骤重放零执行；崩溃只补未完成，operation ID稳定。三次相同工具的原熔断语义保持，写入和提问不被并行越过。取消2秒内返回且迟到结果不产生final或写入。私密/危机/未暴露工具不能借并行扩大权限。原工具、Journal、控制和Runtime目标回归保持。

## Surprises & Discoveries

tarot_read标记只读但当前需要受保护runtime缓存，故属于不能放进纯读并行组的例外。case_list只读索引证明和aliases必须在主线程完成，不能在worker里并发改引用状态。

应用层原纯读取在owner事务内执行，单有线程池仍会被PG锁串行化。新白名单入口分成短事务原权限核查→离锁计算/短查询→短事务重核，最终Journal及引用登记仍由主线程完成。真实日历测试在handler内部断言没有repo线程事务且两个worker同时到达屏障；不拿executor启动当重叠证明。

早间跨片复验发现新增accept前的全control.poll会把本轮合法写入尚未确认的版本变化误认外部变化。删除此新增poll，保留prepare及只读Future收集前poll、Journal.complete原lease/cancel/deadline核查和_register原依赖/撤销核查；不削弱原闸门。该片不是02点固定快照组成部分。

## Decision Log

先保守白名单与固定两个worker，无新依赖、无模型调用。新工具默认串行，只有核实纯读语义后可扩展。运行配置由另一片负责，暂不加未实施的并行配置键。02点固定快照不等待本未完成片；完整测试只对已提交tree运行。

## Outcomes & Retrospective

实现及本机窄组合已验证，精确命令、源码摘要和边界见`../evidence/P3/2026-10-21-read-tool-parallel.md`。07:28恢复前额度中断，无03–06点执行证据，不补造小时进度。没有服务器、真实模型、飞书或合并操作；未运行这份新片的全库回归、真实供应商并行或外部渠道验收。
