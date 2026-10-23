# synastry v1：先确认，再比较两盘结构

版本 `p8-synastry-v1`。状态：P8只读计算候选；不代表主线Agent、持久化授权或HTTP路由已接入。
Schema：[synastry.schema.json](synastry.schema.json)。根Schema验证成功输出，`#/$defs/Request` 验证输入。
Request Schema只做结构检查，之后仍须通过原生语义预检；例如JSON Schema的整数类型可接受1.0，
Python原生revision要求真正int，且身份字段不能只有空白。未知IANA时区也不能仅凭字符串结构通过。
这些变体会在两侧预检阶段拒绝，不得因Schema通过而省略预检或开始准备另一盘。
合成资料为阿远和小禾，双方均不是用户或真实他人资料；实际完整输出由对应样例生成器写入samples目录。

## 入口与输入

Charts原生纯入口：

    synastry(chart_a, chart_b, kind, *, consent, as_of_date, orb_degrees=6.0)

Core隔离入口：`P8ChartAdapter(current_owner).synastry(request)`，通过现有P8 worker运行；
不得把Core与Charts依赖环境合并。`chart_a/chart_b` 是出生计算输入对象，不是两个旧CalculationArtifact，
也不是把整个chart_compute预览信封直接传入。
Core选表由适配器构造器的选项控制，会覆盖输入内的p8_options；原生Charts入口可分别显式提供选项。
不能据一份原生示例推断Core会接受每个人任意指定的选表；实际方法与来源仍以返回结果为准。

```json
{
  "chart_a":{
    "owner_user_id":"synthetic-owner-ayuan",
    "subject_id":"synthetic-ayuan",
    "revision":1,
    "operation_id":"synthetic-ayuan-synastry",
    "birth":{
      "date":"1994-03-12","reported_time":"08:20","gender":"男",
      "place":{"tz":"Asia/Shanghai","lon":104.07,"lat":30.67},
      "clock_basis":"clock","precision":"reported"
    }
  },
  "chart_b":{
    "owner_user_id":"synthetic-owner-ayuan",
    "subject_id":"synthetic-xiaohe",
    "revision":1,
    "operation_id":"synthetic-xiaohe-synastry",
    "birth":{
      "date":"1995-08-27","reported_time":"14:10","gender":"女",
      "place":{"tz":"Asia/Shanghai","lon":120.15,"lat":30.28},
      "clock_basis":"clock","precision":"reported"
    }
  },
  "kind":"romantic",
  "consent":"user_confirmed",
  "as_of_date":"2026-10-21",
  "orb_degrees":6.0
}
```

kind为 `romantic`、`friendship`、`collaboration` 之一，仅表明用户比较意图，
本版不按kind套不同的关系成功分数。
as_of_date是调用方通过Clock明确给出的北京时间日期，不从电脑的东京/北京时间设置读取“今天”。
日期是严格ASCII ISO格式，支持1901–2099，不能早于任一人物出生日期。
orb_degrees为有限数值，0至10度（含边界），默认6度；bool、NaN、Infinity均不能作为数值。
`birth.clock_basis` 为clock、standard或unknown；当前只接受报告准确时分的precision=reported。
`birth.place`要求经度lon和IANA时区tz；纬度lat可选，提供时仍须为-90至90的有限数值，拒绝bool。
当前三体系合盘未计算地理纬度相关的宫位；不因缺纬度猜值，也不将合盘相位称为宫位合盘。
Request Schema已与既有原生预检的可选纬度保持一致，没有改变计算、输出版本或同意闸门。
双方在准备任何一盘前均验证IANA标签可由当前明确时区源读取；未知标签报daily_transit_natal_invalid。
目标日早于任一出生日报daily_transit_before_birth，两侧均不进入本命准备；consent拒绝仍最先执行。
unknown若产生多个物理瞬间、夏令时gap或fold未确认，失败关闭，不据关系事件倒推。

缺纬度专项31项覆盖两侧分别/同时缺省、错误类型、范围、有限JSON与原生预检。
本机以独立Charts解释器实际对照同一阿远/小禾输入含纬度与两侧缺纬度，三体系结果、
文档ID与别名完整相同；这是合成单例及确定性验证，不代表任意输入的外部精度。
详见`../evidence/P8/week-oct21-latitude-contract-validation.json`。

## 授权与资料归属闸门

consent必须是精确字符串 **user_confirmed**。缺失、空串、布尔true、yes、pending等均不允许计算。
纯入口在导入出生准备器、读取盘面或启动任何计算之前检查这一字段，
然后核kind、两份输入为对象、owner非空且相同。
Core适配器进一步要求两份owner都等于构造适配器时已验证的当前owner，然后才启动worker。

