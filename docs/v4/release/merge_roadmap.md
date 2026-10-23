# v4 集成与合并路线图

## 当前路线（2026-10-24，指令板v8）

03:37增量集成：已在3d43cae（基础与X01）之上普通合入a08b32a的观察性生命周期、judge Journal和物理attempt接线。该源Core CI成功（run40005187551）：Core584、v4为4091通过/56跳过、ModelPort重叠子集970通过/95%覆盖；新merge自身CI另核。这里只推进已审开发片，未生成正式候选脚本gate或开放真实模型；跨窗口预算续作、Linux恢复、最终包与stage/生产授权仍缺。下方01:09基础集成是历史来源，后续片不再一概列为尚未合入。

首发核心为P1/P1b/P2/P3，不再单独发布B1/b9。`5af4628c37a6d654a7d8cc02ce50ea75bd3baf3a`的Core和时区CI均已成功，本提交将其普通merge进正式`v4/integration`，保留此前P1b的`6e47a058`历史。CI记录Core584、v4为4002通过/75跳过、ModelPort子集949通过及模型覆盖96%；子集不相加，75项跳过不算通过。草稿PR #16仅改目标为`v4/main`以避免随integration推进而被自动关闭，仍未合并；本周不合`v4/main`或`main`、不rebase或强推。实际CI见https://github.com/JerryandShawn/zhiming/actions/runs/39986672054。

正式脚本来源仍为f18的P3 48/48、日期7/7、原80展开69/81，不能用CI中的fake self-test替代。X01、生命周期/额度与首发恢复后续片在各自已推分支，须各自完成审阅和CI后再普通合入integration，不冒充本次已含。核心30题离线首次30/30不能替代同最终候选的正式脚本门或真实质量评测；完整范围与Linux恢复门仍未解除。

核心脚本全部通过时只读核模块日报首段“记忆2.0就绪”：已就绪则将`v4/p5-memory2`普通合入集成、按Z5分配0009，并以一次完整回归与全部脚本通过后才开真实评测；未就绪先核心评测，模块后续合入补跑M01–M13、KU01–KU02、TM01–TM02、MS01–MS03、A01–A03。23:20实际核对仍未就绪，此观察不代替未来合并时再核。主线承担必要共有记忆文件的后续冲突，不整条合并旧`v4/mod-organize`来带入延期模块。

第二批P5记忆2.0+P8多维命理（P8须首发候选就绪后才开），第三批P6评审员+P4真流式，之后P7/P9/P10。P4独立树WIP保留。定向检查优先，里程碑一次完整回归、最终候选再一次，CI绿以CI准；不照旧表逐次重复所有前端/Charts宽验。

stage/生产旧B/D授权取消，须用户另行授权。最终候选的新库恢复、Linux应用轨及受审执行单就绪之前保持No-Go；不得沿用b9的包hash、空样本或旧开门后回滚规则放行。

## 10-21历史路线记录（不作为当前发布范围、授权或测试频率）

本文件是顺序与测试闸门，不是合并或部署回执。依据用户10-20夜间队列、28号Z5与33号本周队列；本周集成只进`v4/integration`，向`v4/main`保持草稿PR，等大脑与用户复核。任何一条线不得自行合并`v4/main`或`main`。普通merge，不rebase、不强推。B1发布包仍固定b9a89b6，以下集成不能改变B1包或放行其Linux阻塞。

**当前复核（2026-10-21 11:04 +08:00）**：`v4/integration`保持`6e47a058`，运行时代码仅已合P1b；固定`2ca1378`的本机组合门及同头Node22配置push CI已通过，后续文档头不继承该结论。P1b/P3组合在独立Draft #13 `c0892a40`，固定`ff4b4f65`的Core583通过；11:00前只读核该新头PR CI仍在运行，不能称已放行。主P3、P4和P6尚未合入integration。P3修复后的10点固定主树v4为2299通过/1严格xfail/1告警，Core582通过；固定P4 `95df0f9c`的v4为2751通过/1严格xfail/1告警，新timer/监听/游标不在该宽验源。11点新固定源完整回归在途；原脚本仍46/47、扩展13/13，X03原四条断言不改。P6成功CI实际测试合并预览`c79b9e6a`，19项B1 PG跳过不能算通过。见`../evidence/P3/2026-10-21-main-queue-audit.md`及各固定源报告。以下08:14段是历史观察，已解决的case重放错误不再作为当前缺口，但原红档案保留。

