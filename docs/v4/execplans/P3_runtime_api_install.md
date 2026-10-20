# P3：按可信配置安装线程与调度入口候选

本计划遵循 `.agent/PLANS.md`，时间为北京时间；入口改变只在显式注入 AgentRuntime 和受信 meter 后启用，默认 v3。

## Purpose / Big Picture

将已通过本机 PG 的 Runtime/Dispatcher 安装到服务与 HTTP 入口。用户可以创建线程、发消息、查看历史、关闭无痕、取消运行并读取冻结 events_v1 SSE。owner 的持久 settings.runtime 是唯一版本选择来源；客户端不能指定 runtime，未配置 v4 不允许悄悄转回旧模型。

## Progress

- [x] (2026-10-21 00:20) 核对旧 web/ConsultationService、线程服务、冻结 SSE 契约和 ThreadIngress 签名，与 M5 约定 _submit_validated 防递归。
- [x] (2026-10-21 00:43) RuntimeAssembly 与 submit/execute 路由，保持旧 v3 运行与 checkpoint 行为；重复请求固定首次 runtime。
- [x] (2026-10-21 00:43) 线程 API、run cancel/events 与 lifespan 调度切换；旧 worker 只取 v3，v4 显式安装后排队运行。
- [x] (2026-10-21 00:43) 最终 64 项真实隔离 PG / ScriptedPort 目标回归通过；旧 Core 兼容 32 项和 46 个 subtests 另通过；Ruff 与 400/60 检查通过。
- [x] (2026-10-21 00:49) 独立维护片接入 worker：monotonic 每60秒、有界50项、不重入，失败固定code可观察而不中断旧v3；维护与HTTP窄回归15项通过。
- [x] (2026-10-21 00:53) 独立自然无痕入口桥：v3持久前阻断私密意图/活动模式，v4旧请求固定原线程与全部独立来源；24项assembly边界回归通过。

## Context and Orientation

复用 `application/agent_runtime.py:AgentRuntime/RuntimeRouter`、`application/dispatcher.py:AgentDispatcher`、`application/thread_ingress.py:ThreadIngress`、`application/thread_queue.py:owner_runtime`、`application/threads.py:ThreadService`、`application/private_retention.py:retire_private_thread`、`agent/events.py:encode_sse`。不改 web 前端源码、模块线 SSE 核心或 root 独占的 Runtime/Context/私密服务。旧 v3 预算、牌阵、LangGraph checkpointer、owner 隔离、撤销与不重发契约不变。

## Surprises & Discoveries

ThreadIngress.queue 需要旧 submit 验证，因此旧函数提取为 _submit_validated 才能避免入口递归。v4 对附件、既有 tarot reading/report 等复杂输入尚未证明完整语义，必须明确拒绝；默认 v3 仍保留原路径。旧 worker 不可同时抢 v4；新 dispatcher 未配置或容量不足时，旧 v3 仍应能运行。

终态 SSE 回放可能与 Runtime 同时补发 final/ask_user，因此两者共用 run 行锁和实际提交信封核验，相同内容复用原 seq；不同内容视为损坏并拒绝。旧 cancel 处理函数缺少 Request 类型导致真实 HTTP 路由把 req 当查询参数（422），本片以最小类型修复并加入真实路由回归。

## Decision Log

2026-10-21：不自动构造任何 v4 provider。Service 显式注入 AgentRuntime，且 offline 仅允许 ScriptedPort+合成 meter；真实请求仍由既有守卫检查。保持持久 owner runtime 默认 v3，不自动写配置。新 SSE HTTP 适配器严格复用冻结字段与编码，先用 PG 游标回放/轮询，不宣称模块线合并、完整 hub 合并器或生产启用。

2026-10-21：已关闭的私密实体沿用现有 EvidenceError→422，跨 owner 资源仍为 ScopeError→403；新测试最初假定关闭也为403，核对既有领域和HTTP映射后改为明确422，保留关闭后不得读取正文的断言。没有改旧错误处理去迁就新测试。

## Plan of Work

先做可信 assembly/服务路由，再用独立 adapter 挂新 API，最后最小修改旧 web worker/lifespan。所有入口逐项标记已验与未验；无供应商调用、服务器访问、飞书发送或分支合并。

## Concrete Steps

使用本机隔离 PG 和显式 ScriptedPort、清供应商凭据、禁外部 HTTP。目标 pytest 最多一进程，Ruff E,F,I,B,UP,SIM 与 400/60 限制后冻结给 root 提交。旧大文件只最小改动，不整体格式化。

## Validation and Acceptance

默认 v3 仍按旧 runtime 执行。显式 owner.runtime=v4+注入依赖可通过 HTTP 排队，lifespan dispatcher 真正产生一个 core4；未知/缺 meter、客户端 runtime 字段、未覆盖复杂输入在模型前拒绝。不同 owner 无法读取线程/run事件；无痕关闭清空临时正文。SSE Last-Event-ID 不重放旧 seq，事件符合 events_v1，无 reasoning 或 lease。

## Idempotence and Recovery

复用 request_id 和 ThreadIngress 不变式；运行时固定于首次入队，不随后续设置切换。新 API 关闭以 mutation_request 保留最小回执。SSE 为读取适配，取消使用持久 cancel_requested_at。回滚是恢复旧入口装配；没有数据库迁移。

## Artifacts and Notes

证据 `docs/v4/evidence/P3/2026-10-21-runtime-api.*`；契约 `docs/v4/contracts/thread_runtime_api_v1.md`。

## Interfaces and Dependencies

新增 `application/runtime_assembly.py`、`adapters/thread_routes.py` 和必要独立事件读取 adapter；服务新增 agent_runtime 显式参数、内部 _submit_validated。新 API 不拥有模块线的 SSE 核心。

## Outcomes & Retrospective

本机候选安装已通过真实隔离 PostgreSQL 和合成模型验证，覆盖线程人生/无痕、关闭、默认 v3、显式 v4、队列隔离、取消租约、冻结 SSE 游标回放和并发终态幂等。未部署、未发真实模型或飞书请求；复杂附件/旧牌阵/报告输入及模块线 SSE 核心合并未验，不能标记完整产品可启用。后续独立片已接入 root PrivacyMaintenance 的60秒维护，证据见 `2026-10-21-privacy-maintenance-hook.md`。

## 修订记录

- 2026-10-21 00:20 创建，记录候选装配与兼容边界。
- 2026-10-21 00:43 冻结本机安装候选，补最终目标回归、旧 Core 兼容和公开事件并发核验结果。
- 2026-10-21 00:49 独立补入有界、失败可观察的60秒保留维护 hook 和 owner/running/core3 真实PG边界。
- 2026-10-21 00:53 接入 M5 的受信隐私路由检查，保留旧非法输入错误及私密/多来源幂等身份；未改 Loop、Context 或工具策略。
