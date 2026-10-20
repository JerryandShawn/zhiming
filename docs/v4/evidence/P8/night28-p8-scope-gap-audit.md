# P8正式范围差距盘点：33号第二节第2项

盘点时间：2026-10-21T00:23:53+08:00（北京时间）；工作树zhiming-v4-p8，v4/p8-calc，读取时HEAD a92b889815c7cc1c969f6aaa5d4dac5c44816548，仍有父代理待发布增量。

本盘点只读源码/设计/既有证据，仅新增本文；没有运行测试、Charts、模型、网络、数据库或服务器，也没有改动被冻结的源/测试/Schema/样例。最近495定向和2143全量另有既有证据，不能当成本盘点新跑。

## 已完整阅读的设计与优先规则

- `05_Codex提示词/P8_命理能力重建.md`：LF SHA256 `01678104ca5d306f4c19aa0263e7701c6bda2febe9fb00d93629d6a3386a4c80`。
- `18_提示词增补包/P8_增补_推理架构与E2.md`：LF SHA256 `a12da44464f265774cdc6ef58594383c52167e762d49c385056925766a22aac1`。
- `指令板/meta.md`：LF SHA256 `b136b7951f87417f960a1a242b5e541fbcf551b127dabe6428b6f4e03b06b838`。

原P8目标为计算补全、四体系技能、知识校验、专科、旧分析重算；增补明确§A/B/技能/E2脚本归命理线，§C专科/§D合参/§E档案投票、Context/registry接线与全部E2真实调用归主线。后续用户/23号冻结裁定优先：有准确出生记录，默认真太阳时、北京差异并列，倒推实验冻结隐藏、诚实拒绝，不重新启用旧前三/合成命中率设计。meta指令板v1规定本周队列顺序，未授权额外外部访问。

## 能力逐项：有代码不等于已完成正式业务验收

| 原要求 | 当前本机事实与入口 | 剩余/限制 |
| --- | --- | --- |
| 藏干角色/月令司令/十神全表 | named_bazi: options/hidden_for/named_command/named_ten_gods，sanming_5520与xu_7716具名；申月戊/己需显式选择 | 已计算；司令表原刊版页/异文仍待核，不当作唯一传统标准 |
| 旺衰两种口径 | named_strength.named_scores分别输出月根透干与得令地势分/结论、method/参数/分歧 | 已计算；权重及45/55为项目诊断，不是完整传统强弱或现实校准 |
| 八正格/从格/建禄月劫阳刃 | named_patterns + p8_structure.reviewed_regular/reviewed_extra；八格、从财/从杀/从儿/从旺条件、三种regular_extra | 已计算候选；合化、救应、力量、杂气透会、真假从格/特殊外格/岁运成败未实现，不得宣传完整成格 |
| 调候120键/三种喜用 | climate.json120键、climate_review；reviewed_useful分扶抑/调候/格局及交集分歧 | 是开篇/季节摘表；所有full_original_collation/full_chapter_conditions_implemented均非已完成；佐神和条件例外未全收 |
| 十步大运/流年流月流日/神煞≤10 | calendar_layers.decades十步与显式目标层；named_stars8类具名标记 | 已计算；getYun sect1名义日历区间不是精确应期，神煞只是辅助；阴刃第三原典待核 |
| U2交互表 | interactions_bazi有五合/克、冲合害破、自刑及三合/三会/三刑群组，nodes十神；metadata提供palace/domains/按流派priority确定排序 | 已计算；不输出合化成立，六破出处/宫分年龄与领域映射仍有待核和项目标签 |
| U12条件命中 | 38规则，6种condition_ref；保留原35ID+3复合各3条件，engine仅输出true hits并保留全assessments | 本线已实现；原函数路径放adapters/charts/rules而非设计示意calculations/bazi/rules；前10领域注入、持久别名账本/used_claim_ids归主线 |
| 紫微生年/宫干飞化/自化/忌冲/三方/四时间层 | ziwei_flying实际12宫48边、natal标签、temporal_layers；旧原生horoscope与linked_palaces保留 | 已计算具名默认；quanshu仅纯函数可选，公开adapter无选表参数；没有向心/离心、自化强弱或连续转忌 |
| 西占行运区间 | P8ChartAdapter(transit_period=...).calculate -> interactions_transits.transit_windows；entry/exact/exit及裁剪 | 已计算；有限步长可能漏切触/短窗口，2秒括区间不是天文物理精度；主线参数/别名接线待做 |
| 次限推运/太阳回归 | western_timing显式入口；顺行365.2422 UT1日映射，太阳回归精确黄经根+显式地点Placidus | 已计算当前具名技术；推运宫位None、逆行次限/太阳弧/主限未实现；高纬错误拒绝，不换宫制 |
| time_basis/U9准确记录 | P8ChartAdapter.time_basis；时区/DST缺失折叠、标准/真太阳/北京比较、秒级、sect1/紫微晚子分列；v1.1 boundary_alerts | 已计算；保存/确认/界面归主线；事件倒推继续冻结，没有以新证据启用的决定 |
| 日课/择日/黄历/合盘追加 | daily_transit/window_search/almanac/synastry；4 adapter/worker路由、4契约Schema、真实合成样例和局部真实c/r | 已实现纯计算；用户consent必须先于对方计算，字段不是外部授权证明；无主线工具/产品入口；排序分不是结果保证 |
| U3命理档案 | profile_draft.profile_proposal带版本、branch、revision、实际值/Pointer/方法与改判理由，writes0 | 仅只读提案；持久化/确认/稳定度k3模型投票/日常上下文一致性归主线，不能称档案保存完成 |
| P8§C/增补§A5 contradictions | consistency.check_chart_consistency刚交付六字段明确语法预览495定向；registry旧claims_for/revalidate仍保留 | 本线还缺38规则名称/ID与met=false直接核对、≥10正反例；主线尚无registry/review15接线，旧RULE_GAP不会自行降级 |
| consult_specialist/U13/U14/U15 | 本工作树没有mingjing_core/agent目录；E2只是配置请求计划/替身，不是实际subagent | 专科JSON/别名丢弃/重试/SRP/额度、合参、档案投票和Context均归主线，不能据脚本称完成 |
| 旧分析重算 | 本线未实现tools/reanalyze_legacy.py或任何apply迁移 | 按用户边界不做资料写入；P5原话/撤销/回执与dry-run/apply流程归主线，stage需另授权 |

