# P3 自然无痕的公共 submit 最小桥

2026-10-21 00:53 北京时间。本机隔离 PostgreSQL15，合成数据和显式 ScriptedPort；真实模型、飞书发送、服务器连接均为0。此片依赖 M5 的 PrivacyModeService/ThreadIngress，不修改其规则或 root 的 Loop/Context/工具。

`runtime_assembly.route_submit` 在进入旧 v3 submit 前调用受信 `assert_legacy_safe`，直接进入/退出无痕的原话，以及同一会话尚在自动无痕中的后续消息，均在原话或新 run 落盘前拒绝。不同会话保持原 v3；旧 None/空/空白仍使用原 MissingInput 错误契约，不用隐私错误替代普通输入验证。

v4 既有 operation_id 重放从已保存 run 获取原 thread_id 及 source_message_ids，在真实来源仍有效、同 owner/人物/线程且正文一致时沿用；不再强制创建人生线程或拒绝已持久私密请求。合并原话仍是独立来源与 segments，不拼成一条伪引文。显式授权来源同样沿其真实线程排队。源已关闭、撤销、到期或变更时拒绝，绝不从请求正文重建旧私密来源。首次自然路由由 M5 在持久前选线程，调用者应采用真实返回 run.thread_id。

最终 `test_runtime_privacy_routes_pg.py` + 原 `test_runtime_assembly_pg.py`：**24 passed，8.06秒**。新11项含v3三种指令零原话/零运行、三种非法旧输入错误兼容、私密请求在owner改v3后重放、活动私密阻断/独立会话、显式私密来源、关闭拒绝重建、两原话重放。较宽 assembly/线程HTTP/飞书合成入口检查 **36 passed，13.60秒**（最后补入非法旧输入三个断言前）；唯一既有 Starlette/AnyIO 弃用警告。两源码/测试文件 Ruff120/format通过。

自然语言结束无痕只退出后续自动路由；旧私密正文继续服从既有24小时保留。显式close API立即清理。这个差异由 M5 核对正式设计并另有证据；本片不单独宣称完整自然语言模式、真实UI、跨进程负载或部署验收。无新迁移；恢复旧装配可撤回该最小桥，不能把已有私密run当成v3运行。
