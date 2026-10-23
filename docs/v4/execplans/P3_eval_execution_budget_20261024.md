# P3：Core30私密执行预算的真实累计

本活计划遵循AGENTS与`.agent/PLANS.md`。记录使用北京时间；仅真实隔离本机PG和MockTransport，不发真实模型、飞书或服务器请求。所在分支为`v4/p3-wire-execution-budget-20261024`；已有c5e物理UUID/Journal锚点不重复实现。

## Context and Orientation

复用`tools/eval/targets/v4_core30.py::Core30LiveTarget._attempt`在实际execute之前捕获的LifecycleBinding、`mingjing_core/application/runtime_limits.py::policy/validate_pin/deadline`、`mingjing_core/agent/loop_policy.py::RunControl`及原私密生命周期。`agent_runtime.py::_cycle`的control_factory发生在原RuntimeLimits持久pin之后。每个模型步骤都会进入monitor，monitor不能负责关闭整个执行段。

原RunControl每次构造重记monotonic起点；业务FrozenClock和请求次数不能证明已耗执行秒数。本片只给Durable目标注入独立控制器，不修改共享生产RunControl、RuntimeLimits、模型配置、额度策略或记忆模块。

## Purpose / Big Picture

使专用目标在第一次实际发送之前，将真实执行段绑定到当前受信候选、原话、run/epoch、原限制凭据和执行者。整次execute退出后才用当前进程真实monotonic测量封段；跨进程只读取已闭合累计，不能拿另一进程的monotonic绝对值当时钟。累计预算耗尽、未知open或已有Journal却缺预算时拒绝后续发送。

## Progress

- [x] (2026-10-24 07:17:57 +08:00 实时复核录入) 建立最小实施计划；实现执行scope、PG预算helper、Durable窄接线与三个必要PG行为组，先静态审阅。首次创建未保存精确时间，不补造；原误填06:57已纠正。
- [x] 根授测试槽后仅跑新目标首链，记录真实结果及必要修正；首轮2通过/1失败，获批后仅复验唯一红节点1通过。
- [x] (2026-10-24 07:33 +08:00) 根完整审阅两个helper、三处调用方及新测试，受信scope/实际pin、成功清lease关闭、持久化后detach与旧queued只读范围成立，交根小提交。静态与两轮定向证据足够，不追加宽测或重复两绿；新提交CI另核。
- [x] (2026-10-24 07:27:59 +08:00) 六代码路径静态实现冻结；Ruff E/F/I/B/UP/SIM、120列格式及AST尺寸通过，新helper152/267行、新PG文件296行，最大函数54行。第三组补同原closed记录的模型binding漂移拒绝及原摘要不变，未新增节点/schema。尚未pytest/collect。
- [x] (2026-10-24 07:31:23 +08:00 实时录入) 首链实际开始07:28:17、结束07:29:03，2通过/1失败、44.26秒。成功多模型步和未知/缺失/旧只读两组已通过；累计耗尽组首次send抛既有ProviderStopped，尚未到达closed/0POST/下次拒绝断言。根批准仅修该新夹具、复验唯一红节点，不重复两绿。
- [x] (2026-10-24 07:32:30 +08:00 实时录入) 唯一红节点复验实际07:32:17.718–07:32:26.335，1通过、7.65秒。受信首次停止kind为ledger_unavailable，budget_unknown=False；实际closed累计1,562,000,000ns、零POST。恢复原factory后，真实BudgetStore.open明确累计耗尽拒绝，closed记录和原pin不变。新测试312行/最大函数54，静态检查通过；测试槽已释放，代码冻结交根审。

## Plan of Work

最多新增`tools/eval/targets/v4_execution_budget.py`和`v4_execution_budget_store.py`，以及一个专属PG测试文件。前者提供整次execute的scope和RunControl子类，后者用现有runtime_step保存来源、原限制和open/closed段。Core30只新增默认无效果的执行scope接缝；Durable `_ports`安装工厂，checkpoint/detach/attach与私密状态核闭合摘要。

scope早于Runtime.execute建立真实binding与monotonic起点；工厂在原限制已持久化后锁读实际leased run，校验`limit_epochs`原pin及deadline，首次POST前提交open。poll叠加旧closed累计和当前scope真实耗时，不调整原deadline、limit-pin或lease。关闭后成功run的lease已清，需核仍保存的executor_lease_sha256及原source/request/epoch，不要求旧token仍处running。合法工具会推进state_version，不能将最初完整依赖摘要恒等当关闭条件。

只有scope finally封段；monitor每步照常进入/退出。关闭异常不能静默变为成功，保留未知open。原global stop、ModelCancelled和进程控制异常保留；更晚的普通清理失败不能覆盖它们。任何来源撤销、段擦除或身份改变均不能通过put重新激活预算记录。未到工厂或未取得已验证pin的执行不制造closed证据，也不因此开放续跑。

## Validation and Acceptance

仅三个有意义行为组：第一组经真实Agent/PG和多个模型步骤确认整次execute只有一段，并验证正常成功清lease封段及checkpoint→detach→新对象attach保持累计、原deadline和pin。第二组使用合法短配置与真实monotonic/实际等待耗尽预算，后续尝试在POST之前拒绝，不能注入假elapsed。第三组核实际未知open、missing+Journal及身份漂移失败关闭，并明确旧无预算生命周期只允许只读兼容，不猜耗时0。

测试只替代供应商传输，不能替代PG业务、Journal、限制服务或SDK结果；不重复已有27绿。原81脚本金标与完整门不改，附着send、CLI resume、长5小时等待及真实评测均仍禁止。

