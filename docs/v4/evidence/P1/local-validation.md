# P1 本机验证记录

仅本机隔离 PostgreSQL 15；模型 HTTP 为 MockTransport，真实模型调用另见探针与 c2 运行报告。没有 stage/生产/真实渠道验证。

| 检查 | 结果 | 说明 |
| --- | --- | --- |
| 旧 Core 全量 | 553 执行，初轮552通过、1环境失败 | 815.549秒；失败为缺少 pg_dump/pg_restore PATH，没有业务断言失败 |
| 真实备份恢复复查 | 3/3 | 加入已有 PostgreSQL bin 后1.443秒通过；未修改测试 |
| 旧模型诊断复查 | 10/10 | provider 元数据字段变更后0.464秒通过 |
| v4 最终全量回归 | 339/339，零跳过 | 128.22秒；真实隔离PG；最终代码验收提交 a47d583 |
| ModelPort 最终定向 | 89/89 | 5.97秒；含真实 PG 的新垫片成功/回滚开关/额度一次失败路径 |
| 模型包覆盖率 | 94.36%（619/656语句） | coverage 输出四舍五入94%；报告 model-coverage.json；门槛85% |
| v1 scripted + self-test | 80/80；48/48 | 旧语义不改；这不是模型能力评分 |
| c2 scripted | 80/80 | 验证回放与确定性契约；自然语言质量需要独立评审，不能用此结果代替 |
| Ruff | check通过；21文件 format check通过 | E/F/I/B/UP/SIM、120列；consultation仅局部改，不整体重排旧文件 |

命令为仓库中 Core Python 下的 `unittest discover -s tests -p test_core*.py`、`pytest tests/v4 -q`、`coverage run --source=mingjing_core.models -m pytest tests/v4/models -q`、`coverage report --fail-under=85`、两个 runner 的 scripted 模式。详细原始测试输出保存在本机 private，不上传包含请求载荷的失败栈。

新增真实服务集成测试发现并修复：LangGraph 安全边界会用固定安全消息重建异常；新错误类型需兼容单个位置消息参数，同时忽略外部传入正文，继续使用固定安全文案。没有改动旧运行时或旧断言。

c2 执行源码冻结为 `74f83b8`，源码 SHA256 见 c2-execution-source.json。此唯一实测已在 T05 的 HTTP403 停止，不重试、不降级。403原因未确认；全夜真实调用142次（38探针、80目标、24评审），此后关闭全部真实调用。报告不完整，有基础设施失败，不能作为能力基线；只生成 baseline-v3-c2.status.json，不生成有效 baseline-v3-c2.json。

最终端口另经过独立只读复核并修复：退避后跨总截止时间仍发请求、上一用户轮的 tagged reasoning 被回传、指数溢出 JSON、Anthropic 多 Part 工具结果、不可读429响应体的分类、注册表跨供应商总截止时间。相应最小 MockTransport 复现与回归均通过；真实 PG 的撤销/隔离仍由完整v4回归覆盖。

实测使用冻结的旧 ConfiguredModel 与评测代码。之后只对端口硬化和校准候选选择作离线修正，未重跑模型、改写实测原报告或旧v1结果。最终校准候选为20条确实存在P0预览的ID（覆盖七类）；P0仅留200字，无法还原原全文与回执。独立保留实测导出的20槽候选，其中9条有新c2完整合成回答。人工标签0，一致率未计算。
