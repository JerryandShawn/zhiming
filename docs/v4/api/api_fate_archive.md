# 命理档案（C / P8）

> 状态：C 尚未合入 `v4/release-next`（命理线在 `v4/batch2-p8-finish` 收口中）。以下按该分支当前代码写，C 合入后新主线复核并更新本文件。

## 1. 现有命盘接口（已在 release-next）
- `GET /api/chart?system=…&date=…`、`GET /api/chart_ziwei`、`GET /api/chart_astro`：按已确认出生资料排盘；缺资料时返回中文提示，前端引导到出生资料确认。
- 出生资料：`GET /api/subjects/self/profile`、`POST /api/subjects/self/profile/confirm`（见 [记忆](api_memory.md) 第 5 节）。

## 2. P8 新增
- `GET /api/subjects/self/profile/requirements?conversation_id=shared` → 当前对话需要用户补充/确认的出生资料卡片（`application/p8_profile_confirmation.py: profile_confirmation_cards`）。保存仍走 `POST /api/subjects/self/profile/confirm`。单窗口下 `conversation_id` 固定 `shared`。
- 四个命理工具、命盘技能和边界提醒在对话运行里触发，结果经运行事件与助手回答返回，不新增前端接口。
- “关于我”第 7 节命理档案：作为画像条目出现在 `GET /api/memory2/profile` 的 `section == 7` 行里；无痕模式下不保存。

## 3. 展示约束（设计规范）
正文先给易懂回答和现实依据；专业盘面细节放在最后可展开的附录；区分用户事实、偏好、未知项与象征解释。
