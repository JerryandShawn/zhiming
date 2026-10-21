# P3 M6：长期线程的真实运行闭环

本 ExecPlan 遵循 `.agent/PLANS.md`，时间均为北京时间。

## Purpose / Big Picture

把已有 PostgreSQL 快照、模型/工具循环、发送前上下文计量、提交闸门连成可独立注入的 RuntimePort。模型只由显式端口提供，夜间验证全部使用 ScriptedPort；真实模型、飞书和服务器请求为零。用户可观察到已提交的 core4 信封、递增事件、一次评审改写和来源撤销后的至多一次干净重生。

## Progress

- [x] (2026-10-20 23:51) 正式 P1/P2/P4/P8 提示词与增补 H 固定版本和原文 SHA；请求账本、分角色 epoch 与原计量回传组件完成。
- [x] (2026-10-20 23:57) 长期线程候选 RuntimePort 接入、真实隔离 PG 端到端测试及受信评审证明。
- [x] (2026-10-20 23:57) 危机模板、20 秒无正文与供应商失败替身；快照/循环/提交目标回归，130 passed in 18.65s；Ruff 与尺寸限制通过。
- [ ] 父代理接路由、全部旧读取端、无痕线程及网关；本切片不宣称这些已完成。

## Context and Orientation

仓库为 `C:/Users/Administrator/Documents/Codex/zhiming-v4`。复用 `application/agent_snapshots.py:AgentSnapshotStore.load_or_build`、`agent/loop_cycle.py:LoopCycle.execute`、`application/agent_finalization.py:AgentFinalizer.finalize`、`application/context_epochs.py:ContextEpochService.mark_sent`、`application/context_usage.py:ContextUsageService.record`、`repositories/postgres.py:prepare_retry`。禁止改变 owner 隔离、精确版本、撤销账本、core4/events v1 Schema、同一写操作幂等和禁止返回推理正文的契约。初始仅支持人生线程，无痕由独立切片接入。

## Surprises & Discoveries

隐私失效会清空运行请求和租约，不能拿旧快照直接重试。重生要求原执行租约摘要、相关的新撤销、仍有效的当前用户消息，并重建新 epoch；复杂附件输入明确拒绝自动复活。core4 的公开 meta 冻结，提示词来源和程序模板标记放在私有 run.usage.agent_runtime。

## Decision Log

2026-10-20：独立评审只收用户问题、有效资料摘要、真实收据和初稿，不收主模型推理。通过与改写必须绑定真实完成的 critic/revision journal 行，普通 passed 字典仍拒绝。请求原件保存为附来源谱系的私有 runtime_step，确保恢复和实际 usage 使用原计量；没有新依赖、网络或迁移。

## Plan of Work

先连长期线程入口和事件，再以隔离 PG 验证读写、恢复、一次改写和撤销。父代理统一提交推送，路由与读取端由父代理后续合入；不改独占前端、命理或模块线文件。

## Concrete Steps

在仓库根目录使用 Core Python 3.11，配置本机 `CORE_TEST_DSN`，清供应商凭据并关闭 tracing 后运行目标 pytest。新增与修改 Python 文件执行 Ruff E,F,I,B,UP,SIM 和 format；不得使用合成计量声称 K3 实际准确度。

## Validation and Acceptance

对应 P3 的 R07、Q 类危机和 T 类上下文场景：真实 PG 的已提交 assistant 只出现一次；完成步骤恢复不增加物理模型请求；critic revise 至多增加一次正文请求；源撤销后旧正文及推理不再进入下一请求；12356/120/110 模板无需外部模型。公开事件与信封继续通过冻结 v1 契约。

## Idempotence and Recovery

每步使用 Journal 稳定序号和 operation_id；请求账本不可覆盖，完成请求重放。只有相关来源撤销允许一次 clean epoch，当前用户原话撤回不重生。无迁移；回滚为移除候选 Runtime 路由。未经用户允许不构造真实模型端口。

## Artifacts and Notes

目标证据放 `docs/v4/evidence/P3/2026-10-21-m6-life-runtime.*`；未跑过的验收保持未验证。

## Interfaces and Dependencies

候选入口 `AgentRuntime.execute(service, owner, run_id, lease_token, emit=None)`，emit 接收经 v1 验证的单个事件字典。ModelPort、TokenMeter、可选 critic port 均显式注入。新增私有 step 类型 agent_model_request 和 agent_review；私密会话由父代理保留策略清除，普通日志保留 worker 仍属后续。

## Outcomes & Retrospective

长期线程候选已通过 130 项目标测试；提交证明与原计量恢复都经过真实 PG。P3 M6 整阶段仍未完成：主路由、无痕生命周期、全部读取端由父代理和对应切片接续。真实供应商、真实质量、HTTP 取消均未验证。证据为 `docs/v4/evidence/P3/2026-10-21-m6-life-runtime.{md,json}`。

## 修订记录

- 2026-10-20 23:51 创建，记录长期线程边界及真实 PG 验证计划。
- 2026-10-20 23:57 更新候选闭环验证与未覆盖范围，准备父代理小提交。