字符串相等不是完整的授权系统。主线必须先核当前已登录owner、他人资料的明确同意、
subject归属、revision与撤销状态，再传user_confirmed；不从聊天语气、历史使用、照片或默认值猜同意。
本函数不会建立、扩大或永久保存授权，不证明“对方同意”事实本身。
这次计算同意不自动涵盖保存、分享、飞书发送或之后的另一次处理。
拒绝不得返回对方出生值、部分盘或第三人资料；不先算后问。

## 输出与时间口径

信封含 `version/scope/data/rule_hits/sources/document_id/aliases/effects/limits`。
scope绑定同一owner及两侧的subject_ids、revisions、operation_ids，数组顺序与a/b一致。
只读操作不建立档案，重复请求内容相同则生成相同内容标识；operation_id变化属于不同scope。

| data字段 | 计算含义与不可推出的结论 |
| --- | --- |
| `kind/consent/as_of_date` | 原样回显已核定用途、确认状态与明确日期；不代表主线授权已经持久化 |
| `bazi.pillars_a/b` | 两盘实际四柱，分别保留；不合并为一张虚构盘 |
| `bazi.day_stem_combination` | 两侧日干相差五干的五合结构，met为布尔；transformation_established恒false，不据五合宣布合化 |
| `bazi.branch_relations` | 两盘四柱支的16个跨盘配对，保留实际六合/六冲；每条标a/b柱、干支与关系，不额外推吉凶 |
| `bazi.visible_a/b` | 各四个透干加所选藏干表每支第一干，共8个表层元素；不计藏干气量、旺衰或现实性格 |
| `bazi.element_complement` | a缺而b有、b缺而a有的表层五行列表；缺项不等于喜用，也不表示人需要被他人“补足” |
| `bazi.useful_complement` | 两方向 × 扶抑/调候/格局三种候选，共6条。取一方候选干与另一方透干的交集，保留候选与实际对方干 |
| `astro.positions_a/b` | 两人实际出生UTC经Swiss UTC→TT/UT1后的十天体热带地心黄经及速度等；不套真太阳时，不混入当日行运 |
| `astro.aspects` | a侧10天体对b侧10天体的跨盘配对，使用合0、六合60、刑90、拱120、冲180度；每项保留实际误差 |
| `astro.orb_degrees` | 统一容许度上限，误差小于等于上限才纳入；不同软件与方法可取不同值，这是本项目具名参数 |
| `astro.method/natal_at_utc` | 历表、flags、版本与实际两侧UTC；数值算法不证明关系效度 |
| `ziwei.cross_views` | 两侧各一次“自己的夫妻宫 ↔ 对方的命宫”实际宫支、主辅星并列；same_branch和shared_star_names只是事实比较 |
| `ziwei.compatibility_score` | 恒null；尚未建立可校准的相容度或配对吉凶算法 |
| `methods/time_basis` | 两人分别给真太阳主坐标与四柱方法；北京时间四柱或紫微盘不同才保留comparisons，不改原生口径 |

扶抑栏把原先两种项目方法的候选取并集；格局栏把并存候选格局的候选干取并集。
`aggregation=union_of_parallel_candidates_not_consensus` 表示并列候选汇集，**不是**两法共识、唯一用神或力量已经成立。
调候仍是具名摘表，佐神/全文例外未全收；各条都标candidate_only=true与effective_strength_assessed=false。
同一干可同时出现在互相有分歧的候选路径中，不能为了给合盘结论硬选一条。

as_of_date只用于资料核对与计算准备，不把“今天的行运”混入本命合盘。
默认八字/紫微解读坐标是真太阳时；物理年/月节界仍按实际UTC核定；
西占始终用实际出生UTC。坐标不是另一个出生瞬间。
倒推保持冻结隐藏，不能拿合盘匹配度反写出生时间。

## 规则与依据别名

命中按真实条件产生，source既支持具名来源对象，也支持实际官方URL；
项目定义的元素/候选交集来源对象明确标项目方法，可能没有古籍URL，不能补一个不支持该数值算法的古籍链接。

| rule_id模板 | 真实met=true的条件 |
| --- | --- |
| `synastry.bazi.day-stems-combine` | 两日干五合 |
| `synastry.bazi.branch-地支六合/地支六冲` | 具体跨盘柱配对存在对应关系 |
| `synastry.bazi.visible-element-complement` | 对应方向确有表层缺项在另一盘出现 |
| `synastry.bazi.useful-candidate-overlap` | 对应方向、对应候选路径与对方透干有实际交集 |
| `synastry.astro.<相位名>` | 对应天体配对满足实际角距/容许度 |
| `synastry.ziwei.spouse-life-readout` | 两个实际宫位已解析并可并列；只证明视图已构建，不证明适配 |

