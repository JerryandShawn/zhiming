# P3 R7：旧网页的记忆回执兼容

2026-10-23 21:22 +08:00。依据指令板 v4、35 号 R7；只改旧 Web 读取适配层，不接入 P4，不改网页静态文件。尚未提交，由主线统一提交。

## 结果与边界

旧 `/api/chat/{id}` 和 `/api/history` 为已校验 core4 结果增加 `memory_receipts` 兼容投影；仅包含 fact、note、proposal，避免把事项、提醒等成功操作显示成长期记忆。所有原字段和状态逐项保留。敏感提议保持 `pending_confirmation`，用旧网页已有的边界提示区显示“敏感信息需你确认后才会保存；目前未写入长期记忆。”，不生成已保存提示。

冻结的 `receipts`、信封 Schema、数据库结果、`read_result`、`history_window`、`/api/runs` 均不改；core3 原回执与提示照旧。没有迁移、回填或后台写入。

## Decision Log：旧断言保护什么

原 strict xfail 用真实 PG、回环 HTTP、原网页 JavaScript 与真实 DOM 验证：当前回答和历史回答都出现且各只出现一个真实保存回执，即 `[1, 1]`。本次移除 xfail 与只用于标记已知缺口的异常类，保留该精确断言。原 v3→v4→v3、单次 POST、恢复 GET、一个事实、脚本模型调用次数、三条历史、运行版本与 owner 隔离断言均保留。

读取端旧断言从“整个 Web meta 等于冻结信封”迁移为“剥离唯一新增兼容字段后仍严格等于原信封”；同时断言兼容字段内容。领域历史和 `/api/runs` 的完整信封相等断言保持不变。原因是用户明确裁定 R7 增加读取投影，而非修改冻结契约。

## 定向检查

使用 `run_narrow_safe.py`，目标为 `test_legacy_dom_runtime_pg.py`、`test_result_readers_pg.py`、`test_legacy_web_result.py`；隔离 PG 15、脚本模型、Node/JSDOM，显式 `TZ=Asia/Tokyo`。

- 首次两项 DOM 目标在 PG 夹具阶段超时：2 errors/10.90s，未执行业务断言。私有记录：`private/safe-narrow-ef3f2ed7926d42b3a0ff707d5129f33d/`。
- 主线恢复原本机隔离 PG 后，相关链 13 passed、1 failed、1 既有 Starlette 弃用警告/24.85s：保存 DOM 已满足 `[1,1]`，敏感提议当前/历史 DOM 均显示待确认且保存节点为 0；该新测试最后的辅助 httpx 回读受环境代理影响，未取得 JSON。记录：`private/safe-narrow-0817e37f4a164932b55000a98e3fd4bd/`。
- 只将该新辅助 HTTP 客户端设为 `trust_env=False`，隔绝系统代理；保留全部原断言。该单例 1 passed/3.14s，确认真实 proposal=1、fact=0、两步脚本调用，以及冻结结果没有 `memory_receipts`/`caveats`。记录：`private/safe-narrow-caa9216bb943481b9137ec6a3c6d09c2/`。未把分开两次执行冒充一次完整绿验。
- 新 helper 和三份目标测试通过 Ruff E/F/I/B/UP/SIM；新增与修改的目标测试通过 120 列格式检查。

真实模型调用、服务器访问、真实飞书发送均为 0。未跑完整回归，未验证线上浏览器或部署，不宣称整个 P3 验收完成。
