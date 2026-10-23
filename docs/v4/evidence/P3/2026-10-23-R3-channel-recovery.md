# R3 渠道恢复（2026-10-23，北京时间）

X03a（网页）和 X03b（飞书）均从真实 PG 步骤日志恢复，同一运行、同一 epoch、同一条已完成工具步骤，最终各只有一条事实和一条原渠道助手回复。网页 Outbox 为 0；飞书通过真实 native ingress、2.5 秒持久合并、Outbox 服务与本机注入 transport，只有一条 sent，重复处理仍只调用 transport 一次。

生产 Outbox 的 prepare、claim 均重新校验 PG 原话及当前来源授权、人物/线程、依赖修订和外部用户绑定。网页已绑定飞书也不能误投；旧误排队行在领取时变为 stale、尝试数为 0，不调用 transport。请求自填 channel 不提供权限。复用 ingress_sources 的撤销与局部删节检查。v4 scheduled_report 必须有匹配本轮结果的真实持久 report manifest；缺失时拒绝。core3 保持原逻辑，送达不明仍不自动重发。

## 验证

全部使用已有清凭据窄测试启动器、真实隔离本机 PG15、TZ=Asia/Tokyo、替身模型和本机 transport。

| 检查 | 结果 |
| --- | --- |
| 契约、原框架、扩展契约 | 52 passed，15.74s |
| 渠道守卫、恢复、读取端、回填、塔罗血缘、工具及旧 Core 飞书 | 112 passed，1 个既有 Starlette 告警，54.64s |
| 最终守卫 9 例 + 完整 P3 scripted CLI + X07 native 合并 | 11 passed，1 个同类告警，43.29s |
| 最终完整 P3 scripted | **48/48**；81 个合成模型步骤，评审 0 次，场景执行 20.162s |

窄组原始记录分别为 `private/safe-narrow-ac7ea8fff5a244cfbd16cb807923a8b3`、`private/safe-narrow-aa07dfa8c00a4b02bb77929c0fae10dd`、`private/safe-narrow-13e2e3342cde43ee8e4e4382ed3a8a85`；最终脚本报告保存在 `private/r3-scripted-20261023/scripted-v4.json`。测试运行数与场景数不相加。

初次连接时本机 PG 未启动；由主线恢复原测试集群后再测。守卫首轮出现模块循环导入、未进入业务测试，已改为延迟导入；原失败记录保留，不计通过。没有重复运行整库回归。

## Decision Log

35 号 R3 经用户明确要求执行：原 X03 混合了网页发起与飞书投递的互斥期望，现仅在 v4 语料中替换为 X03a/X03b。两者保留原始用户请求、工具、崩溃点、恢复 operation、无重复写入与无重复投递的意图；崩溃发生于最终提交之前，两渠道当时均无 Outbox。其余 46 个原契约不变；原 80 题库及 X03 历史记录不变。新 48 题分数不直接与旧 47 题比较，不通过伪造 Outbox 修分。

旧正例只迁移非法跨渠道来源：读取端继续保护权威依赖和 stale；回填继续保护 sent/uncertain 不变与不重发；删牌继续保护派生清理、独立事实和旧投递不可领取。相关回执投影、冻结信封与 core3 断言均保留。

未验证：真实模型质量、真实飞书、stage/生产；均未调用或访问。本轮评测仍使用 DeclaredDateParser 声明替身，不证明 U4 自然语言时间解析准确性。本证据不代表整个 P3 或首发已经验收。
