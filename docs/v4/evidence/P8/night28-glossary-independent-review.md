# Night28 术语词典独立内容审阅

审阅时间：2026-10-20 23:52:16 +08:00（项目 Clock 实际读数，北京时间）。
分支：`v4/p8-calc`。范围：只读词典及其本地来源，不修改数据、旧引擎或前端；本报告是本审阅者唯一新增文件。

## 结论与适用范围

已逐条阅读全部 212 条的 `term_id`、术语/别名、定义类别、白话、例句、出处、流派差异和待核字段，分布为八字 72、紫微 55、西占 50、塔罗 35。没有发现所抽核十神关系、十二星座角度、紫微宫位几何或塔罗牌号的数学错误；原创解释与外部技术文档、古籍待核的边界总体明确。

修前发现三组出处链缺口和一处含糊措辞，详见下表历史记录；来源代理修正后，已于北京时间 23:59 完成逐项独立复读，G1–G4 均落实，最终 SHA 见文末。当前可称“已全读并修正出处的项目术语草稿”，不能据此称古籍原刊或全部门派解释已完成校勘，也不能把结构/源码核对说成预测效度验收。以下原始结果固定到修前 SHA，不将修前缺口抹去。

| 文件 | 审阅时 SHA-256 |
| --- | --- |
| `mingjing_core/knowledge/p8_glossary/terms_v1.json` | `a50f3993162a0f20dc9b33cd634bd004a33a8cca67a4b36b0ebf11970f8a65e1` |
| `mingjing_core/knowledge/p8_glossary/sources_v1.json` | `80b04bba20a1b67f546ee21aeb4b20b881161de1765221ec7852a03e10ee37d2` |

## 修前发现的条目（历史记录，修后状态见文末）

以下均为草稿的证据定位/编辑问题，未发现相应算法描述本身有错。不改 v3，也不扩大算法范围。

| 编号 | term_id / 位置 | 问题与本地证据 | 建议 |
| --- | --- | --- | --- |
| G1 | `bazi-year-pillar`、`bazi-month-pillar`、`bazi-day-pillar`（terms 481、509、537 行起） | `school_differences` 具体断言 P8 物理瞬间节年/节月与 sect1 晚子日界，但只引用 `p8-elements`。`calculations/bazi/elements.py` 定义十神及四柱符号校验，不实现节界或日界。实际依据为 `adapters/charts/time_basis_candidates.py:_candidate`：`physical.getYearInGanZhiExact()`、`physical.getMonthInGanZhiExact()`、`local.setSect(1)` 及 `pillar_method`。 | 给这些具体方法声明补充时间候选实现的具名来源和定位。日干/符号部分仍可保留 `p8-elements`。同类方法声明 `bazi-jie-boundary`、`bazi-late-zi-hour` 也宜直连 `_candidate`，避免仅靠通用入口间接溯源。 |
| G2 | `bazi-direct-officer`（761 行起）、`bazi-yang-blade`（1657 行起） | 前者的 P8 正官牵制/庚辛例外只引 `p8-elements`，实际为 `p8_structure.py:restraint`，应与已经正确双引的 `bazi-hurting-officer` 一致。后者的默认五阳干刃位在 `p8_structure.py` 可核，但阴干两异表在 `knowledge/p8_bazi/schools.json:/blade` 和 `named_bazi.py:named_stars`，现有 `p8-pattern-review` 的路径不含这两表。 | 前者补 `p8-pattern-review`；后者补具名 `schools.json` 出处。继续保留逆行阴刃原典未核的标记，不将 `primary_attribution_pending_not_verified` 改成古籍已验证。 |
| G3 | `astro-orb`（214 行起） | `p8-astro-aspects` 能支持五大相位与误差 `<= orb`，但该函数必须显式传 orb，不能独自支持“本命/合盘默认 6 度、流日默认 2 度”。本命默认在 `hermes/astro.py:aspects/chart`，合盘在 `synastry.py:synastry`，流日在 `daily_transit.py:daily_transit[_prepared]`。 | 保留数学来源，给默认值声明补实际调用方出处，区分默认参数与所有流派通则。 |
| G4 | `astro-equal-houses`（4989 行起） | 白话为“从精确上升度数起每30度分一宫，不确定以整星座起点作宫头”。“不确定以”容易读成基准未确定，和同条明确采用 A/E 的说明不一致。 | 明写本条 A/E 口径从精确上升度起，每 30 度一宫；整宫制另条处理。无需更动计算。 |

## 逐体系内容核对

