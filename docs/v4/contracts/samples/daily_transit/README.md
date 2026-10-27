# 阿远：2026-10-21 至 10-27 流日样例

七份 `ayuan_YYYY-MM-DD.json` 为与 chart_compute 相同的完全合成人物，本机实际历法/紫微/Swiss 引擎计算，非模型生成。每份是对应日期北京时间 12:00（04:00 UTC）的快照，不能当作整天的所有行运。

直接读取 `data.bazi`、`data.ziwei`、`data.astro`。三体系均有实际规则命中，`rule_hits[].context` 提供明确类别；别名点击按 `aliases.c/r[].path` 从当前 JSON 根解析。每个文件的 `c1/r1` 只在自己文档内有意义，不可把七天短别名混成同一证据。

`manifest.json` 绑定日期、文档 ID、规则及别名数量。校验以 [Schema](../../daily_transit.schema.json) 和 Python 测试为准；JSON Schema 通过不能证明预测有效，数据未接入 HTTP、Agent 或持久化。

本命默认真太阳。阿远当例的北京时间四柱与紫微语义盘面相同，`comparisons` 为空；原时刻在时辰边界附近的提示应与 chart_compute v1.1 的 `boundary_alerts` 一起显示，不应据此把另一个时辰确认成用户事实。

重新生成（Charts 解释器）：

    python -m mingjing_core.adapters.charts.benchmarks.daily_transit_samples --mode scripted --output docs/v4/contracts/samples/daily_transit

脚本断开网络传输、清 API 凭据并关闭追踪，只有本地计算和合成样例写盘。真实模型请求 0；真实用户资料写入 0。