## 技能格式与chart_skill：核到哪一层

五个SKILL.md实际读过全文，32章用静态文本读取核目录、章节结构、字段/来源声明及预算；没有用“有32个文件”替代格式检查。基础四体系10/6/5/7，calendar-tools新增4。五入口frontmatter有name/description、name与目录同名，body有实际章节链接；32章均有方法步骤、字段、流派分歧、前提、反例、表达、rule_id列表、末尾出处/待核。

这只证明本项目最小开放格式形态和内容结构存在；本轮没有运行Agent Skills官方验证器，没有再次联网比对规范版本，也没有模型宿主加载/工具发现验收。name/description本身不是所有规范约束与语义质量的证明。当前catalog仍标draft_requires_owner_review。

loader完整读过：allowlist体系/topic；load一次读单章，返回正文、metadata、版本、正文SHA、完整<技能>块；chapter metadata采用deepcopy；拒目录穿越/超预算，不执行章节代码。它不核本次命盘是否满足required_fields、不负责owner/撤销、不把示例别名注册为实际依据。字段存在性只有既有原生测试/特定样例验证，主线必须按artifact_root/conditional_fields挑对实际产物再解析真实Pointer。

静态按loader精确拼接公式重算上下文大小，32章范围2682–5138 UTF-8字节，最大bazi/patterns 5138；均小于5500字节代理预算。不是实际Kimi tokenizer token计数，正式≤6000 tokens预算仍由主线模型适配层核。旧章节v2.2与catalog v2.3是保留旧章节、追加calendar-tools；不能把目录版本升级说成32章文字全部重审。

| 体系/topic | 静态上下文字节 | 根对象 | 声明pending |
| --- | ---: | --- | --- |
| bazi/basics | 5117 | CalculationArtifact | 无(不代表全部接线完成) |
| bazi/strength | 2905 | CalculationArtifact | 无(不代表全部接线完成) |
| bazi/patterns | 5138 | CalculationArtifact | 无(不代表全部接线完成) |
| bazi/climate-useful | 5081 | CalculationArtifact | 无(不代表全部接线完成) |
| bazi/time-layers | 4054 | CalculationArtifact | 无(不代表全部接线完成) |
| bazi/life-topics | 3247 | CalculationArtifact | 无(不代表全部接线完成) |
| bazi/misreadings | 3419 | CalculationArtifact | 无(不代表全部接线完成) |
| bazi/rectification | 4196 | P8ChartAdapter.time_basis read-only envelope | 有 |
| bazi/rectification-rules | 4558 | P8ChartAdapter.time_basis read-only envelope | 有 |
| bazi/traditional-hour-methods | 3345 | P8ChartAdapter.time_basis read-only envelope | 有 |
| ziwei/palaces | 3481 | CalculationArtifact | 无(不代表全部接线完成) |
| ziwei/major-stars | 2971 | CalculationArtifact | 无(不代表全部接线完成) |
| ziwei/mutagens | 4144 | CalculationArtifact | 有 |
| ziwei/combinations | 2816 | CalculationArtifact | 无(不代表全部接线完成) |
| ziwei/time-layers | 3394 | CalculationArtifact | 无(不代表全部接线完成) |
| ziwei/misreadings | 2911 | CalculationArtifact | 无(不代表全部接线完成) |
| astro/natal | 2789 | CalculationArtifact | 无(不代表全部接线完成) |
| astro/aspects | 3069 | CalculationArtifact | 无(不代表全部接线完成) |
| astro/transits-progressions | 5017 | CalculationArtifact | 有 |
| astro/returns | 4366 | CalculationArtifact | 有 |
| astro/misreadings | 2712 | CalculationArtifact | 无(不代表全部接线完成) |
| tarot/major | 2702 | TarotService.get_for_reading public draw | 无(不代表全部接线完成) |
| tarot/minor | 2891 | TarotService.get_for_reading public draw | 无(不代表全部接线完成) |
| tarot/court | 2682 | TarotService.get_for_reading public draw | 无(不代表全部接线完成) |
| tarot/spread | 2998 | TarotService.get_for_reading public draw | 无(不代表全部接线完成) |
| tarot/relations | 2829 | TarotService.get_for_reading public draw | 无(不代表全部接线完成) |
| tarot/reversals | 2846 | TarotService.get_for_reading public draw | 无(不代表全部接线完成) |
| tarot/misreadings | 2800 | TarotService.get_for_reading public draw | 无(不代表全部接线完成) |
| calendar-tools/daily-transit | 3311 | P8ToolEvidenceResult | 有 |
| calendar-tools/window-search | 3291 | P8ToolEvidenceResult | 有 |
| calendar-tools/almanac | 3027 | P8ToolEvidenceResult | 有 |
| calendar-tools/synastry | 3517 | P8ToolEvidenceResult | 有 |

