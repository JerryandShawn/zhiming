# P5 确认动作接线

应用入口沿用 MemoryProposalService.accept；remember_category=true 时，当前认证用户在所选提案上明确提交“请保存这条记忆，以后这类都记”或“以后这类都记”均可，原文逐字进入 approval source_ref。普通保存仅接受原 SAVE_ONCE。必须保持提案 revision、原话版本/范围、角色、owner、人物、无痕、撤销及操作 ID 检查，不能把自由文本搜索到的短句自动视为按钮授权。

评测入口 MemoryActionDriver 位于 tools/eval/targets/v4_memory_actions.py，仅供本机合成场景。初始 pending 由真实 leased v4 memory_write 创建，源消息沿用种子原始 ID；不直接插入提案/事实，不消费脚本 db/receipt/event。动作通过 ThreadService.receive 写实际 web-action 消息，调用真实 accept；同一动作重放复用原 revision/operation_id，写入不增加。

公开路由/按钮接线仍由主线完成。本片未改 Agent 循环、提交门、渠道、调度器、模型层。consent.category_updated 是评测观察名：只在真实 settings 和 consent/proposal 检查后提供；没有把这个别名伪装成已发出的 SSE。

M08 仍不通过：类别授权已通过，但第二轮带范围日期的 event 写入未满足保存/数量断言。不得改原评分、伪造具体日期或把临时事件偷换成背景事实。需要继续核对 P5 范围日期语义并与主线协调必要的时间契约；F01–F04 真实遗忘/撤销动作仍待完成。
