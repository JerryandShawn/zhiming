# P0 本地评测框架验证

日期：2026-10-17，UTC+08:00。真实模型调用为0，以下模型均是明确的测试替身或脚本回放；PostgreSQL与咨询服务未替换。

| 检查 | 结果 |
| --- | --- |
| `python tools/eval/runner.py --validate-only` | Validated 80/80 scenarios |
| `python tools/eval/runner.py --mode scripted --target fake --self-test` | 80/80，48个框架测试通过，1.25秒 |
| `python -m pytest tests/v4 -q`（隔离PG15，Core3.11） | 119 passed，32.90秒，0跳过 |
| 新代码ruff E,F,I,B,UP,SIM / 120列 | All checks passed |
| 新代码ruff format / 120列 | 21 files already formatted |
| `git diff --check` | 退出0 |

脚本报告：[2026-10-17-scripted-fake-scripted-v1.md](../../eval/2026-10-17-scripted-fake-scripted-v1.md)，同名JSON记录版本、源码/配置/rubric哈希和分类分数。80/80表示独立脚本观测的回放和判分正常，不表示v4业务已实现。

新测试覆盖文本同义备选、工具正反条件、回执、DB计数/状态/路径/范围、事件序列的正反例；全部场景重复回放一致；schema坏格式拒绝；评审非法结构/非有限分数失败关闭；不完整真实评测不生成基线；报告仅保留至多200字合成预览；恢复时核对场景/配置/rubric/源码版本。

44个v3适用场景全部初始化真实合成PG状态并执行原有ConsultationService首轮；替换的只有模型，未用fake_target替代业务服务。来源、计数、未来冻结时间和回环路由的回归说明见 [v3-seed-validation.md](v3-seed-validation.md)。

整仓ruff检查另有6399项既有发现，日志仅本机忽略的`private/p0-logs/ruff-legacy.json`；新增目录发现0项。旧大文件不整体重排；业务改动严格限于today()改走Clock。

真实模型基线在用户授权及可用进程环境配置就绪后单独运行。尚未生成`baseline-v3.json`；不会把测试替身或供应商配置故障的0分冒充v3能力基线。
