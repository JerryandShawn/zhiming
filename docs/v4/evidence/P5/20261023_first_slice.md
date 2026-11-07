# P5 新核心接入首片证据

记录时间：2026-10-23 22:54 +08:00。真实模型请求 0；仅本机隔离 PG15.19 的 core_test_p2，每例创建并清理独立测试 schema。测试子进程禁用追踪、移除供应商密钥，集成夹具禁止 HTTP。没有服务器、stage、生产或飞书访问。

## 已验证行为

原始说话时间参与重要度：偏好每 180 天减半，目标与约束不衰减。重建索引/导入的创建时间不会把旧事实变新。memory_search 和上下文 L4 都在来源授权/撤销检查后排序；陈旧来源、撤销事实不能靠高分重新出现。L4 普通候选最多 50 条消息加 50 条事实，既有时间筛选优先级保留。未启用向量模型，工具明确返回 vector_available=false。

已有 owner health 类授权时，真实 memory_write 保存健康事实并安全重放；未经授权、畸形类别配置、仅授权其它类别或第三人健康仍待确认。用户 opt-out 优先。补上“失眠”和 M08“复诊”的敏感识别。

## 检查结果

组合一：pytest `tests/v4/memory2`、`test_memory2_retrieval_pg.py`、`test_memory2_categories_pg.py`、`test_tool_reads_privacy_pg.py`、`test_toolkit_pg.py`，67 passed / 13.10s。首次 5 failed / 62 passed 揭示健康关键词漏识别及一个新断言误解 stopped 的 ok 契约；修复后重跑以上组合。

组合二：新增复诊参数后，pytest `test_memory2_context_pg.py`、`test_memory2_categories_pg.py`、`test_context_pg.py`、`test_context_time_retrieval_pg.py`，34 passed / 10.54s。两组有交集，不将相加当唯一用例数。Ruff 检查相关新改代码通过；格式按项目既有 120 列检查。

## 限制与下一步

这不是阶段验收。里程碑全量回归待 23:30–44 错峰窗口，指定 `--target v4` scripted 场景尚未执行。用户首次点击确认→写入类别授权的消费流程、去重、单值槽冲突更新、精确撤销、过期归档及画像反思仍未完成。没有迁移或部署。原有旧模块线 WIP 保存在 stash，不混入此分支。
