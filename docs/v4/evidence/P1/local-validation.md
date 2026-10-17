# P1 本机验证记录

仅本机隔离 PostgreSQL 15；模型 HTTP 为 MockTransport，真实模型调用另见探针与 c2 运行报告。没有 stage/生产/真实渠道验证。

| 检查 | 结果 | 说明 |
| --- | --- | --- |
| 旧 Core 全量 | 553 执行，初轮552通过、1环境失败 | 815.549秒；失败为缺少 pg_dump/pg_restore PATH，没有业务断言失败 |
| 真实备份恢复复查 | 3/3 | 加入已有 PostgreSQL bin 后1.443秒通过；未修改测试 |
| 旧模型诊断复查 | 10/10 | provider 元数据字段变更后0.464秒通过 |
| v4 初轮回归 | 325/325 | 74.97秒，含早期75项端口检查；后加3项真实服务集成单独验证 |
| ModelPort 最终定向 | 78/78 | 4.55秒；含真实 PG 的新垫片成功/回滚开关/额度一次失败路径 |
| 模型包覆盖率 | 92.86%（572/616语句） | coverage 输出四舍五入93%；报告 model-coverage.json；门槛85% |
| v1 scripted + self-test | 80/80；48/48 | 旧语义不改；这不是模型能力评分 |
| c2 scripted | 80/80 | 验证回放与确定性契约；自然语言质量需要独立评审，不能用此结果代替 |
| Ruff | check通过；21文件 format check通过 | E/F/I/B/UP/SIM、120列；consultation仅局部改，不整体重排旧文件 |

命令为仓库中 Core Python 下的 `unittest discover -s tests -p test_core*.py`、`pytest tests/v4 -q`、`coverage run --source=mingjing_core.models -m pytest tests/v4/models -q`、`coverage report --fail-under=85`、两个 runner 的 scripted 模式。详细原始测试输出保存在本机 private，不上传包含请求载荷的失败栈。

新增真实服务集成测试发现并修复：LangGraph 安全边界会用固定安全消息重建异常；新错误类型需兼容单个位置消息参数，同时忽略外部传入正文，继续使用固定安全文案。没有改动旧运行时或旧断言。

c2 执行源码已在本机冻结为 `74f83b8`，源码 SHA256 见 c2-execution-source.json。后续硬化改新 models 包/测试，并在服务诊断记录追加 provider；已经启动的 c2 进程使用启动时载入的冻结旧服务。旧适配器、c2评审/场景代码未改。最终交付代码与基线执行快照分开追踪。
