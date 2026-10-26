# chart_compute 接线契约 v1.1（P8 材料终版）

2026-10-26 按42号第二部分定稿；终版指本线材料契约，不表示 Agent 已接线。
原生结构、字段映射、错误折叠与主线改动责任见 [P8 接线说明](p8_wiring_for_main.md)。
预览信封仍保留 `draft_integration_contract`，以免把演示装配器当成运行时入口。

本文件交主线与前端线只读使用。已有实现是 `P8ChartAdapter` 的三个原生计算入口与四个只读工具入口；主线的 `chart_compute` 工具、授权档案读取、别名账本、API、持久化和前端接线尚不在本线实现。本文约定与离线样例不能作为已经上线的证明。

设计依据：蓝图§8/§10、18号推理增补§A/B、23号第二节、24号审校§6；用户本夜直接要求的范围优先于旧阶段提示词。数据来自程序，解释来自有出处的技能；规则成立仅指条件命中，不代表格局或现实事件已经成立。

## 1. 输入边界与路由

### 1.0 v1.1 增量（28号 M3）

2026-10-20升级仅增加交界信息：原生time_basis顶层`boundary_alerts[]`为完整提示对象；
集成信封顶层`boundary_alerts[]`及`view.boundary_alerts[]`为指向这些对象的Ref数组，两者相等。
旧字段含义、默认NOAA/Meeus公式、原38条结构规则和原35条编号不变。
Schema和语义校验继续接受`p8-chart-compute-preview-v1`且无这两个新数组的旧信封；
v1.1则必须提供数组，未命中时是`[]`，不能静默丢弃已有提示。

| boundary_kind | 触发条件（端点包含） | 对照 |
| --- | --- | --- |
| hour_branch | 真太阳时距奇数整点时辰交界≤900秒 | 边界两侧实际计算四柱 |
| late_zi_day | 真太阳时距23:00≤900秒 | sect1晚子换日两侧；可与hour_branch同时出现 |
| zi_midnight | 真太阳时距00:00≤900秒 | 默认sect1可能同柱，另附具名sect2差异；不篡改默认日界 |
| jie_month | 物理UTC+8距最近节月交接≤7200秒 | 物理交接两侧，日/时仍用相应真太阳坐标 |
| eot_implementations | NOAA/Meeus与独立Swiss公式在同一物理时刻算出不同四柱 | 保留默认柱与独立实现柱及实际差值 |

提示包含`rule_id,rules_version,met=true,critical=true,instant_id,current_pillars,alternatives,`
`distance_seconds,threshold_seconds,school,source,evidence_paths,text,default_formula_changed=false`。
独立算法的一致或差异不等于观测真值，也不据此修改记录、确认时辰或解冻倒推。
`source`指向[边界口径与原始资料](../evidence/P8/night28-boundary-policy.md)，原刊未核继续明示。

新增提示也注册真实r别名；`view.rules`继续仅为38条U12评估中的true命中，
不能再用`aliases.r.length == view.rules.length`猜规则数，应按ref路径或rules_version区分。
边界r绑定其instant_id对应的真太阳主盘；其c依据可以指向同原生文档的物理时间或坐标源值，
因此保留c的实际UTC输入属性，不把物理输入改名真太阳坐标。原U12同分支校验不放宽。
主线若合并不同样例别名仍须重登记。三份阿远固定出生与2026-10-19目标日保持，
真实太阳07:06靠近07:00，故新增卯/辰候选而不改变主盘辰时。

模型只提出 `system / target / scale` 等能力意图。主线必须从已授权的同一人物档案读取出生资料，校验 owner、subject、revision、确认状态及撤销状态，再调用下表。禁止让模型补出生地、经纬度、UTC偏移、时辰或原盘字段。

