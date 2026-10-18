---
name: tarot
description: 按固定已翻牌阵解释大牌、小牌、宫廷牌、牌位关系及逆位，保留自主与防反复规则。
---

# tarot 命理解释技能

版本：p8-skills-draft-2026-10-19-v2.2。只解释当前已授权、已计算的产物，不执行计算或写入。章节内示范引用必须换成本轮真实别名；没有注册就不引用，非八字rule_hits不制造〔r#〕。

优先按问题加载一章；未核验字段不补造。每章报告方法、前提、流派差异、反例与可观察行动。U3只生成版本化建议，保存与确认由主线回执决定。

| topic | 章节/适用问题 | 需要的实际字段 |
| --- | --- | --- |
| `major` | [大阿卡纳：象征主题与牌面版本](01_major.md)；大牌多意味着命运已注定吗 | `/cards`、`/deck_version`、`/meaning_version`、`/status` |
| `minor` | [小阿卡纳：四花色、元素与数字](02_minor.md)；同花色或同数字怎样连读 | `/cards`、`/cards/0/card/suit`、`/cards/0/card/number`、`/meaning_version` |
| `court` | [宫廷牌：角色方式而非固定人物](03_court.md)；宫廷牌一定代表某个人吗 | `/cards/0/card/rank`、`/cards/0/card/suit`、`/cards/0/orientation`、`/spread` |
| `spread` | [牌阵与位置：问题、上下文和固定牌](04_spread.md)；牌阵位置怎样改变解读；能否补抽 | `/id`、`/question`、`/spread/positions`、`/cards`、`/draw_source`、`/context_snapshot` |
| `relations` | [牌间关系：支持、张力与反例](05_relations.md)；几张牌能否形成故事；重复牌怎样看 | `/cards`、`/spread/positions`、`/cards/0/card/meaning_version`、`/meaning_version` |
| `reversals` | [逆位的几种读法](06_reversals.md)；逆位是不是坏牌；怎么避免随意解释 | `/reversals`、`/cards/0/orientation`、`/cards/0/card/upright`、`/cards/0/card/reversed`、`/cards/0/card/misreading` |
| `misreadings` | [常见误读与自主决策](07_misreadings.md)；能否用牌决定分手、就医或投资 | `/cards`、`/question`、`/status`、`/revision`、`/previous_draw_id`、`/context_snapshot` |

字段根对象、可选能力、待接入项和rule_id均见章节及catalog.json。只读材料不授予写入权限。