| 体系 | 全读条数 | 本轮重点与结果 |
| --- | ---: | --- |
| 八字 | 72 | 十神十类的阴阳/生克说明与甲日主例句正确。用独立的生、克五行映射逐一检查 100 个日主/他干组合，与实现零差异；这是同一审计程序中的组合检查，不是 100 个测试用例。原局例 `甲戌/丁卯/丁酉/甲辰` 干支及年上起月、日上起时关系可自洽。伤官牵制正官/庚辛例外与当前 P8 一致，未以词典改 v3。藏干司令异表、二藏干不补中气、阴刃逆行未核、六破项目表、旺衰权重未经标定均写明边界。 |
| 紫微 | 55 | 命宫不固定数组第 0、命主/命宫与身主/身宫分开；十四主星名单及原创建议对上技能原文。对宫 `(i+6)%12`、三方四正的两组三合 `(i+4)%12` 与 `(i+8)%12` 例句正确。默认壬科左辅、可选 quanshu 壬科天府与 `p8_ziwei/flying_v1.json` 一致；可选宫干表不覆盖原生生年/运限标签，原刊待核未被抹掉。缺星不补落点、自化与化忌冲只作当前几何定义，没有编造向心/离心算法。 |
| 西占 | 50 | 十二热带黄道区段与座内度数例句逐一核对；跨 0 度的 359/1 相隔 2 度、75 度为双子 15 度正确。五大相位 0/60/90/120/180 与举例容许误差正确。热带黄道与恒星星座、黄经与黄纬、MC 与天文天顶、整宫与等宫、实时行运与次限象征时刻均分开；逆行不说轨道倒转。次限映射 365.2422 为项目具名参数，没有冒称古典逐字算法。等宫制措辞和默认值出处见 G3/G4。 |
| 塔罗 | 35 | 全读 22 大牌条目及 13 个方法/分类条目。22 个 `cards[index]/card_id` 均与固定牌义数据相同，名称、原创署名、牌义版本均一致；RWS 力量 8/正义 11，22+56、四花色各 14 张正确。逆位不是正位简单反义，不启用逆位的读法与项目固定朝向分开；四类过程读法、花色元素、宫廷角色及 24 小时守卫均明说项目编辑/产品约定，没有冒署 Waite 原句或将逆位定为坏事。 |

所有条目的 `pending_review` 均已阅读；没有把“各派可能不同”提升为未举出处的唯一门派真理。202 条沿用“具名项目口径与跨派核对状态”的栏目名，内容多为当前项目范围与尚未对读的限制；这不等于已完成 202 项具名门派对照。后续若要提供学术型跨派词典，应补具名书目、版本和相应定位，而非删除待核来提高完成率。

## 出处与定位检查

- 注册表 32 个来源：16 个 `project_implementation`、11 个 `project_editorial`、2 个 `official_scientific_documentation`、3 个 `official_implementation_documentation`。本地 27 个路径全部存在，所有条目和流派差异的 `source_id` 都能在注册表解析。
- 对 14 个 Python 来源检查 32 个具体函数名，均能在相应文件 AST 中找到。JSON 规则表、技能章节以实际文件内容核对。此项只证明定位存在，不证明各来源覆盖某条所有断言；G1–G3 正是“路径存在但具体声明出处不足”的区别。
- `p8-calendar` 中 `snapshot` 为 `calendar_layers()` 内局部变量，并非公开函数；可定位到该变量，不能误报为同名函数接口。
- 三个注册但当前条目未直接使用的来源为 `p8-pattern-registry`、`p8-ziwei-combination-editorial`、`p8-astro-aspect-editorial`，不据“注册”推断正文已经引用。
- 塔罗逐牌 `/source/type=original_editorial` 和 `meaning_version=zhiming-editorial-2026-10-10-v1` 可核。紫微主星关键词确在项目技能中标为原创概括；外行星没有托名为托勒密已列对象。没有发现项目原创文本被标成古籍逐字摘译。
- 本轮没有访问 5 个外部官方 URL。注册表里的 `official_document_read` 是原编写者记录，不能当作本审阅者已重新访问的证据。原刊版次/页码、公开转录与影印本差异仍按已有待核处理；本轮不能认证网页当前内容或全部原典支持。

## 实际验证与安全范围

本轮启动一个 Core Python 只读审计程序，约数秒结束，未运行 pytest 或全量回归。程序在 `handoff_offline.offline_runtime()` 下运行，并将 `subprocess.run/Popen` 替换为拒绝函数；读取两份词典、固定牌义、本地源码，通过 `Clock` 取得上述北京时间。Charts 进程 0、网络访问 0、真实模型请求 0、业务数据写入 0、数据库访问 0；未提交或推送。

观察结果为：212 条/212 唯一 ID；27/27 本地来源存在；32/32 具名函数定位存在；未知来源 ID 0；100 组十神关系差异 0；22 个大牌索引/名称/原创署名/版本差异 0。不得把这里的字段/组合断言次数换算成测试用例数或专业评测分数。原代理的 252 项元数据测试为其独立结果，本轮没有重复运行，也不作为内容准确率。

