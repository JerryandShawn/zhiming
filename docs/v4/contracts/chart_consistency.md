# 命盘文本一致性检查草稿 v1

版本`p8-chart-consistency-preview-v1`，用于33号§2第3项、主线review #15的
`chart_inconsistency`输入候选。当前为本机纯规则预览，**主线尚未接入**。

## 调用与信任边界

    check_chart_consistency(answer_text, chart_compute, *, expected_scope=None)

实现`mingjing_core.skills.consistency`，不调用模型，不读取时钟、数据库或网络，
不自动阻断、重写或重新生成回答。`policy=record_only`，由主线决定review流程。
`answer_text`须为字符串，最多32000个Unicode码点；空文本可接受，结果为`not_checked`。
结果只保留码点偏移`span.start/end`和有限枚举断言值，不返回正文摘录或正文散列。
偏移不能直接按UTF-16索引使用，前端须转换；它不是原始字节位置。

`chart_compute`须为受信计算提供方交付的现有`p8-chart-compute-preview-v1`或`v1.1`信封，
复用`learning_input.verified_input/resolve_ref`核文档、指针、别名、branch/basis、
规则来源和真实主盘投影。八字、紫微只读native `true_solar`主视图；西占读实际UTC本命盘。
**内容hash不是签名/鉴权**：主线必须先校验来源、当前owner、subject、修订与撤销，
再传完整`expected_scope`作四键严格类型/值比较。可选参数省略不表示已完成授权。
不把同名〔c1〕当作跨信封通用证据，也不从词典、自然语言或旧答案回填缺失字段。

## 可核的有限中文语法

| 字段 | 明确支持的例式 | 实际读取与限制 |
| --- | --- | --- |
| 日主/日干 | `日主是丁火`、`日干不是甲` | `pillars.day.gan`；木火等后缀须与干一致 |
| 格局筛选 | `正印格候选筛选通过`、`正官格筛选未通过` | `p8.patterns.regular_eight[].screen_passed`，只支持八正格；不表示已经成格 |
| 用神候选 | `调候候选天干包括甲`；`扶抑[p8-month-root-exposed-v1]候选天干不包括乙`；`格局[正印格]候选天干包括壬` | 分方法读candidate_stems；未指定方法且候选集合不同即待复核，不做投票或union定用神 |
| 大运 | `第3步大运是庚午`、`2026-10-21的大运不是辛未` | 具名`decades[].index/ganzhi/nominal_start_at/nominal_end_exclusive`；ISO日期整天必须落同一北京时间半开名义区间，交运当日待复核；不猜“今年/现在/32岁” |
| 紫微主星 | `夫妻宫主星包括紫微`、`命宫主星不含天府`、`田宅宫是空宫` | 该宫实际`major`；“是某星”按包含而非唯一处理；不读对宫借星/三方，不把辅星当主星 |
| 西占位置 | `本命太阳在双鱼座`、`本命金星在第12宫`、`本命太阳在双鱼21.2度`、`本命木星逆行` | 必须明确本命；读planets实际sign/house/longitude/retrograde；黄经模30，不使用截断整数，写出精度对应半个末位单位容差；宫位依输入宫制 |

可使用“你/你的/本盘/此盘/该盘/我/我的/本信封display_name”的有限前缀。
直接否定仅支持相邻的`不是/并非/不在/不含/没有`等白名单形式；未知语法不靠关键词猜语义。
每个明确断言按句号、分号、换行分句，再按逗号分子句；问号保留为语气守卫。
别名格式仅支持`〔cN〕/〔rN〕`，必须在原信封存在并覆盖当前字段；错误/不相干引用待复核。

## 保守守卫与结果含义

引用或转述、含未闭合引号/多句引号、代码引用、条件假设、疑问、多重或复杂否定、
不确定/待核、他人资料、旧盘、北京时间/另一口径比较、行运/流年/次限等其它层，
均为`needs_review`，不会按主盘直接判冲突。守卫在逗号分割前作用整句，
避免“如果A，B”的B脱离条件。即使输入已有北京时间比较视图，当前版本仍不自动解析比较句。
“小禾的命盘如下/北京时间结果/旧盘”等明确标题会把保守守卫传递到同一段落后续句，
遇空行或明确`以下为本盘真太阳时主盘`才清除；无法识别的任意自然语言标题仍属召回限制。
句末`不成立/说错/才怪`等显式撤回或纠错表达也守卫整句，不拆出前半句硬判矛盾。
含糊归属、八正格之外格局、未实现语法和缺字段属于低召回边界。

`已成格/用神已定/唯一用神`没有被候选筛选支持，保持`needs_review`；
不会把它们简单改写成“未成格/无用神”，更不会以候选未通过断言任何现实结果。

单项`outcome`是`matched/contradiction/needs_review/not_checked`。
总体优先级为：有明确矛盾→`inconsistent`；否则有待复核→`needs_review`；
否则至少一项已核→`no_contradiction_found`；其它→`not_checked`。
**no_contradiction_found只表示已识别的断言未发现冲突，不表示全文正确或已全部检查。**
缺字段、缺实际c证据、其它体系字段不推断；多主分支或方法值不同保留待复核。
`coverage`只数识别到的子句，不能用作全部自然语言的召回率或准确率。

## 输出与两套证据命名空间

自包含Schema为[chart_consistency.schema.json](chart_consistency.schema.json)。
输出采用既有tool_evidence信封：`version/scope/document_id/data/rule_hits/aliases/sources/effects/limits`。
`data.checks[]`保留`span/field/outcome/reason_code/assertion/expected_values`，
真实`source_refs`、原盘`input_c_aliases/input_r_aliases/input_citations`及`fact_sources`。
`data.input_aliases`是原信封使用到的实际别名原样副本；验证它仍需原始受信chart_compute。

顶层`aliases.c/r`为**这个检查结果自己的临时命名空间**，真实指针绑定`data.checks[]`
及具名`p8.consistency.*`文本比较/守卫规则，SHA256与claim_id按tool_evidence规则生成。
这些r只说明执行了某项比较或保守守卫，不是传统命理规则命中，也不说明格局/用神成立。
顶层c1与`data.input_aliases`的c1可能是两件事，主线登记时须按document_id映射，不能混用短名。
输入的原生命理r仅在明确引用且实际证据覆盖当前字段时附带；不会为凑命理引用新造r。

## 错误与交付样例

| ValueError码 | 含义 |
| --- | --- |
| `consistency_answer_invalid` | 非字符串或超过32000码点；错误消息不含正文 |
| `consistency_chart_invalid` | 原信封内容/引用/主视图/版本/隔离校验失败 |
| `consistency_scope_mismatch` | expected_scope不完整、类型或值与当前信封不同 |
| `consistency_chart_fields_invalid` | 已受信信封的所读字段结构不能安全读取 |

合成阿远样例`consistency-ayuan-{bazi,ziwei,astro}.json`，与同目录`ayuan_*.json`
同一输入文档。样例仅保存人工写的合成短断言，不含真实用户原文；用于主线接口审阅，
不能充当盲测或语义理解效度证据。运行结果和边界复核见`night28-consistency-review.md`。

尚未验证：主线review #15真实接线、流式逐片段策略、鉴权/撤销链路、任意自然语言召回、
生产性能、用户回答质量和现实预测效度。没有新增依赖、迁移或持久写入。