同一rule_id模板可对应多条真实配对；每条拥有独立的Pointer与r别名，
不能把重复模板当作几份独立证据来加重结论。
〔c#〕按当前结果真实/data路径排序生成，〔r#〕按实际命中顺序生成，
内容摘要和claim_id绑定本次scope/数据/路径。短别名只在这份结果中有效。
主线必须登记当前结果后再让Agent引用，不能把一人的c1借给另一人。

老朋友口吻示意（#必须换成本轮实际绑定的别名）：

“这里有一组联系〔c#〕〔r#〕，也有要磨合的地方〔c#〕〔r#〕。
咱们先别替对方下结论，可以聊聊日常节奏、钱怎么安排、分歧来了怎么处理。”

不输出婚配百分比、不评价人品或忠诚、不预告分手婚育，盘面不替代双方意愿。

## 错误码与适配器边界

| 纯入口错误前缀 | 触发 |
| --- | --- |
| `CONSENT_REQUIRED` | 缺少精确确认；任何出生处理之前拒绝 |
| `synastry_kind_invalid` | 未登记的kind |
| `synastry_input_invalid` | 任一输入不是对象 |
| `AUTH_SCOPE_ERROR` | 双方owner不一致/缺失，或Core当前owner不匹配 |
| `synastry_ziwei_palace_unresolved` | 命宫/夫妻宫缺失或不唯一，不猜一个落点 |
| `daily_transit_date_invalid/out_of_range` | 复用准备器的as_of_date格式或范围错误 |
| `daily_transit_natal_invalid` | 任一方日期/时刻、归属修订、经纬度或时钟依据形状非法；两侧全部预检后才准备任何本命 |
| `daily_transit_unconfirmed_physical_instant` | 出生物理瞬间未唯一确认，不能默选 |

`CONSENT_REQUIRED` 指原生调用显式传入 `consent=None` / 其他未确认值，或 Core 请求对象缺少该字段时的运行时拒绝。
直接 Python 调用若省略 `consent` 或 `as_of_date` 必需关键字，会先发生参数绑定 `TypeError`，尚未进入校验或出生处理；
即使显式 `consent=None`，省略 `as_of_date` 仍先发生 `TypeError`。调用方应传完整关键字，输入 Schema 继续要求 `consent=user_confirmed`。

出生资料格式、经纬度、时区、修订版本和出生晚于as_of_date还会由复用校验器拒绝。
orb非法由有限数值校验器拒绝，超大整数也转换为固定ValueError，不泄漏OverflowError；不能把NaN写入JSON。
这些是纯入口异常前缀，主线应转换为面向用户的结构化错误，不能直接泄露参数或stderr。
现有worker失败的Core封装可能只返回 `chart_engine_failure`，依赖缺失为 `missing_chart_dependency`；
不能声称全部底层错误前缀已穿透现有进程边界。

## Schema与语义验证

Schema验证结构、成功consent常量、kind、方法字段、六条候选/两条紫微对读、指纹与别名形状。
它不能替代当前owner授权、撤销、日期先后、有限值、原生计算一致性、Pointer解析、SHA与rule真值复核。
输入Schema拒绝未确认状态，而运行时测试还须验证所有未确认/非对象/越权输入在计算之前失败。
成功样例须通过独立jsonschema检查，所有c/r依据要逐项解析实际内容，不只检查别名字符串长得正确。

## 出处与待核

- [《三命通会》卷二公开转录](https://zh.wikisource.org/wiki/三命通會/卷二)：干支五合、六合与冲的概念；不提供本项目关系分数或完整合婚效度。
- [Swiss Ephemeris官方接口](https://www.astro.com/swisseph/swephprg.htm)：黄经与时间标准计算，不能为关系结局背书。
- [iztro星盘文档](https://docs.iztro.com/posts/astrolabe)：程序十二宫结构；本机固定包版本由实际结果方法复核，当前网站新接口不代表本机已经升级。
- 28号命理线第5项与项目P8显式三候选：consent闸门、结构对读及编辑定义；不是古籍量化算法。

存疑/待核：古籍刻本页码、合婚完整前提、紫微跨盘对读流派、候选权重与现实有效性未验证。
本结果不调用模型、不访问服务器、不发送、不写档案或授权账本；停止使用本独立接口即可回退，v3旧口径不变。