复核所读实现和数据：`calculations/bazi/elements.py`、`calendar_layers.py`，`adapters/charts/p8_structure.py`、`named_bazi.py`、`named_strength.py`、`time_basis.py`、`time_basis_candidates.py`、`time_basis_chart.py`、`time_basis_solar.py`、`astro_ephemeris.py`、`astro_progressions.py`、`daily_transit.py`、`synastry.py`、`ziwei_flying.py`，`knowledge/p8_bazi/schools.json`、`p8_ziwei/flying_v1.json`、`p8_interactions.json`、`tarot_meanings.json`，相关紫微/西占/塔罗技能章节；`hermes/astro.py`、`hermes/ziwei.py` 仅只读引用。

## 待核与后续

G1–G4 的修后复核见下节。外部页面当前内容、古籍原刊校勘、阴刃逆行原始出处、壬科天府原刊页码和现实预测效度均未在本轮新增验证。倒推时辰继续冻结/隐藏，词典不提供放宽门槛的理由。

## 修后独立复读（2026-10-20 23:59 +08:00）

本节时间来自工具实际 UTC 读数 `2026-10-20 15:59:15 UTC` 转固定 +08:00，未依赖本机时区。保留上述修前 SHA；修后逐条对比内存保留的原始 JSON 快照，212 个 ID、顺序、分布与顶层元数据未变化，仅 10 条既定词条发生定点修改。

| 文件 | 修后最终 SHA-256 |
| --- | --- |
| `terms_v1.json` | `b9d310c560df92666b9c1f2d4bdcf6c6a821d099908d113cc4a22acfb32e14a4` |
| `sources_v1.json` | `3e1d2035b299548b1b413a707d3bb28c0e5c8991b96ef3b0c0b723eb2c3aaf12` |

复读结果：

- G1：年柱/月柱/日柱新增 `p8-basis-pillars`，分别精确指向 `_candidate` 的实际物理节年/节月与声明坐标 sect1。`bazi-jie-boundary`、`bazi-late-zi-hour` 同样补了直接来源，不再仅靠通用入口间接解释。
- G2：`bazi-direct-officer` 补 `p8-pattern-review`；`bazi-hurting-officer` 原有定位也明确到对应 `checks` 与 `metal_water_exception`。`bazi-yang-blade` 补 `p8-school-tables` 与 `named_stars` 执行定位，并新增原典尚未找到逆行阴刃表的待核句；原有待核未删除或降格。
- G3：`astro-orb` 保留数学来源，同时补现有本命默认、合盘默认和流日默认的实际实现。新增注册来源的第一次调用链误写为不存在的 `astro_pair`，独立复读发现并交回修正，最终为 `synastry -> _comparison_data -> _astro -> aspects`；已只读核对实际函数和先行 consent 检查。
- G4：等宫制改为精确 Asc 黄经起每 30 度；例句明确白羊 15 度上升对应金牛 15 度二宫，与整宫金牛 0 度区分，并说明当前产品只输出 Placidus，未冒充已接入该可选宫制。修改没有触及算法。

10 条修订的完整集合为 `bazi-hurting-officer`、`astro-orb`、`bazi-year-pillar`、`bazi-month-pillar`、`bazi-day-pillar`、`bazi-direct-officer`、`bazi-yang-blade`、`bazi-jie-boundary`、`bazi-late-zi-hour`、`astro-equal-houses`。除等宫制白话/例句外均为来源、定位或支持范围的补充；仅阳刃增加待核说明，没有删减其它待核。

来源注册从 32 增至 36，新增 4 项均为项目实现：`p8-basis-pillars`、`p8-school-tables`、`p8-synastry-default`、`p8-daily-transit-default`。31 个本地路径存在、条目/流派差异无未知来源 ID；5 个外部 URL 及其原编写者阅读记录保持原范围，本轮没有外访，也没有重新认证其当前页面或原刊。来源中次限标题改为“一日对应一年”是用语澄清。

来源代理报告词典专属 pytest **265 passed、0 skipped**（原 252 场景、新 4 个来源路径及 9 项定点保护），并更新契约与其报告；本审阅者只读检查修后 JSON、源码定位和差异，没有重复启动该测试。当前本审阅者 Core/Charts 测试进程均为 0，未提交或推送，真实模型、网络及数据库访问仍为 0。

现代时制分类的可选改进保留为待核：平太阳时、北京时间、夏令时的 `definition_kind` 仍沿用初稿 `traditional_concept`，但正文与来源没有把它们伪装成古籍算法；后续可统一增加民用时制类别。本次没有为此扩大枚举或前端契约。
