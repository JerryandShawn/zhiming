# P3 M7：双通道调度与真实本机流取消

本 ExecPlan 遵循 `.agent/PLANS.md`；时间一律北京时间。

## Purpose / Big Picture

让网页、飞书等入站只排队，由双通道 dispatcher 调用受信 RuntimePort。后台容量不能占满交互通道，同一 owner/线程只能存在一个有效租约。通知用于快速唤醒，2 秒轮询用于丢通知恢复；取消写 PG 权威标记并关闭模型流，已生成文本以 interrupted 保存。

## Progress

- [x] (2026-10-21 00:02) 完整核对 P3 调度条款、蓝图 §3.4、0005 schema、旧 queue/claim/renew 与 transport 取消实现。
- [x] (2026-10-21 00:15) 双通道 claim、全局容量、同线程锁与提交后通知。
- [x] (2026-10-21 00:15) LISTEN/NOTIFY worker 与取消/续租真实 PG 集成；私有回调移交一次 clean epoch 新租约。
- [x] (2026-10-21 00:15) 真实 loopback HTTP 完全静默时取消 47ms，partial interrupted 与来源撤回清除均通过；最终相关目标 30 passed / 8.94s。
- [ ] 父代理接 FastAPI lifespan/web cancel/网关与 interrupted 历史投影；本片不宣称入口已替换。

## Context and Orientation

仓库 `C:/Users/Administrator/Documents/Codex/zhiming-v4`。复用 `repositories/postgres.py:queue_run/claim_run/renew_run/fail_run`、`agent/loop_policy.py:RunControl`、`models/transport.py:StreamingHTTP/close_on_cancel`、`application/agent_runtime.py:AgentRuntime`。不改变 v3 budget 或 schema，不改 root 正在适配的 Runtime/Loop/Finalizer/context。0005 已有 lane、runtime、thread_id、cancel_requested_at、deadline_at，无新迁移。

## Surprises & Discoveries

旧 web worker 全局单并发且 cancel 直接清租约，旧 queue/claim 没有通知或线程栅栏。新调度以 PG 租约为权威，通知只传 schema/run ID，无正文。当前历史投影只读 active 消息；interrupted 的 UI 展示要随调用方接线处理。

## Decision Log

2026-10-21：最小修改 queue/claim，新增 dispatcher 服务；不会把服务原型称为 FastAPI/飞书已切换。默认总并发 3，后台最多 1，至少 2 个容量留给交互。取消必须保留运行租约直至流已关闭和保存 partial，不能先清租约再假装停止。

2026-10-21：旧 `test_new_user_round_contains_only_old_thread_text_not_old_reasoning` 只跑 Loop 组件并手动记录回答，上一合成 run 仍 running。新 claim 栅栏正确拒绝同线程下一轮；因此该测试显式结束上一组件租约后继续原推理隔离断言，不修改生产串行规则或旧断言。真实本机 HTTP fixture 显式 HTTPTransport 避免环境代理，网络准入断言仅允许 127.0.0.1/http。

2026-10-21：root 的完整组件回归进一步识别 incognito reminder 与 cache epoch 测试同样让上一未执行 Runtime 的 run 留在 running。新增下一轮前显式 `component-fixture-completed` 结束，不伪造成功；并发 epoch 测试改为一个受信租约的两个不同 seq 预览同一代次，仍断言恰一方可提交缓存标记。保留全部原提醒、撤销、压缩、幂等断言。

## Plan of Work

先实现持久 claim/通知与取消，再以多 worker 和真实本机 HTTP 验证。主代理负责组装路由与 lifespan；不创建供应商真实端口或外部发信。

## Concrete Steps

用 Core Python 3.11、CORE_TEST_DSN 指向回环可丢弃 PG，清全部供应商凭据并关 tracing。目标 pytest 一进程，和 root 全量合计不超过四。Ruff 及 400/60 尺寸检查后冻结交 root 提交。

## Validation and Acceptance

对应 P3 R 类恢复、T 类时钟、Q 类中断：多个 worker claim 不能在同一线程并发；不同线程交互不被后台饿死；事务回滚不发通知；停止监听后轮询仍可取队列；20 秒续租被真实 PG 观察；真实 loopback HTTP 静默流在取消后 2 秒内退出，运行 cancelled、partial interrupted，无最终信封或发送动作。

## Idempotence and Recovery

queue operation_id 保留，通知可重复且不包含业务动作。过期租约按 cancel/deadline 状态恢复；已完成/取消不重跑。取消重复请求不创建额外助手消息。无迁移，回滚调度入口即可。

## Artifacts and Notes

证据预定 `docs/v4/evidence/P3/2026-10-21-m7-dispatcher.*`；没有经过真实检查的项目明确未验证。

## Interfaces and Dependencies

新增 Dispatcher(service)、DispatcherClaims、RunSignals、NotificationBridge、DispatcherCancellation；RuntimePort 保持原 execute 签名。只使用现有 psycopg/httpx/标准库。

## Outcomes & Retrospective

调度候选、真实 PG 栅栏与真实 loopback HTTP 静默取消已验证；38 项广目标及最终 30 项复验均绿。没有修改目标服务器或请求供应商。入口集成与 interrupted UI 投影仍未完成，普通 worker 配置必须一致。证据为 `docs/v4/evidence/P3/2026-10-21-m7-dispatcher.{md,json}`。

## 修订记录

- 2026-10-21 00:02 创建，记录调度边界与取消证明要求。
- 2026-10-21 00:15 更新真实 HTTP、PG 与组件 fixture 迁移证据，冻结交父代理提交。
