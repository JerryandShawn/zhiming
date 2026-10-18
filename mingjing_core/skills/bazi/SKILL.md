---
name: bazi
description: 按程序八字产物解释十神、旺衰、格局候选、调候与岁运，并记录分歧和时辰校正边界。
---

# bazi 命理解释技能

版本：p8-skills-draft-2026-10-18-v2。只解释当前已授权、已计算的产物，不执行计算或写入。章节内示范引用必须换成本轮真实别名。

优先按问题加载一章；未核验字段不补造。每章报告方法、前提、流派差异、反例与可观察行动。U3只生成版本化建议，保存与确认由主线回执决定。

| topic | 章节/适用问题 | 需要的实际字段 |
| --- | --- | --- |
| `basics` | [基础、十神与司令](01_basics.md)；日主是什么；十神、藏干和司令怎么区分 | `/data/pillars`、`/data/day_master`、`/data/hidden_stems`、`/data/p8/ten_gods`、`/data/p8/month_command`、`/data/p8/selected_schools`、`/data/p8/auxiliary_stars` |
| `strength` | [旺衰判断：两种项目口径](02_strength.md)；为什么两种算法强弱不同；能否直接定喜用 | `/data/p8/strength`、`/data/p8/ten_gods`、`/data/p8/month_command`、`/data/p8/useful_candidates` |
| `patterns` | [格局候选与成立条件](03_patterns.md)；这是正官格还是从格；为什么不能直接定格 | `/data/p8/patterns`、`/data/p8/strength`、`/data/p8/ten_gods` |
| `climate-useful` | [调候与喜用：三条思路并列](04_climate-useful.md)；喜什么；调候和扶抑为什么冲突 | `/data/p8/climate`、`/data/p8/useful_candidates`、`/data/p8/patterns`、`/data/p8/strength` |
| `time-layers` | [大运、流年、流月与时间交互](05_time-layers.md)；什么时候换运；某月有什么结构变化 | `/data/p8/decade_luck`、`/data/p8/calendar_layers`、`/data/target_year`、`/data/target_month`、`/data/relations`、`/data/p8/time_interactions` |
| `life-topics` | [六亲、事业、财运与感情](06_life-topics.md)；能否谈行业、关系和现实选择 | `/data/pillars`、`/data/p8/ten_gods`、`/data/p8/patterns`、`/data/p8/useful_candidates` |
| `misreadings` | [常见误读、边界与档案一致性](07_misreadings.md)；结论冲突；旧分析是否能当事实 | `/data/method`、`/data/p8`、`/warnings`、`/revision`、`/branch_id` |
| `rectification` | [准确时刻优先：文档与时间口径核对](08_rectification.md)；出生时辰未知；人生事件能否缩小范围 | `/time_basis`、`/charts`、`/profile_update_allowed`、`/life_event_scoring_performed`、`/model_calls`、`/writes` |
| `rectification-rules` | [证据工作台：冻结、留出与置换](09_rectification-rules.md)；为什么候选得这些分；同分和月份未知如何处理 | `/time_basis`、`/charts`、`/profile_update_allowed`、`/life_event_scoring_performed`、`/model_calls`、`/writes` |
| `traditional-hour-methods` | [定时辰的传统方法：只展示，不计分](10_traditional-hour-methods.md)；民间口诀为什么不能定时辰 | `/time_basis`、`/charts`、`/profile_update_allowed`、`/life_event_scoring_performed`、`/model_calls`、`/writes` |

字段根对象、可选能力、待接入项和rule_id均见章节及catalog.json。只读材料不授予写入权限。
