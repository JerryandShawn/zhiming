# 命理线接线索引（持续草稿）

本索引供主线、模块线和前端只读使用，汇集本分支的当前入口；不是上线或专业验收证明。
记录日期为北京时间2026-10-21。范围是显式P8；默认v3入口、运行配置、数据库和前端未改。
各契约自己的版本和实际方法优先于本索引的简述。

## 计算与每日工具

| 能力 | 本地入口 / 契约 | 接线时保留 |
| --- | --- | --- |
| 主盘、双时基、规则、交界 | `P8ChartAdapter.time_basis/calculate/western_timing`；[chart_compute v1.1](chart_compute.md) | 三入口产物根不同；真太阳主解释、北京差异并列，西占物理UTC；旧calculate平太阳/八字sect2不改名 |
| 流日 | `P8ChartAdapter.daily_transit`；[daily_transit](daily_transit.md) | 北京时间正午快照、实际日期层、具名四化与西占容许度；七日阿远样例 |
| 区间择日 | `P8ChartAdapter.window_search`；[window_search](window_search.md) | 六用途、透明正负规则；每页最多31日，保留offset/next_offset和完整区间排序摘要 |
| 黄历 | `P8ChartAdapter.almanac`；[almanac](almanac.md) | 实际锁定历法库、sect与日界；宜忌是传统历书分类 |
| 合盘 | `P8ChartAdapter.synastry`；[synastry](synastry.md) | `consent=user_confirmed`先行、双方形状预检；字段不能代替外部授权，不输出关系成功率 |

工具结果同步、只读。主线负责把计算放入适当工作线程，并实现授权、取消、超时、持久化和工具注册。
阿远、小禾和技能原生样例全为合成资料，不能用作当前用户事实。

## 解释、学习和审阅

| 能力 | 入口 / 数据 / 契约 | 当前边界 |
| --- | --- | --- |
| 技能加载 | `mingjing_core.skills.loader.chart_skill(system, topic)`；[skill_assets](skill_assets.md) | 五包32章、目录v2.4、37组字段绑定；5500字节为上下文代理预算，实际模型tokens待主线核 |
| 术语词典 | `knowledge/p8_glossary/terms_v1.json`；[glossary](glossary.md) | 212术语/39来源；多数school说明是项目范围与待对读，不能称历史门派逐条校勘 |
| 学习要点 | `skills.learning.learning_outline`；[learning_outline](learning_outline.md) | 受信chart_compute输入、纯规则，复用实际c/r；不排新盘、不调用模型 |
| 20课与小测 | `knowledge/p8_learning_lessons/curriculum_v1.json`；[learning_lessons](learning_lessons.md) | 20课40题，真实合成观察绑定六输入SHA；`draft_for_review`，无教学进度存储 |
| 六类明确断言 | `skills.consistency.check_chart_consistency`；[chart_consistency](chart_consistency.md) | 日主/候选格局/分方法用神/大运/紫微主星/西占位置；有限语法、record_only |
| U12明确条件断言 | `skills.consistency_u12.check_u12_rule_assertions`；[u12_rule_assertions](u12_rule_assertions.md) | 独立v1，主线显式另调；38登记ID/完整名、实际assessment.met；条件命中不升级完整成格或效力 |
| 塔罗牌阵资产 | `knowledge/p8_tarot/spreads_v1.json`；[tarot_spreads](tarot_spreads.md) | 三个现有牌阵/九牌位，原创说明；只读交付，不自动成为运行注册源，不修改既有78牌义 |
| 方法差异 | [school_comparisons](school_comparisons.md) | 32项具名默认、可选、未实现与待核；不以项目权重冒充传统统一标准 |
| E2 M2控制输入 | `benchmarks.night28_controls.no_chart_input`；[e2_m2_controls](e2_m2_controls.md) | 模型可见严格两键题目/选项；评分元数据留外侧，旧C0含出生的语义保持独立；仅离线演练 |

两个文本检查器拥有不同的版本和Schema。不要将新`u12_rule`字段塞进旧v1 Schema，
也不要因`no_contradiction_found`就判定整段回答正确。引用、他人、比较口径、假设等保守待复核。
专业原刊、一般自然语言召回、模型表达和现实预测有效性未验证。

## 依据、权限和冻结状态

每个信封有自己的`document_id`和临时c/r命名空间。跨工具或跨案例合并时须重新登记，
不能把两份产物的c1/r1直接当同一事实。checker顶层c/r指文本比较；
`data.input_aliases`才是原盘依据。false assessment保留实际c，不制造传统r。
塔罗只引用当前固定牌阵的实际t；静态教材、牌阵定义和表达占位符不生成用户依据。

调用方必须验证provider、owner/subject、资料revision、操作上下文和撤销状态。
内容hash只绑定内容完整性，不能证明授权或独立计算真值。
倒推时辰保持`experimental_frozen`、默认隐藏、诚实拒绝，不因本轮新工具解冻。

E2固定种子宽松对照仍有2/14借入生日晚于目标年的阻塞，专业分数为null；
不得静默换seed、重抽、删除问题或把结构演练当真实评测。
待决与每日08:00/22:00汇总见[命理日报](../daily/2026-10-21_meta.md)。

本线未调用真实模型、访问项目服务器、发送飞书或合并PR；PR #5保持草稿。
