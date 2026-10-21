# 较早checkpoint CI收集失败与已发布修复

北京时间2026-10-21 07:54读取GitHub job真实日志：提交7f8ee338a09aa03840decabcb7e9bdf57ee86236，Core v3 checks运行39515456038，core job118946421514的“v4 clock and evaluation framework”失败。Core service/calculator与frontend步骤成功；后续ModelPort步骤跳过。

直接错误为新测试`test_legacy_freshness_guards_mod.py`使用bare helper import：

```text
from legacy_freshness_support_mod import (...)
ModuleNotFoundError: No module named 'legacy_freshness_support_mod'
```

该包收集问题已在83a48c422c3140dfb5a2607d8daeb78153d192c9改为显式相对import，并整理import顺序；独立98条守卫行为断言没有削弱。修复后的07:45合法窗口按默认包收集完整9560测试通过，374快照无漂移。新头GitHub CI仍需独立确认，不能用本地通过冒充CI绿，不重跑旧失败SHA来伪装修复。

旧07:43“仍in_progress”是当时工具观察；日志显示该job在07:50才输出收集错误，状态随后更新为失败。保留历史观察，不倒填当时未知结果。

此检查只读GitHub CI，没有登录应用服务器、访问stage/生产或调用模型/飞书。
