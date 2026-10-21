# TA02 旧固定牌读取回归修复

时间：2026-10-21 02:08 北京时间。只在本机隔离 PG15 和 ScriptedProvider 验证，无服务器、真实模型或飞书请求。

固定 02点提交头 `2b25175` 的原 TA02 由此前通过变成失败：工具确实完成，原牌未变，但只调用一次模型，随后 business/EvidenceError，缺少实际 failed→running→success 的解读重试事件。本机原单例复现为 1 failed。原因是旧 manual 牌阵的 context_snapshot 只有 question_message_id 与 message_id/version，没有 source_ids/thread_id/完整区间；实际成功读牌不建新格式 c/r 缓存，而 Loop 强读缺失缓存并终止。

最小修复仅在专业注册入口处理合法旧读牌：原调用方 run 的 epoch/lease、owner/subject、真实完成步骤/精确输出、本轮选择的 ready native viewer、完整只读 ToolResult 模板、有效旧问题来源与实际 reading 必须全部复核；question_sources 明确不足，且从未存在本步骤的新缓存行或其创建 operation，才返回空专业血缘。正常旧牌可继续读取，缺失区间不推断、c/r 不伪造。新格式缓存缺失/已删除/篡改不能静默降级，failed ToolResult 直接保持空血缘。

验证：原 TA02 单例红后转绿（1 passed / 2.21s）；最终独立反例、原 TA02 不变断言、专业血缘与快照目标合计 **52 passed / 24.62s**，0 skipped、0 warnings。原 TA02 实际调用两次模型，同一 native draw 和唯一 reading 从 failed 经 running 到 success；used_claim_ids/used_fact_ids 为空，PG 中 artifact/interpretive_claim 为0。

反例包括篡改结果别名、跨 owner、旧 epoch、伪 lease、错 subject、原话版本变化、问题范围撤销、牌面变化，以及新格式缓存物理缺失、软删除、输入篡改和移除缓存后再改成旧格式。现有严格证明接口仍拒无缓存的旧牌，只有已完成工具读取的 Loop 注册边界允许空专业血缘继续。

ruff/format、AST 文件≤400/函数≤60、diff check 通过。未修改原 TA02 场景、评分断言、固定回归副本或事件契约。此为相关目标回归，固定提交头完整 M8/全库结果由主协调另核。

2026-10-21 07:29 北京时间续作复核：指令板仍为 v1。保留原 WIP，不覆盖其他并行源；在当前共享工作树重新执行上述52目标（包含原 TA02 单例），结果 **52 passed / 16.75s**、0 skipped、0 warnings。ruff、format 与 diff check 再次通过。没有启动全量回归，未修改 parallel/case own-effect 证明文件。
