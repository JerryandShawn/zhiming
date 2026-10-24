# P3 Runtime / 线程 HTTP 安装候选证据

时间：2026-10-21 00:43 北京时间。环境：Windows、本机隔离 PostgreSQL 15（loopback 55480）；不是 Linux 或服务器验证。仅 ScriptedPort / 合成计量；清理供应商凭据并关闭追踪，禁止外部 HTTP，TestClient 的进程内传输除外。没有真实模型、飞书发送、服务器访问或合并。

## 本片行为

ConsultationService 新增显式 agent_runtime 安装；默认 v3 保持原 LangGraph 实例和 checkpointer。持久 owner settings.runtime 决定首次排队版本，重复 operation_id 固定原 runtime。v4 缺 ModelPort / 受信计量、容量不足或未覆盖复杂输入时在写入原话前拒绝；旧 v3 可继续运行。lifespan 仅在依赖有效时启动 AgentDispatcher，旧 worker 只取 v3。

新增线程 create/list/history/message/close 和 events_v1 HTTP 回放接口；旧 chat 在显式 v4 下接新事件格式。run cancel 写持久取消标记，活跃 lease 保留到 worker 停止。历史按 owner/subject/thread 授权投影，撤销原话不重建；关闭无痕清正文。SSE Last-Event-ID 排除旧序号，不返回 reasoning/lease；断线不等于业务取消。契约见 `docs/v4/contracts/thread_runtime_api_v1.md`。

Runtime 与订阅恢复同时发 final / ask_user 时，实际 run 行锁保护；只有与实际成功信封完全相符的终态能写入，相同内容复用原 seq，不同内容或重复行视为损坏拒绝。error 仅为固定安全文案，按 attempts/epoch/status 幂等，重试保留事件序列。并发真实 PG 回归覆盖 ask/final 单份、损坏拒绝及重试错误分代。

持久 inbox_wait 的恢复接入 Dispatcher 和旧队列维护，未采用的来源在父轮终止后恢复为 queued；已采用仍须 Journal 证明。M5 原生双来源入队/飞书假发送由该线独立证据覆盖，本片最终回归也包含其当前版本。

## 验证

- 最终目标：`test_runtime_assembly_pg.py`、`test_thread_routes_pg.py`、`test_run_event_replay_pg.py`、三份 dispatcher PG/HTTP/handoff、`test_thread_inbox_pg.py`、`test_feishu_ingress_pg.py`、`test_result_readers_pg.py`：**64 passed，23.47 秒**。
- 旧 Core 兼容：`test_core_runtime.py`、`test_core_4288_single_tarot_denials.py` 加 assembly/routes：**32 passed，46 subtests passed，39.78 秒**。
- API/events 最后修正的独立复验：**10 passed，5.26 秒**。
- Ruff E/F/I/B/UP/SIM（line-length=120）与 format：**12 文件通过**。新文件 ≤400 行、函数 ≤60 行。
- 唯一警告：既有 Starlette TestClient 使用 anyio.abc.BlockingPortal 的弃用警告。无产品警告忽略配置。

## 界限与待续

这是本机可测试的安装候选，不是 stage/生产启用或真实模型验收。没有安装真实 provider，K3 精确计量/P1b 物理请求守卫/人工开始门要由各自证据证明。复杂附件、旧 tarot reading、report 等 v4 输入明确拒绝。HTTP SSE 是 PG 游标回放/轮询适配器，不冒充模块线 hub/合并器/清理 worker。PrivacyMaintenance 的节流 hook 尚未接入本片；root 的独立私密保留组件另有目标测试。

没有数据库迁移；回退可恢复旧入口装配，已有运行仍按持久 runtime 判断，不能把 v4 静默送旧模型。PR 保持草稿，提交与推送由主代理完成。
