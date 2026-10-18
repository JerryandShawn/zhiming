# 牌间关系：支持、张力与反例

版本：p8-skills-draft-2026-10-18-v2；状态：待所有者抽查的解释草稿，不是模型或现实预测验证。

## 方法步骤

1. 先逐牌列牌位、朝向与快照，再比较相同花色/数字、对比主题和行动先后。连读必须保留每张牌的原始位置，不为顺故事删掉矛盾牌。
2. 用“一个需求与另一个需求拉扯”表达张力，提出两种可能的现实解释；从用户确认的情境中选择，不能让牌替用户确认事件。
3. 重复元素仅说明象征材料集中。跨次反复抽出的重复牌不作为统计独立证据；同一次固定牌阵重读也没有增加抽样次数。

## 需要的盘面字段

根对象：TarotService.get_for_reading public draw。以下为 JSON Pointer；数组示例索引0仅演示路径，必须按实际对象检索。

- `/cards`
- `/spread/positions`
- `/cards/0/card/meaning_version`
- `/meaning_version`

## 各流派观点与分歧

Waite Part III §5有重复牌传统断法，本项目仅借鉴“比较重复结构”的方法，不照抄必然事件的对应。现代图像/元素连读与传统列表可以并存，须说清采用哪种。

## 适用前提

同一可读牌阵与同一版本；牌未揭示不能纳入比较。不能把多次近似问题合成一份“应验率”或拿第三人隐私补故事。

## 反例与常见误读

三张积极牌不保证成功，两张圣杯不证明两人相爱，矛盾牌也不要求不停补抽直到一致。

## 表达示例

“一张牌强调行动，另一张提醒先恢复空间〔t1〕。我更愿意把它们读成节奏上的取舍；哪种更贴近你这周的真实安排？”


## 对应的规则命中 rule_id 列表

本章不新增八字条件规则；本批U12只有八字，不补算其他体系或民间口诀。

## 参考来源

- [A. E. Waite, The Pictorial Key to the Tarot](https://www.sacred-texts.com/tarot/pkt/pkt0305.htm)，Part III §5 The Recurrence of Cards in Dealing；不沿用必然事件列表。
- [A. E. Waite, The Pictorial Key to the Tarot](https://www.sacred-texts.com/tarot/pkt/pkt0306.htm)，Part III §6：读牌方法。

以上白话为项目原创概括；公开转录不等于原刊校勘。传统概念不证明现实预测有效。