2026-10-21 08:14（北京时间）历史状态复核：已从精确b9基线建立`v4/integration`并普通合入P1b；Draft PR #12头`2ca1378e958304547907671564b16aa631103fc0`，迁移/人工scope五项目标通过，完整组合门仍在途。P3尚未合入：08点固定`9a6f882d`（远端`428649b6`）Core581通过，完整v4为1934通过/1失败/1严格xfail；原指定脚本46/47、独立扩展13/13。失败为真实case_update效果后的直接幂等重放，后续修复独立进行，不能把目标绿改写成固定头全绿。公开options、可信runtime配置、只读并行、core4回填和切换CLI已有独立证据；真实K3 encoder、X03原发送断言及旧DOM回执仍未收口。具体门和历史记录见`../execplans/P3_agent_runtime.md`及08点固定头报告。

## 1. 基线、版本与责任

第一次集成从已核`v4/main`新建`v4/integration`；已有该分支时保留历史、核前次回执并续作，不重建或reset。每次记录merge前base、远端精确SHA、merge后SHA、契约版本和测试数字。PR号以下来自33号队列，执行前仍须核实际head/CI，不能把当前远端快照当未来验收。

主线负责既有运行入口、工具接线、仓储/API、迁移协调与集成回归。模块线只交纯模块/契约，前端线独占`web/**`，命理线独占Charts/skills/knowledge。冲突涉及他线独占文件时在集成分支按契约处理、保留来源，不回写他线工作树；未定行为记待决，先用受控替身或继续下一模块。不能把纯函数或Mock回执当持久保存/真实送达。

## 2. 分支合入顺序

| 顺序 | 来源与范围 | 先决条件和预计冲突 | 该步必须通过的闸门 |
| --- | --- | --- | --- |
| 0 | `v4/main`当前已合P1+P2基线 | 核精确SHA、干净工作树、迁移1–7不变；记录独立Core/Charts环境 | 基线Core、v4、Charts、web回归可复现；凭据清空、追踪关闭、隔离PG |
| 1 | P1b `v4/p1b-k3-hardening`，#9 | models配置、中央HTTP守卫、usage账本、0008；P3不得保留第二套guard/可信角色生成逻辑 | U37错误分类、U38≤2全局在途/按角色分区/额度立即全停、U39推理回传/高effort/禁止关闭思考、体积守卫、所有物理入口经过中央门；全用替身 |
| 2 | P3 `v4/p3-agent-runtime`，#8 | Agent Loop、ContextEngine、RuntimePort、工具、dispatcher、旧读取端；与P1b模型端口与epoch/lease冲突风险高，尤其保留中央HTTP guard与socket shutdown两边效果 | 当前真实`--target v4`原46/47，X03原发送断言待脑；公开options已接，不等于整项完成。须收口M2–M8、core3/core4、事件契约、取消/串行/续租/U41与新组合回归，才能满足脚本100%门 |
| 3 | 模块线 `v4/mod-organize`，#10 | 先合新增纯模块，再逐个接线；不能一次导入便宣称全部运行集成完成 | 下节各模块专门门+完整回归；记录现有质量限制，开发集分数不能盖盲评失败 |
| 4 | 命理线 `v4/p8-calc`，#5 | charts_service适配器切P8原生口径；chart_compute参数/多文档依据/方法/时区/别名可能冲突 | Charts合成黄金值与边界测试；owner/subject/revision/撤销、真实源Pointer、跨方法差异、boundary_alerts；无P8时保留v3适配器并明确降级 |
| 5 | 前端线 `v4/p10-frontend`，#6 | 依据`web/src/night/**/port.ts`和主线`api_*.md`接线；事件payload/错误/游标/无痕/区话题差异 | 生产构建、单元/DOM/无障碍/性能与视觉矩阵；本机HTTP/SSE端到端，不以Mock图替代真实API |
| 6 | 文档线，#7 | 接线后的使用说明/迁移说明和链接；分支名/精确head执行前核实 | 代码/契约/样例/回执一致；无密钥、私有正文或未经实测Go描述 |

