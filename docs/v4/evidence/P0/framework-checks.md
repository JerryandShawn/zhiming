# P0 本地评测框架验证

日期：2026-10-17，UTC+08:00。真实模型调用为0，以下模型均是明确的测试替身或脚本回放；PostgreSQL与咨询服务未替换。

| 检查 | 结果 |
| --- | --- |
| `python tools/eval/runner.py --validate-only` | Validated 80/80 scenarios |
| `python tools/eval/runner.py --mode scripted --target fake --self-test` | 80/80，48个框架测试通过，1.25秒 |
| `python -m pytest tests/v4 -q`（隔离PG15，Core3.11） | 184 passed，31.11秒，0跳过 |
| 新代码ruff E,F,I,B,UP,SIM / 120列 | All checks passed |
| 新代码ruff format / 120列 | 24 files already formatted |
| `git diff --check` | 退出0 |

脚本报告：[2026-10-17-scripted-fake-scripted-v1.md](../../eval/2026-10-17-scripted-fake-scripted-v1.md)，同名JSON记录版本、源码/配置/rubric哈希和分类分数。80/80表示独立脚本观测的回放和判分正常，不表示v4业务已实现。

新测试覆盖文本同义备选、工具正反条件、回执、DB计数/状态/路径/范围、事件序列的正反例；全部场景重复回放一致；schema坏格式拒绝；评审非法结构/非有限分数/12类严重度不匹配失败关闭；基础设施不完整评测不生成基线，业务失败保留真实零分；报告仅保留至多200字合成预览；恢复时核对场景/配置/rubric/源码版本，只重跑基础设施失败，不重跑业务零分。比较只在双方live/complete、计分ID与评审契约一致时显示差值。

初次完整新增测试为119项通过，最终独立审查后增加65项评分/恢复/来源回归，最终184项全部通过。AST检查新增代码单文件≤400行、函数≤60行，无超限；没有改写旧测试来迁就实现。

44个v3适用场景全部初始化真实合成PG状态并执行原有ConsultationService首轮；替换的只有模型，未用fake_target替代业务服务。来源、计数、未来冻结时间和回环路由的回归说明见 [v3-seed-validation.md](v3-seed-validation.md)。

整仓ruff检查另有6399项既有发现，日志仅本机忽略的`private/p0-logs/ruff-legacy.json`；新增目录发现0项。旧大文件不整体重排；业务改动严格限于today()改走Clock。

真实模型基线在用户授权及可用进程环境配置就绪后单独运行。尚未生成`baseline-v3.json`；不会把测试替身或供应商配置故障的0分冒充v3能力基线。


## 中期复核增量（2026-10-17）

设计四文件已单独同步提交。T14、C03结构检查、C06实际金标及额度保护落实后，全量 `pytest tests/v4 -q` 为 **229 passed in 60.60s，0 skips**；随后仅增加裸429识别和安全HTTP状态透传，额度针对性回归为 **21 passed in 2.26s**（含4项真实隔离PG与LangGraph），原20项经独立复核通过。最终CI将再次全量执行新目录，不能把本节当作CI绿灯。

最终源码已重跑正式 scripted 报告：`Validated 80/80`、`Result 80/80`；自测48项通过（1.36秒）。新增代码Ruff与显式120列format通过。T14/C03/C06计算证据见chart-goldens.md；额度与分批证据见quota-protection.md；CI根因与修复见ci-v4-failure.md。没有改旧Core测试或业务适配器/User-Agent。
