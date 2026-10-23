# MOD：调度公开边界独立验收计划

## Purpose / Scope

本轮独立验收有限 **28 个案例**，聚焦错误 P2 端口、农历资源边界、民用日期上界及公开合同。
最初只读准备；root随后明确放行28项及一次完整scheduling覆盖插桩兼容，已经完成，不修改产品或旧真值。
工作目录为 `C:/Users/Administrator/Documents/Codex/zhiming-v4-mod`，不运行 Git，不访问外部服务或真实模型。

目标行为是不能把错误或未知历法当作可发送的下次触发，也不能由机器默认时区改变日期。
覆盖率只用于发现未检验行为，不能用私有函数镜像或构造不可达对象追分；不预报修后分数。

## Progress

- [x] 完整读 recurrence_calendar、recurrence_civil、recurrence_contracts、next_trigger、机器串和墙钟实现。
- [x] 完整读 CalendarPort/P2CalendarPort、P2 day_status，及 next_brief、后台反思03点调用面。
- [x] 读既有两套 recurrence 测试、冻结日历真值和晨报订阅测试，排除重复的普通日期与既有随机矩阵。
- [x] 只读提取本轮 coverage 实际缺行，固定以下独立期望；未执行新案例。
- [x] (2026-10-21 09:58 +08:00) root放行后新增唯一独立测试，首轮28/28通过0.11秒；参数与真值未调整。
- [x] 保存首轮命令、输出、13源前后摘要及新测试LF字节身份；无失败可修，不修改产品或旧测试。
- [x] (2026-10-21 09:59 +08:00) 经root单独批准只运行一次完整scheduling插桩兼容，原1240+28共1268通过2.79秒。
- [x] 13相关源及9份完整套件测试/样例前后摘要相同；3目标覆盖、残余分支、新指南补充和§11回执齐。

## Current evidence / 选择依据

读取 [MORNING_completed_coverage_0945.json](../evidence/MOD_2026-10-21/MORNING_completed_coverage_0945.json)，
工作字节 SHA256 为 `7e77d6c25625361fa37eb61cc0266d79725ff9bac4619a20994bff11ec86359a`。
这只是已完成观测的来源，不是本轮新测量。

| 产品文件 | 原综合覆盖 | 实际缺行 | 本计划关注 |
| --- | ---: | --- | --- |
| recurrence_calendar.py | 77.9412% | 24,26,28,32,33,38,55,56,58 | 端口数据形状/异常、P2支持年份、农历返回类型 |
| recurrence_civil.py | 89.7959% | 25；另有4个缺分支 | 上界溢出安全结束、月/年搜索耗尽 |
| recurrence_contracts.py | 89.6552% | 88,90,92,96,98,121 | 公共构造器的语义冲突、缺字段与真布尔 |

既有测试已经覆盖月31缺日、闰年2月29、2026官方调休、2027未公布、农历闰六月/小月30日、
纽约与 Lord Howe 默认 DST、严格/含端点，以及大量 daily/weekly/monthly 随机日期；不重新铺同一矩阵。
现有正常 override 案例也不作为新成绩重复计数。

## Frozen independent truth：28个公开案例

除公开 dataclass 合同构造外，均从 `next_trigger` 进入，不直接调用 `_lunar_date`、`_days` 等私有函数。
所有错误端口由测试显式注入，只代表本地依赖失效；不会读取假期文件或下载模型。

