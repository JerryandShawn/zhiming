# P3 M4：Runtime与后续接线接口

记录：2026-10-20 23:51 +08:00。工具与c/r接线已验证局部链路，完整P3脚本和M6自动恢复仍由对应里程碑证明。

## 调用顺序

AgentToolsService已在原总事务之前分流chart_compute到execute_chart；该处理器明确拒绝任何现存外层PG连接，然后自行做prepare短事务→事务外Charts计算→post-check短事务和受撤销持久cache。不能再从外层transaction包装它。memory_update/profile_update_request自行做短事务和真实mutation_request；date_calc只给server-only调用，默认不披露。

ToolRegistry给AgentToolsService可注入`charts=ChartsService(...)`，仅替换外部计算引擎，真实PG授权/来源/持久步骤不替换。无确认出生资料/private/crisis不披露chart；无痕临时排盘尚不支持，execute也拒绝，不能借read_only标签写入长期artifact。

## 模型读取可信c/r

Loop在journal.complete之后调用verified_versions并扩展alias_map；chart_lineage先匹配本run/epoch唯一已完成chart步骤的原ToolResult，再核PG cache、产物/claim、来源/版本/内容和规则。只有该路径产生artifact→c、interpretive_claim→r；其他工具自报产物不获引用。

M6应且已调用：

    tool_message(call.id, result, self.cycle, aliases=self.aliases)

可选参数只把安全kind/id/revision/native_id/basis映射放下一工具消息data.registered_aliases，alias_registration为verified_current_run；不修改持久ToolResult。空c/r映射不插空字段，保持旧循环消息字节。最终core4 used_claim_ids使用真实持久interpretive_claim ID；c/r数字只是当前循环可见别名，不能跨run复用。

## 普通更正使当前运行stale

当本run已经采用旧fact时，MemoryService.correct_fact会在同一事务提交新fact、使旧fact superseded、撤销旧来源区间并invalidate_derived(recomputable=True)。结果是core_runs.status=stale、error=STALE_INPUT、lease清空；真实mutation回执已保存。旧journal.complete会因lease失效失败，这是防止旧上下文继续发布的正确行为，不是模型失败，也不能回滚已成功事实来让它继续。

Runtime恢复需要先fetch_run核权威状态。仅stale/STALE_INPUT且本轮用户原话仍active、未撤销时，使用已有repo.prepare_retry(owner,run_id)，取得新epoch/清旧cache，再claim_run拿新lease，重建干净Context和别名；不要复用旧reasoning、模型请求或c/r。保留事实更正与真实mutation账本，不能重新让模型把旧目标再更正一遍来取得回执。prepare_retry自身核原话/撤销/预算，异常即停止；恢复次数必须有上限，不能把取消、来源撤销或任意LeaseConflict当作可自动重试。

目前已测真实更正导致stale、旧lease不能完成journal；自动prepare_retry→新epoch继续生成的完整链路归M6/后续端到端验收，本片没有冒称通过。

## 尚不支持

旧引擎长子进程仍由其timeout控制；本片只验证计算后取消/来源改变时不保存，不代表2秒终止已达标。P8真太阳/交界诊断/推运回归/区间搜索保持unsupported；U4只有TimeRangeParser接口及Unavailable替身。P8、U4实际接入必须保留同样授权/内容绑定，不把合成预览别名照搬成可信账本。
