# MOD：晨报公开输入边界补测（有限30项）

## Purpose / Scope

依据已发布ced7419和MORNING_completed_coverage_0945.json，先新增公开接口测试，不改现有172项、
day_pipeline组合测试或黄金。最多29个负向/边界场景加1个正向对照，共30项。
所有失败先保留原LF输出和源SHA并报root，修产品须root审读授权；不以覆盖率为产品要求。
首轮复现5项实缺后，root已逐项授权只修briefing_v2相关产品，并新增current_manifest.py。

## Context and Orientation

完整阅读briefing_v2八源、其compose调用链、现有自有/独立晨报测试与day_pipeline组合、
reports_v2对calendar/transit的复用、P2 Almanac及DayStatus。原coverage基线为8c554bd，
09:50:25完成：calendar综合79.31%、transit82.11%、evidence84.42%。原报告SHA为
7e77d6c25625361fa37eb61cc0266d79725ff9bac4619a20994bff11ec86359a。

只调用CalendarSnapshot、calendar_snapshot、compose_briefing等公开构造/入口，不注入私有状态，
不改函数、不object.__setattr__、不靠绕过构造器。P8使用既有明确synthetic样例的内存副本，
由独立JSON/SHA/RFC6901读值逻辑重签document/c/r/claim和当前来源投影，不用产品验证器造黄金。
重新计算hash只用于隔离绑定失败，不是PG真实性或计算质量授权。

## Progress

- [x] (2026-10-21 09:57 +08:00) 完成源码/调用方/172及组合测试阅读；列出不重复的公开形状缺口。
- [x] root发布完整证据并授权有限新测试；先冻结本计划的独立预期和8源SHA。
- [x] (2026-10-21 09:59:22 +08:00) 冻结30项矩阵，SHA 1f77c413625f6f24c059cd9c7fd372c388b613459fb032632dd2bd1719cdaf9e。
- [x] (2026-10-21 10:03:25 +08:00) 首跑25过/5失败，保存LF原始输出、8源SHA和未变材料并立即报root。
- [x] root完整审读并授权5项实缺修复；不改原矩阵、30项断言、既有测试或黄金。
- [x] (2026-10-21 10:07:53 +08:00) 原30项全部通过；9个产品与测试/矩阵快照无漂移。
- [x] (2026-10-21 10:10:18 +08:00) 晨报、day_pipeline、reports三套471项通过；同次观测9产品分支覆盖。
- [x] (2026-10-21 10:12:04 +08:00) 核对9源仍与实测一致、矩阵仍为1f77，冻结产品；补接线与回执。
- [x] 未运行全项目回归、性能或外部请求，不Git；提交/CI交由root。

## 独立场景矩阵

P2拒绝指受控固定领域错误，不携带原始输入；正向对照同时证明真实P2和三系P8可以公开编排。

| ID | 公开输入变化 | 独立预期 |
| --- | --- | --- |
| BP00 | 当前P2、当前订阅和独立重签的bazi/ziwei/astro三条有效日规则 | 历法与3条正午结构、完整依据，效果0，输入不变 |
| BC01 | CalendarSnapshot.day传datetime而非date | 受控拒绝 |
| BC02 | observed_at的owner日期与snapshot.day不同 | 受控拒绝 |
| BC03 | almanac.weekday与公历日不符 | 受控拒绝 |
| BC04 | workday配is_off=True | 受控拒绝 |
| BC05 | DayStatus.kind为未知枚举 | 受控拒绝 |
| BC06 | festivals含整数项 | 受控拒绝 |
| BC07 | lunar缺少is_leap键 | 受控拒绝 |
| BC08 | lunar.is_leap为字符串 | 受控拒绝 |
| BC09 | days_to_next是合法非负int但比实际owner日差多1 | 不接受矛盾P2快照 |
| BC10 | calendar_snapshot注入Clock.now返回naive时间 | 受控拒绝，不依赖Tokyo主机 |
| BC11 | calendar_snapshot传不存在的timezone key | 受控领域拒绝，错误不回显key |
| BE01 | sources只有2项 | P8整文档省略，不影响有效历法，效果0 |
| BE02 | limits为空列表 | 同上 |
| BE03 | rule_hits是mapping而非list | 同上 |
| BE04 | rule_hit带未定义的额外字段 | 同上 |
| BE05 | rule_hit.source为空mapping | 同上 |
| BE06 | context.system非三系之一 | 同上 |
| BE07 | evidence_paths重复同一路径 | 同上 |
| BE08 | evidence_paths指向有效/scope路径而非/data | 同上，不能因hash正确承认错域依据 |
| BT01 | ten_god日证据对象变为JSON标量，全部hash一致 | 不抛未捕获异常；坏规则不形成输出依据/断言 |
| BT02 | relation.complete为字符串，数据与context一致重签 | 坏规则省略，不把字符串当布尔条件成立 |
| BT03 | 仅有natal而非daily的ten_god规则 | 无流日断言，返回不支持/资料不足说明 |
| BT04 | ziwei日link仍未resolved | 不声称确定宫位，不附该坏规则依据 |
| BT05 | ziwei context宫位index与当前link不符 | 坏规则省略，不挑一边当事实 |
| BT06 | astro orb为bool，数据与context一致重签 | 不当作0/1度数渲染 |
| BT07 | astro angle不等于具名相位标准角 | 坏规则省略 |
| BT08 | astro总orb_limit与context不同 | 坏规则省略 |
| BS01 | 同批两item对同source_id各称不同revision/hash当前有效 | 整批受控拒绝或两项全省略，不能挑首/尾或同时显示 |
| BS02 | 同source_id同revision/hash却有active与revoked矛盾投影 | 同上，不以一个局部有效证明覆盖撤回 |

