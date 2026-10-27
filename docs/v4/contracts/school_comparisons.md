# 关键判断的流派与计算口径差异表

版本：`p8-school-comparisons-v1`。核对时间：2026-10-20 23:50（北京时间，UTC+08:00）。
范围：`v4/p8-calc` 已有纯计算、技能与具名知识表，供主线解释、学习模式和后续校勘使用。
这是静态说明，不注册新工具、不切换默认算法、不产生未计算的方法结果。

下文分别标出传统表格异说、项目量化规则、天文数值约定和旧行为保护。
它们并非都属于历史“流派”；两套输出一致也不能用作预测有效性的证明。
“可选”只表示已有显式计算选项，“未实现”不允许由 Agent 补出另一派的盘。
“待核”表示尚缺指定原刊或完整条件，不因已有网页转录就取消该标注。

字段定位中的 `*` 是实际数组索引的说明符，不是可直接解析的 JSON Pointer。
`chart_compute` 预览的原生字段保存在 `documents[].payload` 内，须先按其 Ref 解析；
表中的 `/charts/*/...` 等路径以相应原生文档为根，不可直接拼到预览顶层。

## 时间基础：先分清同一瞬间的坐标

| 判断点 | 默认 / 已实现 | 可选或未实现 | 影响字段 | 何时向用户提示 | 来源及待核 |
| --- | --- | --- | --- | --- | --- |
| 真太阳时、北京时间、出生地标准时 | P8 默认主解读为 `true_solar`；同一物理 UTC 的北京时间结果在四柱或紫微关键字段不同时并列；`standard` 保留诊断 | 出生地标准时不是海外出生者的北京时间；默认口径选择不替用户确认物理 UTC | `time_basis.selected_basis`、`charts[].interpretation_role`、`interpretation.comparisons`、四柱及紫微列 | 默认与北京时间不同时列出真实差异；不能只说“时辰已修正” | [TB](#source-tb)：项目23号裁定与明确时钟换算；不是证明某派更准确 |
| 平太阳时与真太阳时 | `solar_time.mean_solar` 是经度换算的坐标；`true_solar` 再加均时差 | 当前 time_basis 不单独创建平太阳时排盘分支；旧 `calculate` 保留平太阳时排盘，不能称为新真太阳主盘 | `solar_time.mean_solar/true_solar/eot_minutes`；旧 profile 的 `actual_method` | 比较新旧入口时先报方法；没有平太阳时新分支就不补其 P8 结论 | [TB](#source-tb)、[OLD](#source-old)：程序口径已核，传统采用依据未据此裁定 |
| 两种均时差实现 | 默认 NOAA/Meeus 公式不变；独立 Swiss 赤经与恒星时研究实现只作边界对照 | 对照不是更换默认，也不是独立天文实测；不修改共享 Swiss 全局选项 | `boundary_alerts` 的实现差异项、候选四柱、秒差与来源 | 两实现导致四柱不同时展示各自真实候选；只有数值微差时不捏造不同盘 | [TB](#source-tb)、[SW](#source-sw)：数值实现差异，不是两个命理流派 |
| 晚子换日 sect1 与 sect2 | P8 日时采用声明坐标，sect1 在23:00换日；年月及起运仍用物理 UTC+8 节界 | sect2 午夜日界用于具名敏感性对照；旧 v3/calculate 的 sect2 保持原状，不自动覆盖 | `pillars.day/hour`、`pillar_method`、`boundary_alerts`；间接影响十神和规则条件 | 真太阳时距23:00或00:00不超过15分钟时解释交界及实际两侧结果 | [DAY](#source-day)、[OLD](#source-old)：已核程序两套日界；未宣称某一历史版本唯一正统 |
| 时辰与节气交界 | M3 提示阈值：时辰边界±15分钟、子/晚子±15分钟、节气月交接±2小时 | 提示阈值是项目复核策略，不是把出生精度扩大成区间，也不倒推选一盘 | `boundary_alerts[].boundary_kind/alternatives/evidence_paths`；`time_basis` 的真实 UTC | 命中即提示实际边界与候选；支持范围边缘候选未计算时如实标记 null/未计算 | [TB](#source-tb)：原有±2分钟数值敏感性字段与新增±2小时复核提示用途不同 |
| 夏令时 gap / fold | 按显式 IANA 时区和实际读取的版本/字节 hash 转换：gap 无有效瞬间，fold 保留多个瞬间 | 不按宿主时区、不猜出生城市、不自动平移一小时，也不因真太阳时默认选择就猜 fold | `time_basis.instants[].status/utc/fold`、`timezone_source`、`requires_confirmation` | 无唯一物理时刻先核实出生记录；daily/window 等要求唯一瞬间的工具拒绝继续计算 | [TZ](#source-tz)：时区资料约定，不证明出生证明已核实；1986–1991锚点是软件校验 |
| 八字与紫微的晚子/月末 | 八字按上述 sect1；紫微保留固定 py-iztro 的晚子 index12、闰月等原生规则 | 不把紫微农历日和宫位强行改成八字换日结果；未新增另一套闰月流派开关 | `ziwei_column.lunar_date/ming_gong/shen_gong/palaces/wuxing_ju` 与四柱 | 即使四柱相同，紫微月末晚子与次日早子的宫位不同时仍并列 | [ZW](#source-zw)、[TB](#source-tb)：程序规则有记录，跨流派原刊依据待核 |

## 八字：表格、条件与项目分值分开

| 判断点 | 默认 / 已实现 | 可选或未实现 | 影响字段 | 何时向用户提示 | 来源及待核 |
| --- | --- | --- | --- | --- | --- |
| 月令人元司令两表 | 默认 `sanming_5520`，寅月戊5/丙5/甲20 | 可选 `xu_7716`，寅月戊7/丙7/甲16；其它月份各有整表，不能把7/7/16套到所有月 | `p8.month_command`、具名藏干、十神及依赖这些值的强弱/候选 | 表格使司令或藏干有差异时写明两表与当前所选；未实际算另一表时只讲选项 | [CMD](#source-cmd)：三命公开转录可定位；徐表仅登记 PDF第19页/零基18，原刊版次纸页待核 |
| 徐表申月“戊己土” | 原文歧义保留，使用徐表时须显式提供 `shen_earth=戊` 或 `己` | 项目不能自动裁定原文唯一用戊或己；逆司令次序定义本中余同样是项目归一规则 | 具名 options、hidden map、`month_command` 的所选干 | 未提供选择时拒绝，不借另表或模型知识暗补 | [CMD](#source-cmd)：原始图像、版本页及相邻上下文仍待核 |
| 两套旺衰诊断 | 同时给出月令/通根/透干法40/40/20、得令/得地/得势法40/30/30；45/55为项目阈值 | 没有名为“古籍40分法”的原典；未完整计合化、燥湿及制约力量 | `p8.strength.methods[]/agreement`、各 contribution | 两法分歧或临阈值时展示原因，不取平均制造一致，更不变成成功率 | [STR](#source-str)：古籍支持概念，权重、根气份额和阈值为项目定义 |
| 伤官牵制与庚辛例外 | 显式 P8 筛选看正官透出；庚辛日主保留金水例外 | 金水例外的完整季节、制化与救应未量化；旧 v3 的七杀牵制只为旧行为保护，不能当作同等已核异说 | `p8.patterns.regular_eight`、`rule_assessments`、`rule_hits` | 出现牵制条件时说明其具体前提；庚辛不套一般牵制，过筛仍只是候选 | [PAT](#source-pat)：24号修订与《真诠》第九、十四、四十一章公开转录；原刊待核 |
| 禄、劫、刃复合候选 | 38总规则保留35旧 ID，并加三条禄/劫/刃复合规则；每条三个子条件须全真才命中 | 没有缩成一个无条件标签；根气、制伏力量、救应等不因筛选通过就算完 | `patterns.regular_extra`、`condition_assessments`、`screen_passed` | 任一子条件不满足就讲缺项；单条件命中不说已成格 | [PAT](#source-pat)、[M4](#source-m4)：三子条件是项目显性筛选，原书完整条件待补 |
| 五阳刃与阴干异说 | 默认 `yang_only`，只给五阳干刃位 | 可选 `yuanhai_yin_included`：乙辰/丁未/己未/辛戌/癸丑；另 `yin_reverse_pending`：乙寅/丁巳/己巳/辛申/癸亥，但原典归属未核 | `p8.auxiliary_stars` 中所选表与实际星曜命中 | 阴干命中依赖选表时显式提示；逆行第三说不借《三命通会》卷五链接宣称已获原文证明 | [STAR](#source-star)、[M4](#source-m4)：第三说书名、版本、页码均待提供 |
| 天乙贵人异表 | 默认常用合表，庚丑未、辛寅午，不分昼夜 | 可选“庚辛逢马虎”合表，庚改寅午；可选曹氏阳贵/阴贵表，但不自动按日出选择 | 所选 tianyi option、对应星曜表与命中 | 庚干或阴阳贵表得出不同结果时讲清选表；未算日出就不说已经区分昼贵夜贵 | [STAR](#source-star)：公开转录可定位，原刊仍待校勘 |
| 扶抑、调候、格局用神 | `useful_candidates` 三组并列；`consensus_stems` 只是集合交集 | 不按多数票定唯一喜用；格局枢纽与扶抑所需元素不是同一问题 | `p8.useful_candidates`、`strength`、`patterns`、`climate` | 三组不同时说明各自在回答什么；交集空不变成命运优劣 | [USE](#source-use)：概念来源与项目筛选分别标注，未验证现实有效性 |
| 调候摘表与全文例外 | 120键为《穷通宝鉴》十干分论开篇摘表；保留实际定位和段落摘要 hash | 佐神和条件未全收；乙申现己/丙顺序是项目旧摘表，不否认总论丙/癸及条件例外；不声称实现《滴天髓》法 | `p8.climate.candidate_stems/source_locator`、候选分歧 | 使用摘表时先说范围；遇甲卯佐神、甲巳庚、甲未上半月癸等缺口不补算 | [USE](#source-use)、[M4](#source-m4)：网页 pN不是原刊纸页，异本及全文校勘待补 |
| 合、冲、刑、害、破 | 实际成员、位置和 `complete` 状态可计算；合化明确未成立 | 不完整三合/三会/刑组不能说全成立；六破是项目配对表，完整原典来源待核 | 交互图、`rule_hits[].context`、`transformation_established=false` | 条件不完整、两种作用并存或需要合化时说明，不直接转成事故/关系损害 | [REL](#source-rel)、[M4](#source-m4)：程序关系表与传统事件解释分离 |

## 紫微、西占：技术与时间层不得互相替代

| 判断点 | 默认 / 已实现 | 可选或未实现 | 影响字段 | 何时向用户提示 | 来源及待核 |
| --- | --- | --- | --- | --- | --- |
| 壬干化科表 | 默认 iztro2.5.0：壬禄天梁、权紫微、科左辅、忌武曲 | 宫干飞化可显式选 `quanshu`，仅壬科改天府；其它庚干异表未新增 | `p8_flying_transformations.table_id/edges/nodes`、`matches_named_table` | 壬干实际参与且落点不同，或所选表与引擎结果不一致时列明 | [ZW](#source-zw)：默认程序表已核；《全书》选项为24号裁定，原刊目标页尚未定位 |
| 生年、宫干、运限四化 | 生年保留本命星曜实际 mutagen；宫干给12宫×4的结构边；流年/月/日取引擎实际运限四化再映射本命宫 | 选宫干表不重写生年/运限；缺星、重复落点或未提供运限层须保留未解析/不可用，不造落点 | `ziwei_column`、宫干 edges、`daily_transit.data.ziwei` 的 temporal links | 三层不同，或 `matches_named_table=false`、落点未解析时区分说明 | [ZW](#source-zw)、[DAILY](#source-daily)：同一张盘的不同时间层，不是三份相互投票的证据 |
| 自化与飞星扩展 | 同宫自化定义为宫干所化星曜实际在本宫；忌的对宫只作索引加6的几何关联 | 向心/离心等完整飞星体系未实现，不从48条边推演未编码的事件法则 | `self_transformation`、`ji_opposition`、飞化边及来源宫/目标宫 | 用户问向心离心或事件应期时说明缺口，不能将简单同宫标记改名完整飞星法 | [ZW](#source-zw)：已核程序具名定义；其它流派原典版本与规则待补 |
| 热带与恒星黄道 | 当前为地心热带黄道，实际历表 flags/metadata 随结果保留 | 未实现恒星黄道或任何岁差基准选项；不能生成另一套星座度数作差异示例 | 行星 `longitude/sign`、`metadata/method` | 用户指定恒星黄道或拿不同黄道盘比较时说明当前不支持，不临时减一个常数 | [SW](#source-sw)、[AST](#source-ast)：库支持多坐标不等于项目全部已接入 |
| Placidus 与其它宫制 | 本命及太阳回归当前为 Placidus；失败显式拒绝，不默换宫制 | 整宫、等宫等未在本线暴露为计算选项；不输出假造的另一宫制落宫或优劣结论 | `houses/cusps/ascendant/midheaven`、行星 house、method | 高纬失败、时刻未知或用户要求另一宫制时先说明；解释实际当前 profile | [SW](#source-sw)、[AST](#source-ast)：古籍“行星之宫/守护星座”不替现代12宫算法背书 |
| UTC、UT1、TT 与旧本命 | 新具名西占模块从真实出生 UTC 转 UT1/TT，Moshier；不把真太阳坐标再当物理瞬间 | 旧 calculate 本命的旧民用偏移/UT近似保护不变；没有使用独立 IERS 实测数据来保证绝对时刻 | `actual_UTC`、各 `jd_ut1/jd_tt`、metadata；旧/新方法声明 | 新旧出现微差先说明时间标准与实现；不能判成用户出生资料错误 | [SW](#source-sw)、[OLD](#source-old)：这是数值版本边界，不是人格解释流派 |
| 行运快照、行运区间 | daily/旧快照是指定日北京时间12点；显式区间搜索才给进入/精确/离开、多次经过与截断 | 默认快照不能外推全天；有限步长搜索不宣称无遗漏；没有产物不由 Agent 插值 | `snapshot_at`、transits、`p8_transit_windows.windows/phases`、clip 标记 | 用户问“哪一天/几点”时先核当前是否为区间；截断边界与多次经过如实显示 | [AST](#source-ast)、[DAILY](#source-daily)：2秒括区间不是民用记录或历表的绝对准确度 |
| 次限、太阳弧、主限 | 顺行次限采用 `(目标JD_UT1−出生JD_UT1)/365.2422` 个历表日；默认相位容许度1° | 次限宫位为 null；逆行次限、太阳弧、主限未实现，不能互相改名 | `mapping`、`symbolic_ephemeris_at_UTC`、`progressed_planets`、`houses` | 先说符号映射而非目标日实际天空；问次限落宫就说明当前没有 | [AST](#source-ast)：日返一年有具名资料，365.2422固定系数是项目约定，不冒称所有软件一致 |
| 太阳回归与回归地点 | 由指定 return_year 求热带太阳回归根；明确传入经纬度计算 Placidus 宫位 | 未代选“出生地/现居地哪个更准”，未实现其它回归宫制；高纬失败不回退 | `root/actual_UTC/houses.location`、回归年与周年锚点 | 地点未确认、生日闰日锚点截断、跨公历年或宫制失败时说明实际方法 | [AST](#source-ast)、[SW](#source-sw)：数值求根不证明某地点解释的预测效度 |
| 容许度 | daily/window 的相位默认2°；次限默认1°；本命/回归实际值按其 profile 或明确参数 | 未宣称全流派统一容许度；不为迎合解释暗改阈值或把多个技术的 orb 混用 | `orb_limit_degrees/orb_degrees/aspect_orb_degrees` 与实际角距 | 贴近阈值或跨工具比较时同时报角度、容许度及技术名 | [AST](#source-ast)、[DAILY](#source-daily)：几何条件可核，取舍为项目具名选择 |

## 塔罗与面向行动的工具

| 判断点 | 默认 / 已实现 | 可选或未实现 | 影响字段 | 何时向用户提示 | 来源及待核 |
| --- | --- | --- | --- | --- | --- |
| 原创牌义与历史文本 | 当前78张×正逆位为 `zhiming-editorial-2026-10-10-v1` 原创编辑牌义；RWS序号力量8、正义11 | 不是 Waite 原文逐字翻译；没有实现 Marseille/Thoth 牌义互换，不把原创词句伪称古典原文 | 固定 draw 中 card 的 version/source/upright/reversed 与 deck | 用户问传统出处或其它牌系时先分清牌组、编辑版本与历史参考 | [TAR](#source-tar)：Waite 原著公开文本可定位，当前牌义仍按逐卡 provenance 识别 |
| 逆位与过程读法 | 先读实际 `reversals` 与固定 `orientation`；历史 Waite 有独立逆位条目，不全是正位反义 | 受阻、过量/不足、向内、延迟为项目解释框架；关闭逆位不追加“能量逆位” | 冻结牌阵 orientation、upright/reversed/misreading | 选择过程读法须有牌位及已知现实支持；方向不明保留不确定，不能靠重抽求确定 | [TAR](#source-tar)：历史原文与项目白话分开，不继承历史健康/灾祸断语 |
| 黄历日历标签与个人流日 | `almanac` 为北京时间民用日、正午构造、lunar-python1.4.8宜忌 sect1；不套出生真太阳时 | 库有 sect2精确交节月口径，本接口未开放切换；值神“吉”和建除“破”可同时保留 | `almanac.data.ganzhi/duty/yi/ji/method`；与 daily 月柱用途分开 | 交节日与流日月柱不同，或标签表面冲突时说明口径，不能删除一项制造一致 | [ALM](#source-alm)：库一致性已核，特定原刊通书全表未校勘 |
| 择日分数与传统条件 | `project-six-purpose-ranking-v1` 按六用途权重，年/月/日层因子1/2/3；全区间透明排序 | 权重不是古籍量化择日法、概率或精确吉时；未完整纳入通书神煞等体系 | `window_search.data.weights/ranking_summary/candidates` 的正负/中性命中与 contribution | 展示分数时同时给真实条件和项目权重，现实约束优先；同分按日期，不制造优劣断语 | [WIN](#source-win)：项目表是分值出处，不能借盘面古籍来源替分值背书 |
| 合盘互补与关系结论 | 日干/地支成员、西占跨盘几何相位和紫微夫妻宫对读按具名方法计算；先要求 `consent=user_confirmed` | 五行互补、三组喜用候选互补不是同义词；不支持由合盘推出关系成功率、婚姻或他人意愿 | `synastry.data` 的候选、对读与 method；每条真实 hit/source | 候选分歧就逐条说；无他人资料同意时计算前拒绝，不把来源选择误当授权 | [SYN](#source-syn)：结构和产品互补定义已实现，完整合婚流派原典及现实效度待核 |

## 提示与依据引用的共同约束

只有实际输出存在的条件才能成为本轮 `rule_hits`；`met=true` 只表示成员或数值条件满足。
未命中项留在 assessments，不能给它编出命中 r 别名，也不能把未实现另一派包装成“反证”。
同一问题存在不同已计算分支时，分别引用其 document、branch、basis 和版本；
不能跨盘套用另一个分支的 `〔c#〕〔r#〕`。

白话措辞模板：“这次按真太阳时得到的条件是……〔c#〕；北京时间那份有……差异。
我们把两边的依据放在一起看，先核实记录，不用一条条件替你下人生结论。”
此处 `#` 只是格式，不是已经注册的实际别名。使用前须从当次结果取得数字。
塔罗沿用固定牌阵的实际 `〔t#〕`，本表不替它伪造 charts c/r。
本文件无模型解读验收，不写结果保证；倒推继续实验、默认隐藏，证据不足时诚实拒绝。

## 来源、定位与存疑 / 待核

以下定位支持对应范围；网页/程序源码不等于已获得古籍原刊影印页。
待核项继续登记于 [M4资源清单](../evidence/P8/night28-m1-m4-review.md)，
需要书名页、版本页、目标段及前后页，电子页序与书内纸页分别记录。

<a id="source-tb"></a>
**TB — 时间基础及交界。** 本地 [time_basis_solar.py](../../../mingjing_core/adapters/charts/time_basis_solar.py)、
[time_basis_candidates.py](../../../mingjing_core/adapters/charts/time_basis_candidates.py)、
[time_basis_readout.py](../../../mingjing_core/adapters/charts/time_basis_readout.py)、
[boundary_alerts.py](../../../mingjing_core/adapters/charts/boundary_alerts.py)、
[chart_compute v1.1契约](chart_compute.md)。天文公式入口为
[NOAA计算说明](https://gml.noaa.gov/grad/solcalc/calcdetails.html)。
默认依据为本项目23号/28号裁定；独立均时差比较只证明方法条件差异，不证明哪派预测有效。

<a id="source-old"></a>
**OLD — 旧入口保护。** [Charts说明](../../../mingjing_core/adapters/charts/README.md)列平太阳时、
八字 sect2、原生紫微晚子与旧西占方法；[chart_compute契约](chart_compute.md)分别标明入口。
保留旧行为是版本兼容决定，不替旧牵制规则添加未经核准的历史依据。

<a id="source-day"></a>
**DAY — 八字日界程序。** 本地 time_basis_candidates 显式 `setSect(1)`；
[lunar-python1.4.8 EightChar源码](https://raw.githubusercontent.com/6tail/lunar-python/v1.4.8/lunar_python/EightChar.py)
可核 `getDay` 的 sect 分支；小时柱仍按该库独立入口，不能只手改日期后自行拼时干。
此为程序定义来源，不提供某一古籍原刊日界的校勘结论。

<a id="source-tz"></a>
**TZ — 时区资料。** 本地 [time_basis.py](../../../mingjing_core/adapters/charts/time_basis.py)、
[time_basis_zones.py](../../../mingjing_core/adapters/charts/time_basis_zones.py)记录实际数据选择、IANA版本和字节 hash；
[日期属性研究](../evidence/P8/night28-date-properties.md)包含夏令时锚点与测试局限。
没有把固定偏移、当前 OS 设置或时区库一致性当作真实出生记录认证。

<a id="source-cmd"></a>
**CMD — 司令与藏干两表。** [schools.json](../../../mingjing_core/knowledge/p8_bazi/schools.json)、
[named_bazi.py](../../../mingjing_core/adapters/charts/named_bazi.py)；
[《三命通会》卷二·论人元司事公开转录](https://zh.wikisource.org/wiki/三命通會/卷二#论人元司事)；
[徐乐吾《子平真诠评注》PDF](https://www.anhappy.com/share/books/others/books/%E5%9B%BD%E5%AD%A6/%E5%AD%90%E5%B9%B3%E7%9C%9F%E8%AF%A0%E8%AF%84%E6%B3%A8.pdf)。
后者登记 PDF第19页（零基18），不是已核原刊纸页；原刊版本与申月异文仍待核。

<a id="source-str"></a>
**STR — 旺衰项目权重。** [技能02](../../../mingjing_core/skills/bazi/02_strength.md)、
[named_strength.py](../../../mingjing_core/adapters/charts/named_strength.py)为实际权重来源。
《子平真诠评注》第六章“得时不旺失时不弱”及《三命通会》卷二仅作为概念定位；
不能将45/55、40/30/30或根气份额标为原典数字。原刊版次页码待核。

<a id="source-pat"></a>
**PAT — 格局条件。** [技能03](../../../mingjing_core/skills/bazi/03_patterns.md)、
[rules-review.md](../evidence/P8/rules-review.md)、
[p8_structure.py](../../../mingjing_core/adapters/charts/p8_structure.py)。
《子平真诠》第九、十四、三十九、四十一、四十三、四十五/四十六章为已登记概念定位；
完整季节、力量、救应与原刊校勘未完成，项目筛选不等于原书全部成败判定。

<a id="source-star"></a>
**STAR — 刃与天乙异表。** [schools.json](../../../mingjing_core/knowledge/p8_bazi/schools.json)；
[《命理探源》公开转录](https://libokang.com/zh-hant/classics/bazi/命理探源/)中天乙/羊刃；
[《神峰通考》公开转录](https://zh.wikisource.org/zh-hans/神峰通考)吉神类·天乙贵人。
阴刃逆行第三说未找到原典依据；
[《三命通会》四库本卷五](https://zh.wikisource.org/wiki/三命通會_(四庫全書本)/卷05)
只是排查对象，不是该表已核的证明。以上转录对应原刊版次与纸页均待核。

<a id="source-use"></a>
**USE — 三候选与调候。** [技能04](../../../mingjing_core/skills/bazi/04_climate-useful.md)；
[《穷通宝鉴》十干分论公开转录](https://zh.wikisource.org/zh-hant/穷通宝鉴)，
尤其 [三秋乙木](https://zh.wikisource.org/zh-hant/穷通宝鉴#三秋乙木)总论、七月段与相邻条件段；
《子平真诠评注》第十四/十五章支持概念区分。120键佐神、例外和异本未全收，
网页抽取 pN不是纸页；《滴天髓》寒暖/燥湿仅为待核方向，不作已实现候选来源。

<a id="source-rel"></a>
**REL — 干支交互。** [p8_interactions.json](../../../mingjing_core/knowledge/p8_interactions.json)、
[interactions_bazi.py](../../../mingjing_core/adapters/charts/interactions_bazi.py)与
[《三命通会》卷二](https://zh.wikisource.org/wiki/三命通會/卷二)概念定位。
六破配对仍标项目表，支持全部配对的原典书名/版本/页码待核。

<a id="source-zw"></a>
**ZW — 紫微具名表与时间层。** [flying_v1.json](../../../mingjing_core/knowledge/p8_ziwei/flying_v1.json)、
[time_basis_chart.py](../../../mingjing_core/adapters/charts/time_basis_chart.py)、daily_transit_ziwei；
[iztro v2.5.0天干表](https://raw.githubusercontent.com/SylarLong/iztro/v2.5.0/src/data/heavenlyStems.ts)、
[同版本宫位实现](https://raw.githubusercontent.com/SylarLong/iztro/v2.5.0/src/astro/FunctionalPalace.ts)、
[官方运限说明](https://docs.iztro.com/posts/horoscope)。运行时以固定安装包源码指纹为准，当前网站新版功能不自动加入。
[《紫微斗数全书》卷二](https://zh.wikisource.org/wiki/紫微斗數全書/卷二)目标四化口诀段、所据版次及页码待定位；
不将24号的可选表裁定写成已独立校勘40格。完整飞星流派资料也待补。

<a id="source-sw"></a>
**SW — 数值坐标与时间标准。** [Swiss Ephemeris程序说明](https://www.astro.com/swisseph/swephprg.htm)
§3（位置与flags）、§9（时间换算）、§12（恒星模式）、§15（宫位）；
[astro_ephemeris.py](../../../mingjing_core/adapters/charts/astro_ephemeris.py)是项目实际选项来源。
库提供一种技术不等于项目接入它，也不为文化解释或预测提供效度依据。

<a id="source-ast"></a>
**AST — 西占技术。** [技能01](../../../mingjing_core/skills/astro/01_natal.md)、
[技能03](../../../mingjing_core/skills/astro/03_transits-progressions.md)、
[技能04](../../../mingjing_core/skills/astro/04_returns.md)、
[astro_progressions.py](../../../mingjing_core/adapters/charts/astro_progressions.py)、
[astro_returns.py](../../../mingjing_core/adapters/charts/astro_returns.py)。
[Astrodienst图种说明](https://www.astro.com/faq/fq_fh_owtype_e.htm)支持日返一年概念；
已登记 Alan Leo《The Progressed Horoscope》附录IV为变体讨论定位，具体原版纸页待核。
托勒密《四书》Book I入离相、行星性质及守护星座不替 Placidus、外行星或365.2422参数背书。

<a id="source-tar"></a>
**TAR — 原创牌义与逆位历史。** [tarot_meanings.json](../../../mingjing_core/knowledge/tarot_meanings.json)、
[逆位技能](../../../mingjing_core/skills/tarot/06_reversals.md)；
[Waite《The Pictorial Key to the Tarot》Part III §3公开文本](https://sacred-texts.com/book/the-pictorial-key-to-the-tarot/section-3-the-greater-arcana-and-their-divinatory-meanings)
列历史正逆位与力量8/正义11。当前数据的原创版权/编辑来源依每张记录识别，
不是 Waite 逐字译文；过程性解释与现代白话不伪称历史原文。其它牌系完整对照未实现。

<a id="source-daily"></a>
**DAILY — 具名流日。** [daily_transit契约](daily_transit.md)保存快照、容许度、时间层和真实依据规则；
相位阈值、采样时刻和库版本是可核程序约定，不据此推出事件发生率。

<a id="source-alm"></a>
**ALM — 黄历。** [almanac契约](almanac.md)、
[lunar官方API](https://6tail.cn/calendar/api.html)、
[v1.4.8 Lunar.py](https://raw.githubusercontent.com/6tail/lunar-python/v1.4.8/lunar_python/Lunar.py)。
冲煞等库一致性与不变量检查不等于独立历史通书校勘；未取得特定原刊版本和页码。

<a id="source-win"></a>
**WIN — 透明择日。** [window_search契约](window_search.md)、
[p8_windows_v1.json](../../../mingjing_core/knowledge/p8_windows_v1.json)是实际权重和层因子出处。
没有取得古籍对这些数字的支持，也没有真实事件或专家盲评证明排序有效。

<a id="source-syn"></a>
**SYN — 合盘与他人资料。** [synastry契约](synastry.md)明列 consent、方法、三候选和局限。
干支/黄经/十二宫的程序结构来源不提供关系结局保证；完整合婚、紫微跨盘流派原刊及页码待核。

<a id="source-m4"></a>
**M4 — 原刊资源待核。** [M1/M4审阅及资源清单](../evidence/P8/night28-m1-m4-review.md)
保留每项所需书名、版本信息、目标篇段与未知纸页。缺资料期间不放宽规则门槛，不启动冻结倒推。

本次仅新增静态对照文档；没有新算另一种黄道、宫制、飞星体系或历史异表，也没有模型请求。
仍待主线将这些差异提示接入面向用户的流程，并由大脑补齐原刊后逐项复核。