| ID | 输入/安排 | 先固定的行为 |
| --- | --- | --- |
| CA01 | workday端口给未知 source | 无 at、需澄清，calendar_status_invalid |
| CA02 | source=override但 is_off=1 | 不能把整数冒充真布尔，受控 invalid |
| CA03 | source/布尔合法、kind未知 | 无触发，不回退按星期猜 |
| CA04 | kind=holiday、is_off=False | 相互矛盾的日历状态拒绝 |
| CA05 | kind=adjusted_workday、is_off=True | 反向矛盾同样拒绝 |
| CA06 | day_status抛带合成marker的OSError | calendar_unavailable，不回显marker、不安排 |
| CA07 | 注入对象缺 day_status | 固定 unavailable；不泄露属性错误或安排 |
| CA08 | 普通daily注入会报错的假期端口 | 不读取不需要的假期端口，正常UTC触发 |
| CL01 | lunar_date返回datetime | 不能当作精确date接受，lunar_calendar_result_invalid |
| CL02 | lunar_date返回None | 不能猜日期，同样受控无触发 |
| CL03 | lunar_date抛OSError | lunar_calendar_unavailable，不回显合成marker |
| CL04 | 注入对象缺 lunar_date | 固定 unavailable，不按公历生日替代 |
| CL05 | 农历循环参考本地年1899 | 支持年份之外明确澄清，端口不被调用 |
| CL06 | 农历循环参考本地年2201 | 上界之外同样不调用端口 |
| CL07 | 合成农历端口前一年缺日期抛LookupError，下一年给合法date | 缺日期只跳过该候选，继续下一合法候选；不是全端口故障 |
| CC01 | RecurrenceRule(monthly)缺day | 公开合同拒绝，不默认1号 |
| CC02 | yearly有day无month | 公开合同拒绝，不猜当前月 |
| CC03 | daily带leap=True | 只允许年度农历闰月规则使用该标志 |
| CC04 | workday同时要求offday过滤 | 冲突拒绝，不选一边忽略 |
| CC05 | daily带合法但不适用的day=1 | 多余字段拒绝，不悄悄改成monthly |
| CC06 | NextTriggerResult(needs_clarification=1) | 公开结果合同拒绝真假布尔混淆 |
| CV01 | UTC公历9999-12-31最后微秒，daily当日时刻已过 | 安全返回search_horizon_exhausted，不抛原始溢出 |
| CV02 | 同一上界，monthly第31日已过 | 不截断成可用日期，不进入10000年，不安排 |
| CV03 | 同一上界，yearly 2月29 | 不把不存在日期滚至3月，搜索耗尽明确澄清 |
| TZ01 | workday时区Pacific/Kiritimati，after=2026-10-17T10:00Z | 端口所收日期为当地10/18；00:30触发=10/17T10:30Z |
| TZ02 | 与TZ01同一瞬间，以Asia/Tokyo表达after | 同一端口当地日期及UTC结果，不采用主机显示时区 |
| TZ03 | NY重叠日01:30，after处于两个fold之间，默认clarify | 不选已过去瞬间或悄悄定策略；未来候选只保留06:30Z且仍澄清 |
| TZ04 | Lord Howe 02:15 gap_policy=skip，另加workday过滤 | 不向P2询问不存在的触发日；只验证下个真实候选，不挪成02:45 |

CA数据只来自有类型的合成返回；有效调休日以 override 明确声明，不复制官方假期表。
CL07使用明确的合成映射验证“缺一个候选”的传播，不宣称其为真实农历换算质量验收。
TZ04预期下一真实日期为2026-10-05，当地02:15对应2026-10-04T15:15Z；候选端口可记录日期调用。
上述UTC瞬间用公开时区规则独立算出；新期望不从待测产品输出反抄。

## Intended implementation after release gate

拟新增 `tests/v4/scheduling/test_calendar_boundaries_calendar_mod.py`；若尺寸需要，另新增独有 helper。
不改既有1240验收、黄金JSON、产品或P2表。每个公开案例都用合法公开构造器及注入端口进入；
不使用 object.__new__、替换冻结字段或 monkeypatch 私有迭代器来制造分支。

明确注入 UTC、Asia/Shanghai、Asia/Tokyo 与规则时区，错误输出使用 reason/布尔/候选验收。
调度API本身接受明确after而非Clock；取值通过显式 FrozenClock，不能给产品擅增Clock参数或用系统now。
不更改进程TZ、tzset或全局时区数据库。错误marker为显式合成，例外消息只核不回显，不打印私人正文。