BT行可受控拒绝整份P8或省略坏规则，禁止原始异常、坏claim/虚假断言；不预定产品文案。
BS行的负向真值是不输出同一时刻互相矛盾的当前授权，拒绝整批还是省略同源两项由主线选择。
这些不要求数据库真实性；只是拒绝纯输入内部不一致。

## Surprises & Discoveries

P2 almanac(...).jieqi.days_to_next的明确公式是(next_at按owner时区的date减local date).days，
不能只把非负int当一致；此预期来自P2生成契约，不是为覆盖新增的日期口径。
首轮实际复现BC09、BC11、BT01、BS01、BS02共5项：日差不一致仍被接受、未知时区泄漏原始异常、
P8标量证据触发AttributeError，以及两种全批当前来源互相矛盾仍输出的情况。
其余25项通过。首次8源报告、raw和原矩阵不覆盖，最终9源覆盖另存新文件。
新current_manifest只做纯输入一致性检查；hash与typed投影都不能认证数据库当前授权。

## Decision Log

不重复已有scope/profile/date/noon/15分钟、短alias替换、撤源、每日上限、K2迟到和基础指针转义。
不做形似对象/反射/元类、篡改private属性或平台I/O；只变合法JSON里的公开字段或公开dataclass参数。
首轮不放宽黄金；受控早拒绝允许，不要求进入某个私有函数/特定覆盖分支。
命题含糊时暂停该场景写待决，不把新假设标成冻结需求。

root授权后采用整批固定领域错误处理同source_id的scope/revision/hash/active/revoked/incognito矛盾，
在交付授权通过之后、生成任何正文之前检查。typed item状态包括撤回状态，不先筛掉矛盾一方。
订阅当前typed状态也参与；P8仅结构/alias及doc/scope/revision/hash匹配时参与，不以active先筛选。
缺失、不匹配或结构坏的单份P8继续省略，不新增整批失败；全局关闭/停订继续提前返回。
P8对象证据检查局部收紧，不泛化捕获AttributeError，也不把紫微合法标量星名一律禁掉。
纯验证可能重复执行，本轮没有测性能，不声称旧晨报性能仍对应新源码。

## Validation / Recovery

新矩阵/源快照metadata写UTF-8 LF，合成正文不新增落盘，重用现有synthetic样例内存副本。
目标pytest仅新文件且同时≤1；keys空、tracing关闭、socket/DNS替身禁止网络。不连PG、不跑模型。
首轮raw先保存并hash，产品源前后相同；随后即使修复，也不覆盖失败证据或原黄金。
没有业务写入或迁移；产品修复仅在root明确授权的范围内。root独占Git。
兼容运行绑定308个材料：全Core文件集合及字节、三套测试/黄金、P2数据与显式docs矩阵。
矩阵pre/frozen/post均为1f77c413625f6f24c059cd9c7fd372c388b613459fb032632dd2bd1719cdaf9e。
新current_manifest.py明确纳入9文件覆盖分母与before/after快照，未用原8文件报告冒充。

## Outcomes & Retrospective

完成30项公开边界测试与获授权的5项修复；原30项30/30、有限兼容471/471通过，308材料无漂移。
9个晨报产品：行597/640=93.28125%，分支215/254=84.64567%，综合812/894=90.82774%。
calendar综合95.12195%、transit90.76923%、evidence93.50649%；覆盖变化不证明全输入或命理计算正确。
最终9源canonical-JSON SHA为b81054bd97d3eeb0f410a0b928a563eafa34d06b109409ebc3a5c183eb10a666。
首次失败、修后目标、最终兼容和coverage分别保留独立LF JSON；PG、通知、模型、性能均未运行。

## 待决问题

context.target_layers若是含daily子串的字符串是否必须整文档拒绝，P8自由context契约未完全明确；
首轮不纳入，改用已有严格布尔complete类型场景，不等待此项继续其余队列。

## 修订记录

2026-10-21 09:57 +08:00：完成只读审查并独立冻结有限30项预期；记录P2明确日差公式和待验证静态疑点。
2026-10-21 10:12 +08:00：补实测首轮失败、root授权修复、原30通过、有限471兼容及9文件覆盖证据。