每次实际merge后完整跑Core、v4、Charts、web再进入下一分支，不把单分支绿替代组合绿。之后每天对已接收的新提交普通merge一次；上次失败先留回执、定位可独立修复边界，禁止带着未解释失败继续宣称整体可用。

## 3. 模块线接线次序与具体门

模块线已交四份说明，可在执行前以`git show origin/v4/mod-organize:docs/v4/integration/mod/<文件>`只读核最新版本。此次路线图核到README/Q1–Q4；其记载是模块线本地证据，不是主线集成通过。

| 次序 | 模块/后续主线阶段 | 预期接线与冲突 | 专门测试闸门 |
| --- | --- | --- | --- |
| 3a | P5b A整理引擎 → 主线P5b B | 先P3完整ContextEngine，再区/topic实体、API、topic_route、分区上下文；A/C继续由模块/前端线负责 | 合成PG expected_revision、owner隔离、批次幂等/撤销/逆操作；旧历史真实应用必须用户审阅。关键词盲评失败路径只提供待审候选 |
| 3b | P6结构/旧lint/critic → Loop接线 | Q2中StructuralFinding不能直接转ProgramIssue；绑定同一次Clock与本稿证据。legacy_lint只告警；评审独立上下文、普通revise仅一次 | 结构负例、未知别名/假回执、一次修订、fail-open与危机例外、撤销/epoch/lease；未校准项record_only，脚本评审不当人标校准 |
| 3c | P7规则/晨报编排 → 调度/Outbox | Q3纯decision不代替PG领取事务；日计数、撤销、接收度和binding须事务内重读 | 并发领取、日界/DST/提醒到期、sent/uncertain不重发；D4默认不开使用提醒、不登记紧急联系人；无真实推送 |
| 3d | P9卡片/action token/CardKit → 网关 | Q4内存token换PG单次能力账本；官方字段与权限仍需核，不把候选JSON当已获飞书接受 | 假飞书HTTP、重复/过期/跨owner token、原子业务命令、同卡恢复、取消/lease/uncertain；2.5秒合并，0真实发送 |
| 3e | U4 `TimeRangeParser`实现 → 主线接口替换 | 按Z6主线保留接口/替身，不复制第二实现；同一显式Clock与owner时区，完整不确定范围/歧义 | 基准2026-10-17周六、正反例≥20、跨午夜/年/月/DST；本机Tokyo/UTC/Shanghai切换不影响断言 |
| 3f | 记忆2.0/后台反思/关于我 → P5 | 复用模块纯计算、主线负责授权输入/来源和持久事务；不由模型直接写画像或旧历史 | M/R/F/KU/TM/MS脚本、来源撤销、无痕不入长记忆、确认/修订/幂等、旧core3读取兼容 |
| 3g | SSE核心 → P4 | 按冻结events_v1/schema而非临时字段；journal/落库/pg_notify/Last-Event-ID游标兼容 | 重连补发/去重/顺序、text_reset、取消≤2秒、owner隔离；24小时清理text_delta且保留必要收据，X类脚本全绿 |

若模块间存在依赖，先合纯模块，再在`v4/integration`子分支做小接线、目标测试后普通merge回来。上表是接线次序，不要求为同一源分支制造七个重复merge；每片单独回执，不能把源分支merge完成等同七片完成。

## 4. 迁移号与校验和裁定

28号Z5覆盖旧ExecPlan的预分配草案：已发布/已应用0001–0007原字节不改；**0008归P1b model_usage，0009预留P5b B区/话题，之后0010及以后按最终合入顺序发放。** 不提前给pgvector/retire等占号。各分支有撞号时，在尚未发布的集成候选中协调重新编号及所有manifest/校验和/测试引用，普通merge完成，不通过rebase改写别人历史。

重新编号只针对未应用的新迁移；任何环境已实际应用的迁移都保持原checksum并加前向迁移。每片必须测试新隔离库全量初始化、前一schema增量升级、重复verify无变、运行角色无DDL、owner与writer分离。不能把P1b0008或P5b0009装入固定B1 b9包；B1真实授权仍只5–7，tzdata随B2。

## 5. 共享契约与组合测试