授权放行后单个pytest进程，先跑28新目标，必要时再跑既有兼容集合；全量和覆盖测量由root错峰安排。
所有新公开JSON使用 open(..., encoding="utf-8", newline="\n")；保存原始观察，不覆盖历史或规范化旧gold。

## Source snapshot / 待执行状态

| 已读目标 | 工作字节SHA256 |
| --- | --- |
| recurrence_calendar.py | `57173b352496bb513fef47714a80ff5f59ab5ef0c904df5f1d2708c95085a622` |
| recurrence_civil.py | `a7260919264f427f5a1e65ca04338da9b177ff8a71549d249c66251b1fe4f174` |
| recurrence_contracts.py | `061cb1756e30e27f6e23795d7cbec0d9a28646b51111cd440d4ad7fc07d9a47d` |

这些是原始字节SHA256，不是Git提交号或授权证明。三份目标摘要与上述coverage来源一致。
## Surprises & Discoveries

28个公开拒绝/边界案例首轮全部通过，没有发现产品实缺。覆盖不足提示的是未执行过的保护，不能直接称为错误。
公历上界可以从公开next_trigger进入并安全耗尽；无需调用私有迭代器或绕过构造器制造分支。
端口返回形状、P2有效年份、半小时DST及日期线的拒绝/正常行为均保留原设计。

兼容观察不等于整项目全量：本次仅tests/v4/scheduling，不能把先前09:45历史三轮数字加上本轮新28。
civil仍有2个未执行分支、calendar仍有1个，保留缺口，不在结果之后追加案例追求100%。

## Decision Log

原计划冻结SHA256为`d1ed28e9093dac3a78a15ccabd816253fa21d3caaa27b36d77ebef2696963c93`，
原28行真值表未改；本次只更新活文档状态。独立测试在首跑前完成Ruff120，SHA256始终为
`9b17b923b1ad3334931c092fdee37be629121b8621afc24d19f45c270c93aaab`。

使用公开RecurrenceRule/NextTriggerResult、显式FrozenClock及注入本地端口，既有conftest阻断socket。
无产品修改，不运行性能、PG、模型或跨项目全量。覆盖只做root批准的一次模块兼容观察。
本轮不更改P2数据或原有黄金；新证据使用显式UTF-8 LF，Git发布与blob字节复核交root。

## Outcomes & Retrospective

独立28/28首轮通过0.11秒，完整scheduling兼容1268/1268通过2.79秒。
calendar行100%/分支95.4545%/综合98.5294%；civil行100%/分支85.7143%/综合95.9184%；
contracts行、分支、综合均100%。综合定义为行与分支计数相加后求比例，不把civil分支误报为90%以上。

首轮报告：[SCHEDULING_calendar_independent_first_20261021.json](../evidence/MOD_2026-10-21/SCHEDULING_calendar_independent_first_20261021.json)，
SHA256 `b23418c86960feba00e5a706557f02fd243e34477d212da8a59374b6409ddfdb`。
兼容覆盖：[SCHEDULING_calendar_coverage_20261021.json](../evidence/MOD_2026-10-21/SCHEDULING_calendar_coverage_20261021.json)，
SHA256 `003b9a0534782acb9045d63774b4c4af712250425c884b8886ad0ec79eea7043`。
这些结果仅证明当前本机合成端口及规则行为；真实cron/PG/CAS/通知和主线接线仍未验证。

## 修订记录

- 2026-10-21：只读审查实际缺口、完整产品及调用方，冻结28个独立期望。
- 2026-10-21 09:58 +08:00：获root放行后首测28全过，保存独立观察，不改产品或真值。
- 2026-10-21 09:59 +08:00：获root单独批准完成一次模块插桩兼容1268全过；更新四活段落并保留真实残余分支。
