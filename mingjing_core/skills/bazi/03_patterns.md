# 格局候选与成立条件

版本：p8-skills-draft-2026-10-19-v2.2；状态：待所有者抽查的解释草稿，不是模型或现实预测验证。

## 方法步骤

1. 逐个读 regular_eight 的 conditions、satisfied、unsatisfied、screen_passed；先月支藏神，再看透干与筛选牵制条件。通过筛选只能称候选。
2. 从财、从杀、从儿、从旺分开读 following，指出无根、无生扶、强弱阈值及十神占比哪些成立；这些是可复核项目筛选，不代表完整真假从格学说。
3. 读 not_evaluated，列出合化、救应、特殊外格、岁运成败尚未纳入的条件。多个候选并存时保留，不由语言模型自行填补盘面或改条件。

4. `regular_extra`另列建禄、月劫、阳刃，每项三条件合成一个候选命中，逐子条件核对；与八正格合计38条规则。月支藏神的`qi_matches`区分本气/中气/余气；辰戌丑未注明杂气透干会支尚未完整实现。

## 需要的盘面字段

根对象：CalculationArtifact。以下为 JSON Pointer；数组示例索引0仅演示路径，必须按实际对象检索。

- `/data/p8/patterns`
- `/data/p8/strength`
- `/data/p8/ten_gods`

## 各流派观点与分歧

月令取格、透干取格、从格边界并不统一；《真诠》的用神多为格局枢纽，不应与现代常说的扶抑喜用混成一词。救应与合化是正式补全项，目前不宣布成立。

审校后的P8筛选：伤官牵制看正官，庚辛日主保留金水例外；七杀见财且无食神透出才触发本条牵制；印见正偏财、财见比劫或七杀、食神见偏印分别列明。印轻、财轻比重、力量与救应未判，不得把保守筛选写成古籍完整败格判定。七杀的食神、正印、偏印是并列取用候选，并不要求同时使用。旧v3算法保留，仅显式P8采用本修订。

## 适用前提

需要完整四柱及所选方法的强弱输出；必须在相同 subject、revision、branch 内对照。跨分支候选不同应说明时间条件。

## 反例与常见误读

“食神透出=食神格”“极弱=必从”都是省略条件。某候选未过当前筛选，不等于所有流派都排除它；过筛也不能保证职业或财运。

## 表达示例

“月令线索支持把食神格列入候选，但另一项条件尚未满足〔c1〕。我们先记候选与缺项，不能直接说已经成格。”

“阿远，程序核到了伤官和正官同透〔c1〕，但你这张如果是庚辛日主，还要一起看金水例外〔c2〕。这条命中〔r1〕只是提醒我们把条件看全，不是说工作一定会出问题。”别名为表达模板，只有本轮实际注册了对应依据才可使用；未命中项不能编造r别名。


## 对应的规则命中 rule_id 列表

`u12-pattern-officer-c1`、`u12-pattern-officer-c2`、`u12-pattern-officer-c3`、`u12-pattern-killer-c1`、`u12-pattern-killer-c2`、`u12-pattern-killer-c3`、`u12-pattern-seal-c1`、`u12-pattern-seal-c2`、`u12-pattern-seal-c3`、`u12-pattern-indirect-seal-c1`、`u12-pattern-indirect-seal-c2`、`u12-pattern-indirect-seal-c3`、`u12-pattern-wealth-c1`、`u12-pattern-wealth-c2`、`u12-pattern-wealth-c3`、`u12-pattern-indirect-wealth-c1`、`u12-pattern-indirect-wealth-c2`、`u12-pattern-indirect-wealth-c3`、`u12-pattern-output-c1`、`u12-pattern-output-c2`、`u12-pattern-output-c3`、`u12-pattern-hurting-officer-c1`、`u12-pattern-hurting-officer-c2`、`u12-pattern-hurting-officer-c3`

`met=true`只表示该条件成立；未命中项在rule_assessments，不能把单条件命中写成成格或事件确定。〔r#〕须由本轮上下文实际分配。

新增`u12-pattern-established-lu`、`u12-pattern-month-robber`、`u12-pattern-yang-blade`各保留三项`condition_assessments`；单项缺失时只读未命中assessment。

## 参考来源

- [沈孝瞻著、徐乐吾评注《子平真诠评注》](https://www.anhappy.com/share/books/others/books/%E5%9B%BD%E5%AD%A6/%E5%AD%90%E5%B9%B3%E7%9C%9F%E8%AF%A0%E8%AF%84%E6%B3%A8.pdf)，第八章论用神、第九章论用神成败救应、第十章论用神变化、第二十二章论外格用舍。
- [《子平真诠》公开转录第九章](https://donglishuzhai.net/chapter/3722.html)，成败条件；第十四章金水例外、第十六章杂气、第三十九章七杀、第四十一章伤官、第四十三章阳刃、第四十五/四十六章建禄月劫；逐章链接见rules-review。公开转录与原刊差异仍待校勘，三格三条件是项目显性筛选。

以上白话为项目原创概括；公开转录不等于原刊校勘。传统概念不证明现实预测有效。
