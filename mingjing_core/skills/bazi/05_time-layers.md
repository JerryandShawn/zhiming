# 大运、流年、流月与时间交互

版本：p8-skills-draft-2026-10-18-v2；状态：待所有者抽查的解释草稿，不是模型或现实预测验证。

## 方法步骤

1. 先读起运 start_age、nominal_start_at 与每步 nominal_end_exclusive，分清虚岁显示、日历交运与所用 sect。按明确的目标日期选所属区间，不用主机此刻代替。
2. 流年以立春区间、流月以交节区间核对。年度列表与目标日快照可能属于不同节年；目标日时柱只是 UTC+8 正午采样，不代表全天择时。
3. 时间层与原局的关系只读程序清单：五合、相克、冲合刑害破会及十神变化必须来自 U2 产物。合或会出现不等于已经合化，缺项不能由模型临时凑表。

## 需要的盘面字段

根对象：CalculationArtifact。以下为 JSON Pointer；数组示例索引0仅演示路径，必须按实际对象检索。

- `/data/p8/decade_luck`
- `/data/p8/calendar_layers`
- `/data/target_year`
- `/data/target_month`
- `/data/relations`
- `/data/p8/time_interactions`：`nodes/relations/day_master/method/school`，各关系保留参与节点与complete/missing_branches；原局自身关系不重复纳入。

U2现有新入口可读取`/data/p8/time_interactions`。其目标柱取指定日的UTC+8正午快照；天干五合/相克、地支冲合刑害破会与十神均为结构观察，不建立合化或事件因果。

每条U2交互新增palace（实际涉及原局柱的列表）、domains与各school的priority字典。程序按所选school项目优先级、时间层与稳定id排序；不得由模型重新加重。年祖上/月父母/日配偶/时子女的标签为常见说法，目前未核可靠原刊条文，标存疑；领域映射与优先级是项目检索口径，不是人生事实。

## 各流派观点与分歧

日界、起运折算法、虚岁实岁和月界存在流派差异；本项目记录实际参数并保持 v3 原结果。旧 `/data/relations` 只涵盖部分关系；完整U2须读新入口独立块，三合/三会缺成员不能解释为完整成局。

## 适用前提

明确目标年/月/日与时区，有同一分支的原局和岁运产物。时辰不明只讲分支稳定项；“那天适合吗”先问现实安排与可控风险。

## 反例与常见误读

农历初一不是本项目流月交界；把每月15日样本当成整月完全一样、把刑冲直接等同事故日期，均是误读。

## 表达示例

“〔c1〕把这一步运的日历边界列在这里。那个月出现的是一组结构关系，并不等于事情必然发生；我们可以据此列一个现实观察点。”


## 对应的规则命中 rule_id 列表

`u12-palace-year-clash-combine`、`u12-palace-month-clash-combine`、`u12-palace-day-clash-combine`、`u12-palace-hour-clash-combine`

`met=true`只表示该条件成立；未命中项在rule_assessments，不能把单条件命中写成成格或事件确定。〔r#〕须由本轮上下文实际分配。

## 参考来源

- [沈孝瞻著、徐乐吾评注《子平真诠评注》](https://www.anhappy.com/share/books/others/books/%E5%9B%BD%E5%AD%A6/%E5%AD%90%E5%B9%B3%E7%9C%9F%E8%AF%A0%E8%AF%84%E6%B3%A8.pdf)，第七章论刑冲会合解法、第二十五章论行运、第二十六章论行运成格变格。

以上白话为项目原创概括；公开转录不等于原刊校勘。传统概念不证明现实预测有效。
