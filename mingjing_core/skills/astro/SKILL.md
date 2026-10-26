---
name: astro
description: 按程序西占产物解释本命、相位、行运区间、具名次限与太阳回归，区分实际UTC和象征时刻。
---

# astro 命理解释技能

版本：p8-skills-draft-2026-10-26-v2.5。只解释当前已授权、已计算的产物，不执行计算或写入。章节内示范引用必须换成本轮真实别名；没有注册就不引用。本体系不补造八字U12结构r；本轮真实提供、met=true且已登记的边界或工具r可按其来源文档引用，不能当作本体系新增结构规则。

优先按问题加载一章；未核验字段不补造。每章报告方法、前提、流派差异、反例与可观察行动。U3只生成版本化建议，保存与确认由主线回执决定。

| topic | 章节/适用问题 | 需要的实际字段 |
| --- | --- | --- |
| `natal` | [行星、星座与宫位](01_natal.md)；如何读本命盘而不只讲太阳星座 | `/data/planets`、`/data/houses`、`/data/asc`、`/data/mc`、`/data/method`、`/data/calculation_flags/natal` |
| `aspects` | [相位、容许度与条件](02_aspects.md)；刑冲是否必坏；相位为什么软件不同 | `/data/aspects`、`/data/aspect_orb`、`/data/planets`、`/data/method` |
| `transits-progressions` | [行运与次限推运：区间和技术分开](03_transits-progressions.md)；行运何时精确；次限是否已经算出 | 旧快照 `/data/transits`；可选区间 `/data/p8_transit_windows`；次限信封 `/data/progressed_planets`、`/data/mapping`、`/data/actual_UTC` |
| `returns` | [太阳回归盘：时刻、地点与比较](04_returns.md)；今年回归盘怎样看；能否用生日中午代替 | 回归信封 `/data/planets`、`/data/root`、`/data/actual_UTC`、`/data/houses`；不混用旧本命 `/data/asc` |
| `misreadings` | [西占常见误读与证据边界](05_misreadings.md)；为什么不能用星盘诊断或保证未来 | `/data/quality`、`/data/method`、`/warnings`、`/data/utc_time`、`/data/calculation_flags` |

字段根对象、可选能力、待接入项和rule_id均见章节及catalog.json。只读材料不授予写入权限。
