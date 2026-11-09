# P5 自然语言遗忘接线

MemoryService.retire_from_message 识别“把我……的事忘了/忘记”等完整明确句，委托 MemoryWithdrawalService.forget_from_message。代码只以原文中的字面主题与当前有效事实匹配，必须唯一且与所选 fact_id 相同；模型的猜测 ID、query、授权标记不能扩大范围。否定、问题、假设、引述里的命令拒绝。旧路径的删除动词也先遮蔽引述，防止只剩一个事实时误删。

forget_from_message 先绑定当前用户消息修订与稳定操作 ID，再取得首次目标修订；否则删除后重放会误用 tombstone 新修订。沿用既有所选项服务的 owner/人物/事项、当前来源、时间、无痕与双重绑定守卫。回执只留 ID/状态，不能用旧授权恢复已删正文。

评测初始化：历史敏感 pending 与助手回复由真实脚本 Runtime 生成；保留声明的原话 ID/时间，助手引用有真实运行依赖。旧模型脚本 query/scope 按唯一初态事实转换成真实工具参数，expect/seed 评分契约不变；不能把 ambiguous query 当作具体用户授权。

需要主线配合：自然语言 memory_forget 可以真实删除当前冻结上下文引用的事实，但这会清除旧 epoch 的工具输出并触发一次原生重生成。core_mutation_requests 保留 body-free 删除凭证，最终回执尚未跨失效边界接回。应由主线将当前 owner/用户命令/运行和旧操作的真实删除证明安全接入最终输出，不恢复旧工具正文，不放宽 lease/epoch/来源守卫。模块线本片未改 Agent 循环、提交闸门、渠道或模型层。

F02 仍 0/1；另有 proposal 空 tombstone 与 fixture/native ID 的逻辑视图口径待确认。不得注入 receipts 或改硬断言声明通过。见证据 20261024_memory_natural_forget.json 与总索引 20261024_memory_coverage.json。
