---
name: ziwei
description: 按程序紫微命盘解释命身宫、主星、四化、宫位组合与运限，不补造盘面或事件。
---

# ziwei 命理解释技能

版本：p8-skills-draft-2026-10-21-v2.4。只解释当前已授权、已计算的产物，不执行计算或写入。章节内示范引用必须换成本轮真实别名；没有注册就不引用。本体系不补造八字U12结构r；本轮真实提供、met=true且已登记的边界或工具r可按其来源文档引用，不能当作本体系新增结构规则。

优先按问题加载一章；未核验字段不补造。每章报告方法、前提、流派差异、反例与可观察行动。U3只生成版本化建议，保存与确认由主线回执决定。

| topic | 章节/适用问题 | 需要的实际字段 |
| --- | --- | --- |
| `palaces` | [命身宫与主星：先定位再解释](01_palaces.md)；命宫身宫有什么不同 | `/data/ming_gong`、`/data/shen_gong`、`/data/palaces`、`/data/topic_palace`、`/data/method` |
| `major-stars` | [十四主星：性质、组合与条件](02_major-stars.md)；主星怎样读；单星能否定性格 | `/data/palaces`、`/data/topic_palace/major`、`/data/topic_palace/minor`、`/data/topic_palace/linked_palaces` |
| `mutagens` | [四化与飞星：起点、落点和时间层](03_mutagens.md)；化忌是否一定不好；自化怎样核对 | `/data/palaces`、`/data/horoscope/yearly/mutagen`、`/data/horoscope/yearly/mutagen_links`、`/data/p8_time_interactions` |
| `combinations` | [宫位组合与三方四正](04_combinations.md)；事业、感情该看哪些宫 | `/data/selected_topic`、`/data/topic_palace`、`/data/topic_palace/linked_palaces`、`/data/palaces` |
| `time-layers` | [大限、流年与流月](05_time-layers.md)；今年和十年背景如何区分 | `/data/horoscope/decadal`、`/data/horoscope/yearly`、`/data/horoscope/monthly`、`/data/horoscope/daily`、`/data/palaces`、`/data/p8_time_interactions` |
| `misreadings` | [紫微常见误读与未知时辰](06_misreadings.md)；为什么同一人不同时间盘差很多 | `/data/method`、`/data/quality`、`/branch_id`、`/warnings`、`/data/palaces` |

字段根对象、可选能力、待接入项和rule_id均见章节及catalog.json。只读材料不授予写入权限。
