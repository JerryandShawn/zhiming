# v4 集成与合并路线图

本文件是顺序与测试闸门，不是合并或部署回执。依据用户10-20夜间队列、28号Z5与33号本周队列；本周集成只进`v4/integration`，向`v4/main`保持草稿PR，等大脑与用户复核。任何一条线不得自行合并`v4/main`或`main`。普通merge，不rebase、不强推。B1发布包仍固定b9a89b6，以下集成不能改变B1包或放行其Linux阻塞。

## 1. 基线、版本与责任

第一次集成从已核`v4/main`新建`v4/integration`；已有该分支时保留历史、核前次回执并续作，不重建或reset。每次记录merge前base、远端精确SHA、merge后SHA、契约版本和测试数字。PR号以下来自33号队列，执行前仍须核实际head/CI，不能把当前远端快照当未来验收。

主线负责既有运行入口、工具接线、仓储/API、迁移协调与集成回归。模块线只交纯模块/契约，前端线独占`web/**`，命理线独占Charts/skills/knowledge。冲突涉及他线独占文件时在集成分支按契约处理、保留来源，不回写他线工作树；未定行为记待决，先用受控替身或继续下一模块。不能把纯函数或Mock回执当持久保存/真实送达。

## 2. 分支合入顺序

| 顺序 | 来源与范围 | 先决条件和预计冲突 | 该步必须通过的闸门 |
| --- | --- | --- | --- |
| 0 | `v4/main`当前已合P1+P2基线 | 核精确SHA、干净工作树、迁移1–7不变；记录独立Core/Charts环境 | 基线Core、v4、Charts、web回归可复现；凭据清空、追踪关闭、隔离PG |
| 1 | P1b `v4/p1b-k3-hardening`，#9 | models配置、中央HTTP守卫、usage账本、0008；P3不得保留第二套guard/可信角色生成逻辑 | U37错误分类、U38≤2全局在途/按角色分区/额度立即全停、U39推理回传/高effort/禁止关闭思考、体积守卫、所有物理入口经过中央门；全用替身 |
| 2 | P3 `v4/p3-agent-runtime`，#8 | Agent Loop、ContextEngine、RuntimePort、工具、dispatcher、旧读取端；与P1b模型端口与epoch/lease冲突风险高 | M2–M8、core3/core4兼容、事件/信封v1契约、2秒取消、串行/续租、U41；P3脚本100%，真正`--target v4`入口实现后才验收 |
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

事件类型、序列化和客户端按`docs/v4/contracts/events_v1.md`、`events_v1.schema.json`冻结；结果按`core4_envelope_v1.md`及相应Schema冻结。文档文件由主线契约里程碑补齐，未落盘前不能称冻结完成。新增字段/枚举必走版本兼容策略和正反例；服务端/模块/前端不得各写一套看似相同的类型。core3.0读取端保留兼容，旧payload不能被新版解析默认覆盖成成功结果。

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

Charts使用独立锁定Charts解释器，Core配置`CHART_PYTHON`，命理线Golden/属性/边界入口接入后追加精确命令；新`web/`采用其package脚本，不假设旧根目录npm命令已覆盖新前端。`--target fake`只验证框架，P3 v4验收必须实际运行ScriptedProvider/v4目标，入口尚未实现时标阻塞，不用fake成绩补位。ModelPort用MockTransport，全部真实入口都清凭据/关追踪；真人开始CLI只做替身演练，不能无人值守自动触发真实批次。

每次完整回归在北京时间每小时00–15分开始，测试并行进程总≤4；目标回归可在其余时间跑。每40分钟至少提交推送一次；长任务先保留可审wip/局部证据。CI须是本次精确merge head，旧绿、排队和skip均不替代通过。

## 6. 回执与未完成事项

每步输出`docs/v4/release/integration/<日期>_<分支>.md`：base/source/merge SHA，修改/冲突决策，迁移号与checksum，实际命令/通过失败跳过/耗时，契约正反例及仍未验证项，0模型/0真实飞书/0服务器声明（有授权动作另分轨）；阶段回执按AGENTS§11。汇总引用对应回执，不复用上次数字。

当前仅完成路线图，未创建/merge集成分支，未核本次PR新head。B1仍受真实Linux恢复阻塞；P3脚本v4入口、模块主线接线、P8运行适配、新前端真实API与完整组合回归均由后续里程碑证明。真实Kimi评测仍须用户在线说“开始”，正式上线仍须本人“上线”和相应条件授权；本周集成代码不是部署许可。
