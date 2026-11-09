# 对话接口（一个窗口聊到底）

真相源：`mingjing_core/adapters/thread_routes.py`、`thread_events.py`、`agent/event_contracts.py`、`memory/history.py`、`adapters/web.py`。

## 1. 时间线（只读）
`GET /api/history?session=shared&subject_id=self&limit=60&before=<cursor>&q=<关键词>`
- `session` 省略或为 `shared` 时**不按对话过滤**：所有旧 `conversation_id`（含飞书原话）合并成一条时间线，数据不动。PG 测试 `tests/v4/agent/test_single_window_web_pg.py`。
- 返回数组，按时间升序；每行至少有 `role`（`user`/`assistant`）、`content`、`at`、`turn_id`、`source`（`web`/`feishu`…）、`cursor`。用户行若已关联运行，还有 `run_id`、`status`、`meta.meta.core_run`；助手行有 `meta`（结构化结果，经 `legacy_web_result` 投影）。
- 翻页：取当前最早一行的 `cursor` 作为下一次 `before`。`limit` 上限 500。
- 无痕消息和无痕运行**不会**出现在时间线里（隐私规则）。

## 2. 发送（v4）
`POST /api/threads/life:self/messages`
```json
{"request_id": "<稳定 id>", "message": "…", "subject_id": "self", "conversation_id": "shared",
 "case_ids": [], "depth": "standard", "draw_id": null}
```
- 严格字段（多一个字段即 422）。`request_id` 只允许 `[A-Za-z0-9][A-Za-z0-9_.:-]*`。`conversation_id` 固定 `shared`。
- 202 返回 `{"run_id","thread_id","status","runtime","run_url","events_url"}`。
- 线程由后端决定：每个人物一条 `life:<subject>`；用户原话里说“开个无痕/结束无痕”时后端自动转到/转出 `incognito:*` 线程（24 小时），前端不传线程提示。`thread_id` 可能与请求路径不同，以返回为准。
- 线程列表 `GET /api/threads`、无痕关闭 `POST /api/threads/{id}/close` 仍在，但单窗口界面不需要。

## 3. 运行事件（SSE）
`GET /api/runs/{run_id}/events?after_seq=<n>`（或请求头 `Last-Event-ID`）
- `text/event-stream`，每 15 秒心跳；运行结束后流关闭。事件类型、字段见 `agent/event_contracts.py`（`phase`：thinking/tool/writing/reviewing；记忆回执 `write_status`：saved/updated/pending_confirm/undone/rejected，带 `fact_id` 或 `proposal_id`）。
- 断线重连带上最后的 `id` 作为 `Last-Event-ID`。

## 4. 运行控制
| 动作 | 接口 |
|---|---|
| 查询 | `GET /api/runs/{id}` |
| 停止 | `POST /api/runs/{id}/cancel` |
| 重试 | `POST /api/runs/{id}/retry`，体 `{"request_id": "retry:<operation_id>"}` |
| 澄清后继续 | `POST /api/runs/{id}/resume`，体 `{"message_id","message","interrupt_id","state_version"}` |

## 5. 不再使用
- `POST /api/sessions`、会话切换：单窗口界面不得调用。`GET /api/sessions` 只为旧页保留，且已过滤无痕状态行。
- 旧 `/api/chat`（v3 SSE）仍给旧页 `/legacy/` 用；新前端走第 2 节。

## 已知风险
无痕状态按 `conversation_id` 分开记录：用户若在旧页某条非 shared 对话里 24 小时内开了无痕，切到新页（shared）后不在无痕中。上线说明中告知。
