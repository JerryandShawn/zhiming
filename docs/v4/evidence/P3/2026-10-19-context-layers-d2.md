# 夜间Context分层与D2离线子里程碑

截至2026-10-18 22:56 +08:00。属于夜M3的可独立验证切片，**完整M3/P3未完成**；无网络模型调用、服务器访问或飞书发送。

## 已实现

- 层顺序为L0→L2→L3稳定→L5→L4→L3易变→L1→L6；工具定义在请求独立字段。选中事项的标题、目标与最近3条有效事件、带来源的相关笔记/情景、跟进/提醒/缺口进入各层。派生内容无血缘、跨人物/事项/线程、来源失效或撤销时拒绝或排除。
- L5默认30轮目标，超过40轮时前移10轮。块内仅追加旧前缀不变，消息别名用源时间线序号，窗口前移不重新编号既有消息。超过预算可丢旧窗口原文；PG原文不改写。完整L5两轮整体相同的矛盾仍待大脑，未宣称通过。
- 注入依赖只保留最终层与递归来源的版本；压缩移出的旧消息不再误登记为实际注入。
- TokenMeter接口明确estimated/upper/actual及provider/model/version，完整规范化messages/tools/tool_choice/reasoning均交计量器。上界未知拒绝；>120k压缩到约30k，required超过180k整次拒绝；配置不得抬高180k硬限。现有UTF-8策略单位另存，不混作token。
- D2真实PG计数：以已完成model步骤为事实来源，在run.usage保存元数据与幂等指纹，thread保存连续计数/待汇总提醒。actual未知为null；只有上界超限时另记measured_upper提醒；第三次触发，≤60k重置。重启、重复确认不重复计数，Journal完成后的provider usage不可覆盖。

## 验证

使用P2 Core Python3.11、本机隔离PG15/core_test_main；每个用例独立p2_test_* schema。清除provider凭据并关闭tracing，测试拒绝HTTP发送。最终目标回归命令：

```text
python -m pytest tests/v4/agent/test_context_budget.py tests/v4/agent/test_context_pg.py tests/v4/agent/test_context_layers_pg.py tests/v4/agent/test_context_tokens.py tests/v4/agent/test_context_usage_pg.py tests/v4/agent/test_context_token_stress_pg.py -q --tb=short
python -m pytest tests/v4/agent/test_context_stress_pg.py -q --tb=short
ruff check --select E,F,I,B,UP,SIM --line-length 120 <本切片Python>
ruff format --check --line-length 120 <本切片Python>
```

目标98项与压力2项的实际输出在日报确认；压力两项57.24s：R07 300轮/600条、Scripted300次、provider0，最大18,411策略单位；一万条原文哈希前后一致，候选返回≤81条，远处3项约束仍存在。此次原始元数据见同目录`2026-10-19-context/r07-300-rounds.json`和`10000-messages.json`。它们明确actual/upper为null，不作为Kimi180k token证明。

另有真实PG大历史用例，采用明确标为synthetic的字符单位计量器：>120k触发L5裁剪，最终≤30k、约束和本轮完整保留，PG哈希不变；181k required整次拒绝。synthetic计量器永远不获真实端点准入。

## 未完成、阻塞与风险

会员k3-256k tokenizer/framing缺可信校准，**默认真实发送继续失败关闭**；没有真实token/缓存命中率/模型质量结论。新UsageService尚待Loop每次模型步骤完成后接线；send-time撤销闸门、完整循环、无痕/inbox、槽位、命盘摘要、时间检索模块适配与正式v4场景仍在队列，不能将本切片算完整M3。

压力附加用例最初以181k无标点连续同字作为MemoryService入库输入，卡在既有jieba分词阶段；约3分钟后仅停止该次pytest子进程，未停止PG。该次记为未通过/性能阻塞，未冒充上下文结果；hard-limit新用例改为同样181k、带自然分句的合成中文以隔离被测上下文门。超长连续单字的入库性能仍待后续处理。进程强停可能留下本机合成测试schema，不据此清理其他工作树或不明schema。

新增迁移0，v3路由与服务未切换。回滚为撤回本子提交；没有线上动作可回滚。完整CI以精确远端提交的结果另报。