| 能力 | 现有入口 | 使用方式 |
| --- | --- | --- |
| 八字/紫微的准确记录核对、主解读与北京时间比较 | `P8ChartAdapter.time_basis(request)` | 主解读选返回的 `interpretation.primary_chart_ids`；保留全部有效物理瞬间，不能用流派选择消除DST歧义 |
| 原有结构产物和西占本命/显式行运区间 | `P8ChartAdapter.calculate(archive, date, requested_systems, revision, subject)` | 只有它返回标准profiles/artifacts/features。其八字/紫微保留旧平太阳时；八字日界sect2，紫微走自身晚子index12，不可标成新真太阳时主盘 |
| 具名次限、太阳回归 | `P8ChartAdapter.western_timing(request)` | 独立只读信封，以实际UTC计算；不是默认本命artifact，也没有自动存档 |
| 全书可选宫干飞化表 | `palace_flying_transformations(data, school="quanshu")` | 纯函数可选；公开适配器尚未暴露school参数，默认仍iztro |

所有入口同步计算；主线异步服务需移交工作线程，并保留取消/超时与授权检查。命理线没有新建HTTP路由或后台调度。

### 1.1 time_basis 原生请求

```json
{
  "owner_user_id": "synthetic-owner-ayuan",
  "subject_id": "synthetic-subject-ayuan",
  "revision": 1,
  "operation_id": "synthetic-ayuan-bazi-20261019",
  "as_of_date": "2026-10-19",
  "birth": {
    "date": "1994-03-12",
    "reported_time": "08:20",
    "gender": "男",
    "place": {"tz": "Asia/Shanghai", "lon": 104.07, "lat": 30.67},
    "clock_basis": "clock",
    "precision": "reported"
  }
}
```

`as_of_date`由主线Clock显式提供，不读取机器当前日期。revision是非负整数（不接受布尔值）；owner、subject、operation_id为非空字符串。出生时间范围1901–2099，日期严格`YYYY-MM-DD`，时刻`HH:MM[:SS]`。`place.tz`必须为已提供的IANA时区，不能拿当前UTC偏移代替历史时区。`clock_basis=clock|standard|unknown`分别表示钟表时、已去除夏令时、记录依据未知；`precision=reported`仅核对准确记录，不接未知时辰倒推。

原生八字/紫微时间核对使用tz与lon，lat不参与这一步；预览Schema为完整三体系合成资料登记lat。西占本命/宫位必须显式提供lat且绝对值小于90。不要因预览样例字段齐全而推断真实档案也齐全。

P8具名表在构造器`p8_options`显式选取，默认与允许值以`knowledge/p8_bazi/schools.json`为准；徐表申月戊己合土必须额外明确选项。`time_basis`不是资料确认动作，`profile_update_allowed=false`、`writes=0`。

### 1.2 calculate 原生请求

`archive`含`owner_user_id`、`subject_id`、`user.gender`及`user.birth`；出生字段为`solar_datetime`（明确到整分钟）、`timezone_offset`（出生当时实际偏移，含DST）、`time_precision`、`location{lng,lat}`。传入`date="2026-10-19"`、`requested_systems=["astro"]`、`revision=1`、同一subject。seconds不能静默截断。只有明确的阳历日期才可传入；阴历资料先由有来源的主线流程转换。

`calculate`返回`{profiles,artifacts,features,branches,errors}`，profiles/artifacts/features三个字典按原生ID索引，branches/errors是数组。`errors`可能与部分有效结果并存，调用方不能只检查HTTP状态或吞掉错误。profile保存`requested_method/actual_method/versions/fallback`；artifact保存`profile_id/branch_id/time_scale/target_date/data`；feature通过`artifact_id + path`定位值。原有出生时间有限采样不等于连续覆盖。

行运区间经构造器`transit_period={start_at,end_at,moving_bodies?,orb?,step_hours?}`提供。本命黄经必须由该次真实本命计算派生，不接模型自报的本命位置。区间带明确时区、长度大于0且≤366日；步长0.1–6小时、orb 0.01–10度，天体按已登记枚举。默认未请求区间时，不能以目标日正午快照冒充区间搜索。

### 1.3 western_timing 原生请求

公共外层严格为`owner_user_id,subject_id,revision,operation_id,technique,args`。

