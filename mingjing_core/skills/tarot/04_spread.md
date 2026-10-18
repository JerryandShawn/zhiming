# 牌阵与位置：问题、上下文和固定牌

版本：p8-skills-draft-2026-10-18-v2；状态：待所有者抽查的解释草稿，不是模型或现实预测验证。

## 方法步骤

1. 先说明question、spread.id与每个position/label，再按牌位解释。reflect3等产品牌阵用实际位置文字，不能把它冒称书中凯尔特十字。
2. 自动、点选、手动来源都以固定公开快照为准；未翻开、取消或未完成牌阵不解读。更正沿用服务的revision与reason，模型不自行重新洗牌。
3. 同一或近似问题24小时内，先沿用最近牌阵并温和指出反复求确定。用户明确坚持的新抽需要实际工具规则与原话溯源；本技能文本不执行抽牌或修改记录。

## 需要的盘面字段

根对象：TarotService.get_for_reading public draw。以下为 JSON Pointer；数组示例索引0仅演示路径，必须按实际对象检索。

- `/id`
- `/question`
- `/spread/positions`
- `/cards`
- `/draw_source`
- `/context_snapshot`

## 各流派观点与分歧

牌阵有多种传统；Waite Part III §7只是其中一种。位置为本次提问设定的阅读语境，不能倒推成客观人生事实。U7的24小时规则是产品决定，不假托古籍。

## 适用前提

仅在TarotService.get_for_reading成功后的owner范围内读取。牌阵、事项与阶段关联不能绕过；旧牌复用契约不因24小时经过自动失效。

## 反例与常见误读

不喜欢答案就补牌、把“建议位”当“结果位”、把固定旧牌悄悄换成更积极的牌，都会破坏依据。

## 表达示例

“这张牌在‘可控行动’的位置〔t1〕，所以我先谈你能做什么。我们沿用这副已固定的牌，先核查现实进展，再决定是否真的需要新抽。”


## 对应的规则命中 rule_id 列表

本章不新增八字条件规则；本批U12只有八字，不补算其他体系或民间口诀。

## 参考来源

- [A. E. Waite, The Pictorial Key to the Tarot](https://www.sacred-texts.com/tarot/pkt/pkt0307.htm)，Part III §7 An Ancient Celtic Method of Divination；产品reflect3等不是该原牌阵。
- [A. E. Waite, The Pictorial Key to the Tarot](https://www.sacred-texts.com/tarot/pkt/pkt0306.htm)，Part III §6：读牌方法背景；24小时守卫是项目规则。

以上白话为项目原创概括；公开转录不等于原刊校勘。传统概念不证明现实预测有效。
