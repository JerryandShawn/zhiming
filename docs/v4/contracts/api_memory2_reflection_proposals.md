# 接口：空闲反思的待确认记忆（确认 / 忽略 / 撤销确认）

适用分支：`v4/mem2-reflection-real`（下一版 A）。界面由前端线在新前端 `web/` 里做。所有接口都用现有认证（`X-Token`），owner 只来自认证，请求体里不接受 owner。

## 背景

开关 `MEMORY_REFLECTION_MODEL=real` 时，线程空闲 10 分钟后会整理一次记忆（不设每日次数上限，只受中央守卫后台 20% 份额约束，不占对话 60% 预留）：
- 用户明确说过、非敏感的偏好/约束/背景/目标：**直接写入**长期记忆（事实带 `origin=memory2_reflection`、`auto_written=true`），用现有"撤销这条记忆"撤销。
- 推断项、事件、敏感/第三人项：生成**待确认提案**，用户在界面里确认或忽略。

"已开记忆"的口径（大脑 11-09 同意的暂行做法）：owner 设置 `auto_save_low_sensitivity` 不为 `false`。关掉它，反思既不写入也不生成提案。

## 1. 列出待确认的反思提案

`GET /api/memory2/proposals?subject_id=self`

响应 200：

```json
{"items": [{
  "id": "proposal_…",
  "revision": 1,
  "kind": "preference | constraint | background | goal | event | concern",
  "summary": "可能偏好户外",
  "quote": "周末常去山里",
  "message_id": "msg_…",
  "inferred": true,
  "sensitive": false,
  "can_remember_category": false
}]}
```

- 只列来源原话仍然有效的提案；原话被删除或撤销后自动消失。最多 50 条。
- `quote` 是用户自己的原话片段；`message_id` 可用现有接口跳到原消息。
- `sensitive=true` 的条目同时可以勾选"以后这类都记"（`can_remember_category=true`）；非敏感条目不能勾选。
- 未认证 401/403；别人的数据看不到（返回空列表或 404）。

## 2. 确认 / 忽略 / 撤销确认（沿用现有路由，不新增）

| 动作 | 路由 | 请求体 |
|---|---|---|
| 确认 | `POST /api/memory2/proposals/{id}/confirm` | `{"request_id": "...", "expected_revision": 1, "remember_category": false}` |
| 忽略 | `POST /api/memory2/proposals/{id}/ignore` | `{"request_id": "...", "expected_revision": 1}` |
| 撤销确认 | `POST /api/memory2/proposals/{id}/undo` | `{"request_id": "...", "expected_revision": <确认后的 revision>}` |

- `request_id`：前端为每次点击生成一次性的稳定 id（`^[A-Za-z0-9][A-Za-z0-9_.:-]*$`，≤180）；同一 id 重放返回同一结果，不会重复写入；同一 id 不能用于另一个动作。
- `expected_revision`：取列表里的 `revision`；版本不对返回错误，前端提示"已变化，请刷新"。
- 确认成功：写入一条事实（来源 = 原话 + 这次点击），提案变为 `accepted`，从列表消失。撤销确认后事实退休，提案回到待确认。
- 非敏感条目带 `remember_category=true` 会被拒绝（4xx），不会改任何设置。
- 事件条目确认时由现有日期核实逻辑解析绝对日期；原话里没有可核实日期的事件确认会失败（4xx），只能忽略。
- 他人 id：404，且不会产生任何写入。

## 3. 撤销与隐私

- 提案和确认后的事实都记录来源消息；用户删除原消息时，派生事实一并删除并进入撤销账，待确认提案被删除。
- 列表与回执都不含模型输出以外的私人正文；日志不记正文。

## 实现位置

- 列表：`mingjing_core/application/memory2_reflection_review.py`，路由在 `mingjing_core/adapters/memory2_routes.py`。
- 确认放行：`memory2_proposals.reflection_reviewable`（`origin=memory2_reflection` 且 `sensitivity=normal`）；其他非敏感提案仍然不能确认。
- 测试：`tests/v4/agent/test_memory2_reflection_review_pg.py`。