| technique | args必需字段 | 可选字段与边界 |
| --- | --- | --- |
| `secondary_progressions` | `birth_at,target_at`（明确时区的ISO时刻） | `orb`；顺行、一UT1日对应365.2422 UT1日，年龄0–150热带年；推运宫位`null` |
| `solar_return` | `birth_at,return_year,longitude,latitude` | `orb`；回归地点必须明确，不能默认与出生地相同或猜旅行地 |

太阳回归按实际UTC生日周年锚点前后5日寻找唯一黄经根；return_year是周年标签，实际根可能跨UTC自然年。闰日处理、地点与Placidus失败保留实际输出；不以生日中午代替，不自动换宫制。西占时间不套真太阳时。

## 2. 输出字段与原生文档根

### 2.1 time_basis 双口径

原生信封包含`version,owner_user_id,subject_id,revision,operation_id,time_basis,charts,interpretation,profile_basis_record,release_policy,source_sha256`及只读标志。

`time_basis.instants`描述真实UTC、DST、fold/gap及IANA来源；`charts[]`逐一保存`time_basis`坐标、八字`data`和`ziwei_column`。`basis=true_solar`是默认主解读，`beijing_standard`是固定UTC+8比较；`standard`是出生地标准时，海外资料不能将它改名北京时间。坐标相同可以归组，来源变体仍保留。不存在时刻时`charts=[]`，不能自动平移一小时；重复时刻会有多组主盘，必须核对记录。

`interpretation.comparisons`只列盘面不同项及“按北京时间则为…”文字；两种口径结果相同可为空，不为展示差异改出生记录。`visible_by_default`及`interpretation_role`供展示主盘/比较/诊断；不把诊断坐标隐藏为不存在。`profile_basis_record`是只读建议，不是数据库已保存记录。

八字年/月与起运以物理UTC+8节界计算，日/时采用声明坐标，P8准确核对使用sect1晚子23点换日。紫微实际按py-iztro晚子index12处理；农历月末晚子与次日早子可能命宫不同，不能宣称两个体系历法完全一致。西占始终保留实际UTC。

### 2.2 规则与交互

| 字段 | 含义与使用限制 |
| --- | --- |
| `charts[i].data.p8.rules_version` | 规则知识版本；来源/方法变化须使持久化依据重新生成，不能沿用旧别名 |
| `...rule_hits[]` | 仅`met=true`，含rule_id、条件参数、source、priority、domains、time_scale、evidence_paths、details |
| `...rule_assessments[]` | 全部38条，包括false；供步骤日志、反证和contradictions，不给false项分配r别名 |
| `...patterns.regular_eight` | 旧八正格各三条件；qi_matches区分本中余，过筛仅候选 |
| `...patterns.regular_extra` | 禄劫刃各三子条件的复合候选，38总数不代表省去条件 |
| `...time_interactions` | nodes、relations、ordering_school/label、priority_labels、annotation_basis、limits；关系palace/domains/priority均是项目检索口径 |

八字规则的原生`evidence_paths=/data/...`相对于该chart的`{data: chart.data}`根。包成外层工具响应时必须显式提升为`/charts/i/data/...`或登记独立文档根，不能直接对整个time_basis信封解析`/data`。

priority目前只有子平与通用两列，1–5是项目排序值、未获专家标定，不能当风险严重程度。U2只观察结构关系，不宣称合化、灾祸或因果；流年/流月/流日含具体采样和区间，不能混称事件发生时间。

### 2.3 紫微飞化

time_basis根路径为`charts[i].ziwei_column.p8_flying_transformations`。默认48条宫干边、12节点；边含起点、四化、星曜实际落点、self_transformation、几何对宫、table_ref和证据Pointer。缺星/歧义保持unresolved，不补星或补宫。

`table_id=iztro|quanshu`；当前默认iztro壬科左辅，可选全书壬科天府。选表只改变宫干edges/nodes，不重写实际生年星曜mutagen与真实运限，`matches_named_table=false`可合法表示差异。time_basis只读列当前为本命盘，未提供的运限层是`unavailable`；不要据此伪造流年。calculate产物可含实际运限，但该入口仍按其平太阳时方法声明，不能冒充本契约真太阳主盘。

