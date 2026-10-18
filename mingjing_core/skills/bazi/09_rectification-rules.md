# 证据工作台：冻结、留出与置换

版本：p8-skills-draft-2026-10-19-v2.2；状态：低优先离线预备。已有准确时刻者优先使用第8章时间核对，不启动事件倒推。

## 方法步骤

1. L0可靠出生记录优先；L1先处理夏令时、真太阳时和交界。本章只解释冻结的低优先实验，默认不启动L3。L2民间口诀只展示，不参与评分，不作为弱先验偷偷加权。
2. 盲收集用户确认事件，不显示候选盘、时辰或中间得分，不诱导“那年是否搬迁”。冻结规范化events_hash与rules_version后，第一轮清单不可改年份；新增材料记第2轮，首轮结果不变。
3. 规则映射与年龄范围是项目口径。预计算年份×候选×信号；紫微四化单列，不与八字分数相加。事件≥6时，按session_id固定留出约1/3；训练领先者在留出前2才算支持。不足6件没有留出支持，必须拒绝区分。
4. 离线仍做1000次合理年龄年份置换，p=(1+零分布≥实际次数)/1001，保留p≤alpha、留出支持、唯一领先及margin≥delta三闸。校准严格绑定轮次/alpha和单一候选数/事件数；首轮.05、第2轮.025，最多两轮，未标定拒绝。23号已冻结为低优先实验：即使实验统计通过，产品仍“分不出来”，不启用解读倾向、不放宽门槛。

## 需要的盘面字段

当前已落地的是第8章只读时间核对envelope：`/time_basis`、`/charts`、`/profile_update_allowed`、`/life_event_scoring_performed`、`/model_calls`、`/writes`。这些不等于工作台已评分。

`/interpretation`、`/profile_basis_record`记录主口径只读建议；`/release_policy/rectification`记录默认隐藏的冻结状态。

工作台新结果字段distinguishable、p_value、margin、holdout、alpha、round、stable_conclusions、conditional_conclusions属于待接入契约；未取得实际程序结果不作结论。旧RectificationEngine、两分加总与前三字段已撤回，不再调用。

当前离线结果把统计是否通过单列为experimental_statistical_pass；distinguishable=false、selected_candidate=null、enabled_for_interpretation=false。真实信号E-R1唯一首名0/10，默认隐藏且不继续加入紫微命身信号；继续实验须另经复核。

## 各流派观点与分歧

事件→结构信号的映射、权重、合理年龄区间、holdout前2、alpha与delta均为项目口径，不是古籍评分公式。无可靠原典的映射必须source=null、注明项目口径待审；不能把八字、紫微共同主题当两份独立证据。

## 适用前提

每件事有来源、年份、类型与确认状态；源事实撤销后结果须标依据变化并重算。仅在另行获准的离线实验中，第二轮才按程序差异年龄段设计中立追问，不点名希望出现的事件类型；当前冻结状态不启动追问。确认前绝不改出生资料；可区分性不足而用户仍选择时，后续说明“时辰为你选定，依据不足”。

## 反例与常见误读

合成E-R1只测代码一致，不能用于证明方法有效。E-R2必须报告噪声曲线、≥200零数据的假阳性和Wilson区间、自信选错比例；门槛达不到就报告失败，不调宽阈值。E-R3外部人物资料须另得用户同意，未授权不下载、不入库。

## 表达示例

“程序这次说分不出来，我就不挑一个分高的当答案。能稳定讨论的结论与受时间影响的结论会分开；如果有出生记录，仍优先核对记录。”


## 对应的规则命中 rule_id 列表

本章不新增八字条件规则；本批U12只有八字，不补算其他体系或民间口诀。

## 参考来源

- 18_提示词增补包/P8_增补_时辰校正.md §E/F/J：冻结、留出、置换和门槛是项目设计。
- [Stellium预注册计算校正研究](https://stellium.readthedocs.io/en/stable/development/specs/rectification/RECTIFICATION_REPORT.html)：检验背景；本章不以同规则合成回收宣称现实效度。
- [Gelman与Loken：The garden of forking paths](https://stat.columbia.edu/~gelman/research/unpublished/p_hacking.pdf)：分析路径选择造成检验偏差的原始论文背景。

存疑/待核：事件映射、合理年龄、留出与统计闸门均为项目实验约束，外部人物E-R3及现实有效性未验证；本阶段冻结、默认隐藏并诚实拒绝，不因离线通过启用解读。
