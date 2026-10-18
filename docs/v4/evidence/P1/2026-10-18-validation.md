# P1 14A/C 与 E1 准备验证（2026-10-18）

范围是会员额度边界、v2.1 判分契约、全文采集、冻结恢复及有效基线之后的新端口子集入口。
今日真实模型调用为0；以下模型和供应商测试均使用脚本或HTTP替身。
数据库回归连接本机PostgreSQL15.19 `127.0.0.1:55480/core_test_main`，E1专用库另为`core_test_e1`。
没有访问stage/生产或发送真实飞书。P1端口开关默认关闭，尚未生成有效c2.1基线。

## 主线验证

| 检查 | 命令 | 实际结果 |
| --- | --- | --- |
| 旧Core | `python -m unittest discover -s tests -p 'test_core*.py' -v` | 553/553，1340.335秒 |
| 全部v4 | `python -m pytest tests/v4 -q` | 458 passed，157.69秒，零跳过 |
| 端口与评测 | `python -m coverage run --source=mingjing_core.models -m pytest tests/v4/models -q` | 208 passed，117.00秒 |
| 端口覆盖率 | `python -m coverage report --fail-under=85` | 700/737语句，约95%，阈值通过 |
| 原脚本契约 | `python tools/eval/runner.py --mode scripted --target fake --self-test --output <独立目录>` | 80/80；自检48 passed，16.44秒 |
| v2.1脚本契约 | `python tools/eval/runner_v2.py --mode scripted --output <独立目录>` | 80/80；真实供应商0 |
| 静态检查 | 修改/新增现代Python的 `ruff check --select E,F,I,B,UP,SIM --line-length 120` 与 `ruff format --check --line-length 120` | 18文件通过；旧适配器仅最小补丁，不整体重排 |
| 差异检查 | `git diff --check` | 通过 |

Core回归将隔离PG备份工具加入本机PATH，Charts通过独立`CHART_PYTHON`调用。
本机Core无pip/coverage模块，coverage7.11.0安装在忽略目录`private/day-check-deps`并仅在该检查进程加入PYTHONPATH，未改变Core/Charts包环境。
脚本报告中的85次model_calls为模拟观测，不是85次真实请求。
旧CI兼容的`--stop-file/--once-file`在scripted模式未产生文件，历史夜间停止记录未删除。

## 针对边界的证据

`2026-10-18-member-quota-validation.md`记录公开403夹具、实际POST计量与真实PG接线。
最终追加的44项定向回归还覆盖nested error.type三条件、共享额度预检查停止传播、有效基线前禁止子集及基础设施错误不能完成子集。
`c21-offline-validation.json`记录C21的91项定向、16文件LF/Git blob核对、旧P0哈希和原场景保护；`c21-scripted/`保存实际80场景回放。

所有事实硬检查与判分分支都保留原回答，不通过改写回答让断言通过。
旧80场景、原rubric/schema/config/基线没有修改。现行逐条审计为81事实、9隐私字面、130语义模式。
旧v2.0审计原文保存在`docs/v4/eval/c2/contract-v2.0-assertion-audit.md`。

## 仍待执行

发布当前提交并等待其CI；CI绿后按15号授权合并PR3，再集成PR4。
在P2之前冻结独立P1执行快照，P2合并后从该快照启动E1；真实调用共享滚动五小时八十次账本。
仅完整有效基线之后，才补充标记为calibration_only的一条D02回答并运行新端口十场景子集。
20条人工标签与一致率未完成；同一决策场景两次独立回答是否满足七类覆盖要求，留给大脑裁定。
本文件不构成真实模型能力分数、stage或生产验收。