紫微飞化Pointer已在time_basis中提升到完整响应根`/charts/i/ziwei_column/...`，对应`evidence_document_root=complete_time_basis_response`；嵌入工具外层后再通过原生document_id引用。`table_sha256`是完整知识文件的LF归一hash，不是单个异表单独hash。全书原刊尚未完成独立校勘。

### 2.4 西占行运、推运与回归

显式区间在astro artifact的`data.p8_transit_windows`，含requested_interval、actual_UTC、orb、step、根括区间和windows；每个window保留entry/exact[]/exit、边界裁剪与入相/出相片段。区间可能无命中，`[]`是有效结果；finite-step搜索不保证没有短窗口或切触遗漏，2秒括区间不等于物理准确度。

western_timing信封的`data`另按technique提供`progressed_planets/mapping/actual_UTC`或`root/houses/actual_UTC`。次限的象征历表时刻不是目标日期的真实天空。老本命calculate与新具名UT1计算的实际方法各自保留，不能拿不同方法的细小差异当作录入错误或偷偷覆盖。

## 3. 别名与内容绑定

短别名只在本轮实际可见上下文有效。`〔c#〕`对应计算依据，`〔r#〕`对应实际true的规则命中；数字不是rule_id或数据库ID的一部分。样例中的注册表为临时演示，不能当作生产账本或确认动作。

主线注册时至少绑定：owner、subject、revision、当前工具运行、时间分支/坐标、实际产物内容ID、方法/来源hash和JSON Pointer。`time_basis.charts[].id`仅是坐标标识，不包含目标日/全部规则版本；`feature.id`也不能脱离artifact_id单独作为跨运行唯一依据。方法、来源、目标日或资料修订变化后，先生成新的内容绑定依据，再分配本轮短别名。

r引用同一命中的实际evidence字段，且附rule_id、规则版本、分支和原命中行；false只留assessment。跨口径同名规则不是同一条依据。`used_claim_ids`必须映射回本轮登记的稳定依据ID，未知、过期或跨scope别名应被拒绝。ContextEngine只按本轮领域与已登记优先级注入前10项；其余可通过工具按需查看，这部分由主线实现。

预览中c按`(document_id,path)`去重、字典序从c1编号；r按主盘顺序及程序原rule_hits顺序从r1编号，证据c引用沿用原evidence_paths顺序。JSON保存`c1/r1`，正文渲染为`〔c1〕/〔r1〕`。每份样例是独立演示运行，operation_id分别为`synthetic-ayuan-bazi-20261019`、`...-ziwei-...`、`...-astro-...`，不能把三份c1直接并入同一真实上下文。主线上下文已有别名时应延续本轮账本，不照抄演示编号。

document_id为`doc-`加完整scope、kind、source_sha256及payload的内容SHA256；claim_id为`demo-claim-`加scope、ref、值hash、branch_id、basis以及规则身份/版本的内容SHA256。短别名和evidence_aliases短号不进入稳定claim_id。规范化采用Python有限JSON、UTF-8、`ensure_ascii=False,sort_keys=True,separators=(",",":")`；这是项目序列化约定，未宣称等同RFC 8785跨语言数值规范化。主线若改序列化需升契约版本。

内容hash用于识别变更，不提供来源签名或授权；主线仍必须验证真实artifact的产生与归属，不能把外部用户自行重算hash的任意JSON当本项目可信计算。

## 4. 错误与确认状态

