# 记忆、画像确认与撤销

真相源：`adapters/memory2_routes.py`、`application/memory2_proposal_listing.py`、`memory2_web_actions.py`、`memory2_profile_web.py`、`adapters/web.py`。

## 1. 记忆事实（已生效）
- `GET /api/memories?subject_id=self` → 事实数组（含已停用的），每条有 `id`、`revision`、`status`、`text`、`kind`、`source_refs`…；`GET /api/memories/{id}/source`、`/audit` 查来源和审计。
- 撤销/删除一条（包括 A 空闲反思**自动写入**的事实）：`DELETE /api/memories/{id}?scope=fact&expected_revision=<n>`，或体 `{"scope","expected_revision","request_id"}`。
- 停用：`PATCH /api/memories/{id}` 体 `{"status":"hidden","expected_revision","request_id"}`；更正：体 `{"text","expected_revision","request_id"}`。

## 2. 待确认提案（新增列表）
`GET /api/memory2/proposals?subject_id=self` → 只列 `status=pending` 且未撤销的提案：
```json
[{"id","revision","status","proposal_type","origin","kind","summary","sensitivity","categories",
  "inferred","needs_confirmation_reason","created_at","quotes":["用户原话片段"],"confirmable":true}]
```
- `quotes` 只是用户自己的原话片段，不含模型文本；渲染时按纯文本处理。
- `confirmable=false` 的提案（非敏感推断/事件，`needs_confirmation_reason="inferred_or_event"`）目前后端**不接受确认**，只能忽略——待大脑裁定（模块线日报 11-09 第 2 条）。前端请只在 `confirmable=true` 时显示“确认”。
- 动作（均需 `{"subject_id","expected_revision","request_id"}`）：
  - 确认 `POST /api/memory2/proposals/{id}/confirm`，可加 `remember_category`（同类以后自动保存），冲突提案必须带 `choice: "old"|"new"`；
  - 忽略 `POST /api/memory2/proposals/{id}/ignore`；
  - 撤销确认 `POST /api/memory2/proposals/{id}/undo`；
  - 撤销一次自动变更 `POST /api/memory2/changes/{id}/undo`，加 `change_type: slot|confirmed_slot|merge|archive`。
- 返回统一回执（`public_receipt`），带 `write_status`。对话中的提案也会经运行事件带 `proposal_id` 出现，可用同一组动作。

## 3. 关于我（画像，新增列表）
- `GET /api/memory2/profile?subject_id=self` → 按 `section` 排序的数组，每条与单条视图完全一致：`{"id","revision","section","text","confirmed_by_user"}`。第 7 节为命理档案（见 [命理档案](api_fate_archive.md)）。
- 单条 `GET /api/memory2/profile/{id}`；编辑 `POST …/{id}/edit` 体加 `text`（≤800 字，不能含密钥类内容）；删除 `POST …/{id}/delete`。均需 `subject_id/expected_revision/request_id`。

## 4. 记忆开关
“已开记忆”目前即设置 `auto_save_low_sensitivity`（`PATCH /api/state/settings`，体 `{"settings":{…},"expected_revision","request_id"}`）。关掉后 A 的空闲反思也不运行。

## 5. 出生资料
`GET /api/subjects/self/profile`、`POST /api/subjects/self/profile/confirm`（必须 `confirmed: true` + `profile` + `request_id`）。
