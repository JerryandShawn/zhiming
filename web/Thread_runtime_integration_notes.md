# 线程与补发接线核对（2026-10-21 08:42 +08:00）

只读本工作树已有 Git 对象；没有请求后端、运行模型或合并分支。固定核对对象为 `origin/v4/p3-agent-runtime@f49218bc5630501ec9339e2b63b7fc0c31eaf16c`。其 `docs/v4/contracts/thread_runtime_api_v1.md` 是实际 HTTP 本机候选契约；`mingjing_core/adapters/thread_routes.py`、`thread_events.py` 及 `web.py` 注册已有分支实现，不能再把当前缺口称为“契约完全未发布”。本前端分支尚未集成或适配，不代表服务已部署。

| 能力 | 已发布形状 | 前端后续接线要求 |
| --- | --- | --- |
| 线程 | POST/GET `/api/threads`，返回 opaque ID、mode/incognito/status | 用返回的 ID；本地无痕 ID 不冒充服务端资源；close 仅允许无痕 |
| 发消息 | POST `/api/threads/{id}/messages` → 202 JSON，包含 run/thread/runtime/run_url/events_url | 新增集中两步适配；不能把当前期待 POST 直接 SSE 的 executeV3 原样换路径 |
| 输入 | message/request_id/subject/conversation/case_ids/depth | 当前候选拒绝附件、tarot/report/selection 等；不得静默丢掉 images 或转普通长期消息 |
| 历史 | `{thread_id,items[]}`，条目含 role/content/at/run/status/incognito/case_ids | 独立公开投影与当前作用域；不直接当成旧 history 数组或 PrivacySession |
| 恢复 | GET `/api/runs/{id}/events`，Last-Event-ID / after_seq、15秒注释心跳 | 可复用严格 v1 解析；422无效游标应重读 run 状态，不无限按 unavailable 原游标重试 |
| 排队 | 持久 inbox_wait，Journal/Dispatcher 决定消费 | 不等同当前模拟 QueueAck；item/scope/images 回执仍需显式适配 |
| 取消 | POST `/api/runs/{id}/cancel`，GET run 状态为权威 | 请求停止不等于确认已停止；保留原有确认规则 |

默认 runtime 仍为 v3；普通 HTTP 正文不能启用 v4。后续验证只做集中适配和本机假服务，不改其他工作树、不合并、不访问服务器。

当前新版记忆/画像/提案/区话题/整理/联系设备/今日的 HTTP 契约仍缺，两条追踪 ref 均无 `api_*.md`。`origin/v4/integration@f756731ba8b40be54cf0842d7e590672490ac610` 尚无 contracts 目录；v3已有接口继续保留，不能冒充新版聚合端口。此处只反映本次已存在的本地追踪对象，没有外推远端最新状态。

事件 Schema 没有漂移：主线 Schema 与 `web/tests/fixtures/events_v1.schema.json` 的 Git blob 均为 `c84b89f3fb1c58fb0e11797122f9af3470629acd`，原始字节相同。

核对对象：thread 契约 `cd153b5e315eb89eefaea3b631821b64507c8af5`；router `34ee0c3d3ca6a466a9bce85419de1872805af21f`；SSE bridge `303dbfff8f27be4f58391e8a9514f7797e418c8f`。内容一致性不替代授权、部署或真实设备验收。