## Surprises & Discoveries

RunControl.monitor由每个模型步骤调用；其finally不是整个execute终点。RuntimeState.pin在工厂之前保存执行者lease摘要，而成功finalizer会同事务清lease。新控制器需要显式持有scope对象，监控线程不能依赖不会自动传播的ContextVar。

根静态复核补充：原queued生命周期可能从未进入控制器，不能因预算只允许running/succeeded而拒绝旧只读观察；新read_closed仅在无预算时保留queued的未知耗时观察，有预算却queued仍拒绝。scope提前分配session不能代替成功checkpoint；detach现核真实control.save返回记录、binding及PG私密状态。第一组的新fact断言通过实际本轮Journal saved receipt定位完整summary/原话lineage，不能由已有种子fact满足。

首链唯一红的实际栈位于Core30._attempt对ModelUnavailable的转换分支。源码确认LoopCycle._model的confirmed包住首control.poll；LoopStopped会被转为ModelAttemptUnconfirmed并重新抛出，最后成为ProviderStopped。原log未保存safe kind，失败前的预算闭合、耗时及0POST断言尚未触达，不能将它们补称已通过。原证据保留于`private/safe-narrow-a3192047659d45d7a17914345f92b1f1/`。

获批复验在XML保存safe kind并通过全部后续断言；第二次恢复原factory，避免再次实际sleep造成原单次RunControl本身拒绝而误称累计保护。fixture只观察真实open的有限拒绝类别并原样抛出，不替代PG返回或制造耗时。复验原证据为`private/safe-narrow-65aef112837c4476ac04a9317ea8b1da/`。

## Decision Log

2026-10-24：默认Core30保持nullcontext，不启用此预算；Durable执行scope使用现有真实LifecycleBinding，工厂不从事后checkpoint自报字段赋权。现有未启用预算的生命周期保留只读观察兼容；任何后续执行资格都不能把缺预算解释为0秒。内部epoch/执行者变更或不明确阶段本片保守拒绝，不建立新的自动恢复权限。

2026-10-24 07:27:23 +08:00：按根静态审点明确异常优先级使用显式None判断，保留falsey原异常对象；close同时核当前原生authority、预算完整原anchor及最后段原lease。首个进程控制异常最高，原ProviderStopped/ModelCancelled或global stop不能被普通close错误替换。三个新行为组内加入正常清lease、checkpoint前detach拒绝、实际open后detach拒绝、原KeyboardInterrupt对象及queued旧只读兼容，不增加测试节点。没有已验证控制器的退出保持未知，不制造closed或执行资格。

2026-10-24 07:31:23 +08:00：根批准仅新累计耗尽夹具捕获受信ProviderStopped、记录safe kind并严格核ledger_unavailable和budget_unknown=False；实际closed至少1.1秒、首次0POST不减。第二次尝试前恢复原factory，spy真实BudgetStore.open并原样重抛，必须观察明确累计耗尽拒绝、原closed摘要/pin不变及0POST；不改生产或时间预算，不接受单改raises掩盖close失败。

## Idempotence and Recovery

使用原场景私密runtime_step及稳定run/epoch定位；在实际run行锁下核记录revision与完整段摘要。新进程只消费closed记录，遗留open/未知状态保持现场并拒绝，不猜补、不清停、不改旧记录来凑相等。失败后的测试记录不覆盖、不自动宽测或重试。

## Outcomes & Retrospective

实现与静态检查已就绪；首链2通过/1失败、44.26秒，获批仅复验唯一红节点1通过、7.65秒，两绿不重复。三个必要行为分轮通过，不称一次3/3。原metadata/XML/log分别保留在`private/safe-narrow-a3192047659d45d7a17914345f92b1f1/`及`private/safe-narrow-65aef112837c4476ac04a9317ea8b1da/`；实际首段多模型步9,703,999,999ns/2物理Mock请求，耗尽组1,562,000,000ns/0POST，均来自真实monotonic和PG闭合记录。仅六代码路径加本计划，未修改生产RunControl/RuntimeLimits、原81金标、配置、记忆代码或物理UUID锚点。此片仅累计预算基础，不能证明已开放同run跨进程续作、外部评审续作、正式模型质量、Linux部署或首发Go。

## 修订记录

- 2026-10-24 07:33 +08:00：根完成实际调用方/全部六代码路径审阅，接受分轮三行为证据并准备小提交；所有真实评测/附着执行/CLI/发布门继续关闭。

- 2026-10-24 07:17:57 +08:00 实时复核录入：记录根批准的scope边界、原pin权威、失败关闭、旧只读兼容与三行为验证范围；删除未经工具核实的06:57创建时间，不补造历史。
- 2026-10-24 07:27:23 +08:00：记录实现静态冻结、根审窄修及三必要行为组；测试等待根明确授槽。
- 2026-10-24 07:27:59 +08:00：仅第三组补原closed预算的模型身份漂移拒绝及摘要保持断言，代码最终静态冻结；仍未pytest/collect。
- 2026-10-24 07:31:23 +08:00：诚实记录唯一首链2绿1红与旧后续断言未触达；按根批准只修新夹具首停止捕获及第二次真实累计拒绝观察，不改生产、不复跑旧绿。
- 2026-10-24 07:32:30 +08:00：记录唯一红复验1通过及XML真实累计/零POST/明确耗尽拒绝证据；两绿不重复，释放测试槽，冻结全部七路径交根审阅。