事件类型、序列化和客户端按已落盘的`docs/v4/contracts/events_v1.md`、`events_v1.schema.json`冻结；结果按`core4_envelope_v1.md`及相应Schema冻结，已有89项契约切片证据。present_options/options已有公开API目标证明，见`2026-10-21-runtime-api.md`；冻结形状和单项证明仍不等于各线已完整组合。新增字段/枚举必走版本兼容策略和正反例；服务端/模块/前端不得各写一套看似相同的类型。core3.0读取端保留兼容，旧payload不能被新版解析默认覆盖成成功结果。

完整回归入口以当次`.github/workflows/ci.yml`为准，当前已有：

    python -m unittest discover -s tests -p 'test_core*.py' -v
    python -m pytest tests/v4 -q
    python tools/eval/runner.py --mode scripted --target fake --self-test
    npm test
    node tests/dom.test.cjs
    node tests/report-settings.dom.test.cjs
    node tests/method-limits.dom.test.cjs
    node --check static/app.js
    npm run build

Charts使用独立锁定Charts解释器，Core配置`CHART_PYTHON`，命理线Golden/属性/边界入口接入后追加精确命令；新`web/`采用其package脚本，不假设旧根目录npm命令已覆盖新前端。`--target fake`只验证框架；实际ScriptedProvider/v4目标现已接通，01:00窗口原47为46/47，报告见`../evidence/P3/m8-v4-2026-10-21/full-0100/`，扩展13单独报告，不用fake或改断言补成绩。ModelPort用MockTransport/ScriptedProvider，全部真实入口都清凭据/关追踪；真人开始CLI只做替身演练，不能无人值守自动触发真实批次。所有物理入口经过P1b统一守卫的组合结论仍须集成后证明。

每次完整回归在北京时间每小时00–15分开始，测试并行进程总≤4；目标回归可在其余时间跑。每40分钟至少提交推送一次；长任务先保留可审wip/局部证据。CI须是本次精确merge head，旧绿、排队和skip均不替代通过。

## 6. 回执与未完成事项

每步输出`docs/v4/release/integration/<日期>_<分支>.md`：base/source/merge SHA，修改/冲突决策，迁移号与checksum，实际命令/通过失败跳过/耗时，契约正反例及仍未验证项，0模型/0真实飞书/0服务器声明（有授权动作另分轨）；阶段回执按AGENTS§11。汇总引用对应回执，不复用上次数字。

已执行第一片普通merge：`49d40dd69d299200d4549f22b70931dbf47ac171`，父为基线计划提交`092ec036361a09171be204d7331b9157f2a721fc`与P1b`8087d7fa64839dc5a080491fd5db4e358f5814ec`；后续仅更新计划到`2ca1378e`并推送Draft PR #12，未合P3或其他线。原0001–0007字节不变，0008指纹`5eef5d65363baa0ab4dc8ec9763b85136f4ba249688330b9cd8448f0b39ccbcb`；完整回归、Node22等价与精确merge头CI尚待结果。详细记录见`../execplans/integration_20261021.md`。B1仍受真实Linux/native恢复阻塞，固定b9不改；本片无服务器操作。

P3原X03四条发送断言、真实K3 encoder、P1b/P3组合、旧DOM回执与08点幂等重放失败仍是未完成门；不能以各项目标绿替代对应失败记录或尚未完成的新精确头Linux CI。P6接线只在独立Draft #11普通更新基线，默认关闭；不代表主P3或集成分支已接入。模块主线接线、P8原生适配、新前端真实API与完整组合回归继续按上表推进。

P3 stage仅有离线计划`P3_stage_plan.md`，当前No-Go，先在本机隔离库用合成模型完成v3→v4→v3。当前B1的条件B/D只覆盖固定b9，不含P3启用；正式P3服务器部署或真实质量请求需相应明确授权。本周集成代码不是部署许可。

## 修订记录

- 2026-10-21 11:04 +08:00：新增当前版本/精确测试源与CI实际checkout判定，保留08:14失败历史；本次只更新文档，没有执行新的merge或部署。

- 2026-10-20夜：建立合并顺序、冲突/迁移与组合闸门草案，未执行合并。
- 2026-10-21 01:06 +08:00：对齐实际v4候选、46/47及独立13报告、公开options待接、P1b未集成/K3缺失和宽回归失败状态；未运行测试或外部操作。
- 2026-10-21 08:14 +08:00：据已回收的固定头结果及实际P1b普通merge更新当前状态，保留01点历史和08点失败；完整集成门未预告通过，无主干合并或部署。