| 实际表现 | 当前入口 | 主线处理约定 |
| --- | --- | --- |
| `AUTH_SCOPE_ERROR` | calculate.errors | 拒绝归属不匹配，不尝试其它人物 |
| `MISSING_INPUT` | calculate.errors | 列明缺少的已确认参数，不猜值 |
| `RULE_GAP` | calculate.errors | 未支持体系；保持未实现状态 |
| `CALCULATION_ERROR` | calculate.errors | 可有部分成功结果；保持requested/actual/fallback和警告 |
| `ValueError` | time_basis/western_timing预检或纯函数 | 主线需映射为结构化输入错误，不能直接拼私人原文 |
| `missing_chart_dependency` / `chart_engine_failure` | 子进程RuntimeError | 原始stderr不外发；缺依赖与引擎失败不能返回假盘 |
| `chart_output_limit_exceeded` | 子进程RuntimeError | 超过输出大小上限，拒绝结果 |
| subprocess timeout/OSError/JSON解析错误 | Python异常 | 主线捕获并输出脱敏错误；当前并无统一HTTP错误封装 |
| gap/fold、记录依据未知 | time_basis正常结构化结果 | `requires_confirmation`及可能的空/多charts；不是可自动修正的数据错误 |

`INPUT_INVALID`、`BIRTH_TIME_CONFIRMATION_REQUIRED`、`REFERENCE_INVALID`等可作为主线映射建议，但当前适配器并未统一抛出这些错误码。前端不应把本文件建议码当作已经存在的API返回。错误reason不要原样发送出生正文、底层stderr、路径或令牌；现有calculate的reason仍由主线统一脱敏后呈现。

## 5. Schema、样例与验证边界

结构Schema：[chart_compute.schema.json](chart_compute.schema.json)，draft 2020-12。本文件的工具集成信封是`p8-chart-compute-preview-v1.1`草稿，**不是**对主线已有HTTP返回的描述。

| 顶层字段 | 结构 |
| --- | --- |
| contract_version / status / mode | `p8-chart-compute-preview-v1.1` / `draft_integration_contract` / `scripted_synthetic_preview` |
| display_name / scope | 阿远；owner_user_id、subject_id、非负整数revision、独立operation_id |
| request | system、target_date、time_scale、birth、physical_birth_at_utc；birth为本节明确标注的合成资料 |
| documents[] | document_id、kind、source_sha256、完整未改写payload；kind为time_basis、calculation_bundle或western_timing |
| view | time_basis、primary、comparisons、diagnostics、rules、assessments、interactions、flying、transits、timings各为Ref数组；不适用为空数组 |
| aliases.c[] | alias、claim_id、scope、ref、value_sha256、branch_id、basis |
| aliases.r[] | 同上，另有rule_id、rules_version、evidence_aliases；对应源值必须met=true |
| effects | model_calls=0、writes=0、alias_registry=ephemeral_demo_only |
| warnings[] | 草稿/合成/来源限制，不能当作已上线或预测有效 |
| boundary_alerts[] | v1.1新增，等于view.boundary_alerts；原生time_basis顶层完整提示的Ref数组 |