## 独立计算证据与正式验收缺口

已有calc-crosscheck.md记录教材柱/手算、72日期×4柱sxtwl参考；规则有38条正反例和3公开教材四柱快照。西占tests/test_p8_astro_native.py用16个缓存NASA/JPL Horizons位置、回归插值/Swiss另一路算法、几何恒等式等21原生检查；本盘点未重新联网或运行它们。紫微飞宫有安装库fliesTo/mutagedPlaces/selfMutaged一致性、日四化1000日期/4000落点独立实现，但仍共享本命星位/表源/甲子锚，不等于独立第二引擎/古籍真值。

28日期研究真实1000唯一随机日期+12DST锚、2026–2027全部730日daily与730次公开window/24月分页均已有脚本报告；这不验证古籍/软件跨平台/预测准确。原P8“所有新增项与至少独立来源逐项核对”的正式口径尚不能一笔验收：规则力量/救应和调候全文未实现，紫微跨流派独立校盘未完成；图书版次页码M4十项仍待核。应分别写库一致性、独立算式、缓存外部参考、原刊待核，不合成“计算全部准确”。

skills-review.md保留28章旧状态并在顶部提示后续；正文仍有35条/宫干未接/推运尚未接的历史句。本次新盘点与night24/night28增量才是当前状态，建议后续追加单一当前索引，不改写旧证据当时事实。

## E2与不允许跨越的门槛

E2 v2提供C0/C1/C2/C3/C4a/C4b、选项乱序、同案例会话、Wilson/配对差/McNemar/截尾，3合成题脚本路径存在，不是真实Agent。最新M2清点2025赛季80题，纳入14(9 MingLi+5 BaziQA)，排除66(61无明确目标年、5年份未解)；题目目标年不等于赛季年，当前无题目标年为2025。2025缺标签排除0；全源其它赛季缺标签另计，不改分母。

严格同目标年控制历史失败保留；宽松同源跨案例固定seed和无盘各14只做结构演练。宽松2/14 donor出生晚于目标年，时间预检已如实报告，未重抽/删题/改seed；专业模型分数与区间null。真实排盘输入补全、题面泄漏复核、主线配置/额度与真实调用均未完成且本周禁止本线执行。没有证据说安慰剂准确率下降或深度模式值得默认开启。

## 建议下一动作（不等待睡觉用户）

1. 命理线优先补新增 checker 的显式U12规则名/ID断言：仅按同受信信封、同主分支的rule_assessments布尔值检查；区分“条件命中”和“已成格/完整夺食/制杀有效”，未知名字/多匹配/引用否定仍待核，保留真实c/r/false无r。至少10正例+10反例及反讽/时间口径/归属边界，新增Schema/样例与既有495保护。不要扩大为自由语义判官。
2. 在现有skills结构上做正式来源/格式清单与单一当前入口审阅，逐章对接当前根对象/可选能力；仅用本机已有材料，不编版页、不安装新validator/依赖、不以目录数冒领全量合规。
3. 可离线扩大独立历法/西占参考和异常边界；完整古籍条件/异派必须有可核原文版本才实现，缺资料列M4待决并切换储备。
4. 向主线交现有工具契约、词典/学习/一致性和明确未接线项；主线负责registry/review15、领域前10命中、专科/合参/档案/旧分析迁移。命理线不越界改agent或数据。

倒推冻结、真实模型0、服务器0、不合并不变；本盘点不授予下一个开发任务的额外修改权限。
