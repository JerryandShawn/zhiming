# 线程、运行装配与 HTTP 事件适配契约 v1

本文件描述主线 P3 的**本机验证候选**。不是生产启用声明，不包含真实供应商质量、服务器部署或飞书真实发送验收。公开事件数据和 SSE 编码唯一来源仍是 `events_v1.md`、`events_v1.schema.json`，本片不改这些字段。

## 安装与可信选择

`ConsultationService(..., agent_runtime=AgentRuntime(...))` 显式注入 v4。AgentRuntime 的 ModelPort、TokenMeter、可选 critic 都由可信程序传入；服务不会从 HTTP 正文构造 provider。`offline=True` 只允许明确的 ScriptedPort 和 provider=scripted/live_admissible=False 的合成计量；非 offline 依赖必须声明已核验计量，发送前仍执行 Runtime 的原有计量闸门。此声明不等于 K3 tokenizer 或 framing 已实测。

owner 的持久 `settings.runtime` 仅为 `v3|v4`，省略时 v3。普通设置 API 不开放修改此键，线程或消息正文也不能指定 runtime/lane。首次排队固定 runtime/thread/lane，重复 request_id 沿用原运行，即使 owner 设置后来变化。原请求撤销、内容不同或跨线程复用 ID 必须拒绝，不能重建私密正文。

默认 v3 保持原 LangGraph 实例、checkpointer、预算与旧 worker。v4 显式安装后，lifespan 启动 AgentDispatcher；旧 worker 只回收/取 v3 队列，不抢 v4。新 dispatcher 默认容量 3，交互2/后台1；显式旧容量1或无效 v4 依赖不会关闭 v3，v4 请求则明确拒绝。各进程的并发配置必须一致。

v4 目前安装普通 chat 的人生/无痕线程及已验证工具语义。附件、既有 tarot reading、report、selection、parent_run 等复杂输入经公共 submit 明确拒绝，默认 v3 原路径仍在。旧网页牌阵入口在 v4 下先拒绝再建 reading，原牌阵保留；旧 chat 遇到 incognito/thread_id 提示时拒绝，要求走线程入口，避免私密提示被悄悄当成人生对话。

## 线程资源

所有端点沿用现有 `X-Token` 身份认证及 owner/subject 授权，默认 `subject_id=self`。资源 ID 使用程序返回的 opaque ID。

| 方法与路径 | 输入 | 输出 / 行为 |
| --- | --- | --- |
| POST `/api/threads` | `{request_id,subject_id?,incognito?:false}` | `{id,subject_id,mode,incognito,expires_at,status}`；人生线程固定 `life:<subject>`；无痕需要已安装 v4 |
| GET `/api/threads?subject_id=self` | 无正文 | 当前 owner 的线程元数据，不返回缓存或原话 |
| GET `/api/threads/{id}/messages?subject_id=self&limit=80` | limit=1..1000 | `{thread_id,items[]}`；只返回该 owner/人物/线程；含 interrupted 回答，不把它用于模型事实 |
| POST `/api/threads/{id}/messages` | `{request_id,message,subject_id?,conversation_id?,case_ids?:[],depth?:standard}` | 202 `{run_id,thread_id,status,runtime,run_url,events_url?}`；深度 standard/deep；不接受多余身份/运行时字段 |
| POST `/api/threads/{id}/close` | `{request_id,subject_id?}` | 幂等 `{id,status:closed,deleted:true}`；只允许无痕，立即清临时正文和相关 run/event 私密载荷 |

消息 request_id 为 1–200 个 ASCII 字母、数字、`_ . : -`，首字符字母或数字，与冻结 core4 标识一致。message 为 1–16000 字。case_ids 最多8个，无痕不能携带长期事项。每项历史只投影 `id,role,content,at,thread_id,run_id,status,incognito,case_ids`，不返回模型推理或 token。

运行中的后续消息先成为持久 inbox_wait 备用轮次。模型实际采用的来源有 Journal 证明才会消费该轮次；父轮结束/失租时，Dispatcher 和旧 worker 的有界维护将未采用消息恢复为 queued，不因一次通知丢失而丢消息。

跨 owner 资源为403；已关闭私密资源沿用既有 EvidenceError→422；结构错误、未配置 v4 或未覆盖输入为422。验证错误不回显私人正文。人生线程不可通过 close 删除。

## 取消与 SSE

`POST /api/runs/{run_id}/cancel`（兼容 `/api/chat/{run_id}/cancel`）对 v4 写 cancel_requested_at 并通知。活跃租约保留到流关闭和 partial 保存，不能提前清租约假装停止；已生成文本存 status=interrupted，取消不产生已验证最终信封。v3 的旧取消语义保留。

`GET /api/runs/{run_id}/events` 仅供 v4，接受 `Last-Event-ID` 或 `after_seq`（两者同时指定须一致）。响应为 `text/event-stream`，逐条调用冻结 encode_sse，`id=seq`、`event=<type>`、`data=<payload>`。序号按 run 递增，客户端以 run_id/seq 去重；15秒心跳为 `: ping`，心跳不占序号。无效或已不可用游标为422，客户端重新读取 run 状态。恢复重连应携带最后已处理 seq，避免把上一失败尝试的历史 error 当成本次新状态。

本片是 PostgreSQL 游标回放/150ms 轮询 HTTP 适配器，不拥有模块线的 SSE hub、文本合并器或24小时清理 worker。消费时跳过被撤销清空的旧事件，绝不重建旧正文。终态缺事件时可恢复公开 final 或固定 error；这是幂等的操作事件写入，不修改业务答案。final 必须匹配已提交 core4，ask_user 必须匹配最终卡片；订阅恢复与运行时并发时同 run 行锁复用原 seq，不覆盖不同终稿。错误事件按实际 attempts/epoch/status 幂等，重试后保留历史 seq 并生成本次终止事件。

旧 `/api/chat` 在 owner 显式 v4 且 dispatcher 已启动时返回同一 events_v1 SSE；默认 v3 保持原事件格式。`GET /api/runs/{id}` 仍为持久状态权威。HTTP 断开不会取消已排队业务，用户停止需显式 cancel。

## 未覆盖和集成边界

未安装到 stage/生产，未构造或调用真实 v4 provider。真实 K3 计量、人工开始门、P1b物理入口统一守卫和全部复杂输入仍需各自证据。这里没有合并模块线 SSE 核心、没有修改 `web/**` 前端，也没有发真实飞书。无痕临时历史和事件可见性已在本机隔离 PG 验证；跨线程对话质量、真实 UI 与部署仍未验证。