Ref严格为`{document_id,path}`，path始终相对于该document的**payload根**。空path表示整个payload；对象键按`~1→/`、`~0→~`解码；数组只接受0或不带前导0的正整数，拒绝负索引、`01`、`-`及越界。不能把文档外层的`documents[i]`或其它样例当同一根。[RFC 6901](https://www.rfc-editor.org/rfc/rfc6901)定义引用语法；[JSON Schema 2020-12](https://json-schema.org/draft/2020-12/json-schema-core)定义结构验证框架。

### 5.1 三份实际计算的合成画像

阿远采用07号§0.4的`default_synthetic`：男，1994-03-12 08:20，成都经104.07纬30.67，Asia/Shanghai。目标日2026-10-19，revision=1。没有使用真实用户资料。职业/居住/跳槽偏好只作画像背景，不混入计算条件。

| 文件 | 可供前端直接解析的数据 |
| --- | --- |
| [ayuan_bazi.json](samples/ayuan_bazi.json) | 准确时刻原生time_basis、真太阳时/北京时间、38规则assessments与true hits、交互顺序及临时c/r引用 |
| [ayuan_ziwei.json](samples/ayuan_ziwei.json) | 同一合成出生记录的真太阳时/北京时间紫微列、默认iztro48边飞化；未提供的运限层如实unavailable |
| [ayuan_astro.json](samples/ayuan_astro.json) | 实际UTC本命、7日月亮/太阳区间（1小时步长）、具名次限与2026周年太阳回归；样例显式选择成都坐标，不是推定真实回归所在地 |

两口径如果恰有相同四柱或宫位，comparison可为空；原始documents仍保留两个坐标。前端可将诊断坐标放可展开的核对区，不为演示制造差异。没有U12八字规则的体系不分配U12规则别名；真实边界命中仍有独立r别名。前端使用说明见[samples/README.md](samples/README.md)，本线不改web/。

### 5.2 重现与验证

在本分支仓库根目录，以Core解释器运行以下命令；CHART_PYTHON指向已安装独立Charts环境。用户模型Key不写文件。命令仅构造本机合成样例，不支持live模式。

```powershell
python -m mingjing_core.adapters.charts.benchmarks.handoff_build `
  --mode scripted --chart-python '<Charts Python绝对路径>' `
  --output docs/v4/contracts
```

构建器使用的离线网络/子进程拦截仅适用于独立CLI与测试进程，会临时操作该进程环境；**不能**复制到主线共享线程当作并发安全沙箱或生产网络策略。主线应使用其正式provider/额度/权限边界。

JSON Schema需启用FormatChecker并结合`ensure_finite_json`；归属、内容hash、引用解析、r=true、完整规则版本与西占实际UTC等跨字段关系由语义检查处理。它不证明授权、来源签名、排盘外部精度或人生预测有效。各样例的精确SHA、数量和本机验证结果在本里程碑证据报告列出；夜间不运行真实模型或服务器。

附带的`validate_preview`只校验当前builder的canonical阿远固定合成请求及其表示形式，会拒绝其它人物、日期或时间标签。Schema本身仅约束结构；固定输入核对后仍检查原生目标日、西占实际输入与显式地点、时序目标、内容hash、scope和依据引用。原生time_basis没有完整输入回显，因此它不是任意请求的通用校验器。主线通用接线需单独设计实际输入回显和内容绑定，不能照搬固定合成输入白名单作为真实用户API。修复缘由与反例见[请求绑定复核](../evidence/P8/night24-handoff-binding-review.md)。


### 5.3 v1历史本机验证回执（不代替v1.1验收）

完整v4 **816/816、0跳过、110.72s**；新增预览负例等47项通过。三JSON的Schema、原生scope、内容hash、全部依据Pointer和当前源码hash检查通过；前端README的JavaScript在三份JSON上共68次引用读取通过。103个Python样式检查、141保护文件不变。精确文件SHA/字节数见`../evidence/P8/night24-m2-validation.json`。单次构建观测八字1.122s、紫微1.114s、西占2.766s，含子进程/验证/文件写出，n=1，仅为本机观测，不是已接线chart_compute的API耗时或SLA。新提交CI发布后另核，不借用M1绿色。

## 6. 四个新增只读入口

| P8ChartAdapter入口 | 原生计算能力与独立契约 |
| --- | --- |
| `daily_transit(natal,date,orb_degrees=2)` | [流日](daily_transit.md)：真太阳本命、北京时间正午三体系快照，七日样例；快照不是区间 |
| `window_search(natal,date_range,purpose,offset=0,limit=31)` | [择日](window_search.md)：六用途公开权重，全区间排序、显式分页、实际正负命中；不建立结果保证 |
| `almanac(date)` | [黄历](almanac.md)：已有lunar-python具名日期口径，实际版本与安装包源码摘要 |
| `synastry(request)` | [合盘](synastry.md)：先检查consent=user_confirmed，再核对两资料当前owner；三体系结构对读，无适配百分比 |

四个工具使用独立`tool_evidence`信封，其`aliases[].path`相对于该工具结果自身根，
不同于本文件预览的`ref={document_id,path}`。两种别名结构不要混读；各工具仍需主线登记当前上下文账本。
Core入口通过现有P8隔离子进程运行原生库；直接Charts函数及其预计算缓存用于顺序本机计算，
不声称Swiss或pythonmonkey全局状态在共享应用线程中并发安全。所有API注册、主线资料授权/撤销、
持久化、HTTP和前端交互仍由主线实现；本线没有启动8003或部署服务。
