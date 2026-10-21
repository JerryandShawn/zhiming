# P3 储备：隔离 P6 结构与旧 lint 接线草稿

本计划遵循 `.agent/PLANS.md`。独立工作树 `zhiming-v4-p3-wire-p6`，分支 `v4/p3-wire-p6-20261021`，初始基准7c07038。2026-10-21早间经主线授权，将P3固定9a6f882d普通合入本草稿更新基线；不合并到v4/main或main，不合并模块线，记录使用北京时间。提交和推送由主线统一办理。

## Purpose / Big Picture

让真实P6纯结构检查和旧lint在实际Loop的交付路径运行，修正确定星期/未知引用/虚假回执并保留原答。旧lint只告警；普通校验故障开放，最终租约、取消和撤销闸门仍严格拒绝。默认关闭，只能由可信构造注入，HTTP和模型不可自行开启。

## Context and Orientation

已全文读模块线Q1–Q4接线说明和P6源码。模块结构检查与当前P3的`validation.structural.check_structure`同名冲突，故保留原P3接口；将模块线固定ebfa22f的11个纯依赖字节相同放入`validation/p6_candidate/`，SOURCE_MANIFEST逐项核源SHA和blob。复用AgentRuntime、RuntimeState.authority、persisted_receipts、真实实体/别名、clock.FrozenClock与原Finalizer；不改原模块工作树、前端、P8或现有P3工作树。

## Progress

- [x] (2026-10-21 01:18) 核四份说明与实际依赖；从固定module SHA复制11纯模块，保留原字节和相对导入，未覆盖P3 structural。
- [x] (2026-10-21 01:27) 持久固定单次Clock、真实scope/receipt/alias投影，Runtime显式可选桥及只告警lint。
- [x] (2026-10-21 01:27) 新增22项通过；最终相关90项20.40秒通过、零warning。18文件Ruff/format通过，7适配文件400/60通过；冻结离线草稿。
- [x] (2026-10-21 08:01) 对P3固定9a6f882d（远端428649b6、tree d6a4f0d9）执行普通`--no-commit --no-ff`合入；唯一构造参数冲突同时保留`p6_validation=None`和`runtime_config=None`及双方校验。11候选文件SHA256、Git blob、来源提交路径映射和源字节全部一致。
- [x] (2026-10-21 08:07) 历史事项受限投影及45项新增真实PG正反例通过，旧P6的22项保持通过；三组窄检查共252项通过（67/25.92秒、168/68.22秒、17/4.10秒），均无skip/warning。所有case只投影P6现有规则实际需要的标题/状态与身份版本字段。
- [ ] (2026-10-21 08:07) 普通合并候选待root统一提交/发布草稿PR新头并核Linux CI；本机Windows结果不能替代Linux验收。

## Surprises & Discoveries

P6 StructuralResult与P3 StructuralResult字段不同，不能直接覆盖或强行转换。现有critic proof绑定真实模型行，P6确定性改稿后不能冒称critic审过该稿；本草稿对改稿明确evidence_only，保留review=skipped，不伪造模型步骤。

模块把未保存提示加在整句之后，P3旧检查又在“已经保存”词组后加同一注释。经root授权，仅wire目录的P3结构检查补句内精确注释幂等；完整原注释不再重复，但unsupported_save_claim告警仍保留。跨句旧注释、新保存句、近似拼写/他处/引用中的注释均不能抑制新警告。实际saved规则原样保留。

早间P3已支持有当前真实case_list证明的历史事项，以及选中事项单次状态写入后的严格引用。旧P6投影仅允许active/open/pending，会在校验桥提前拒绝这些合法引用；即便未引用该历史别名也受影响。投影不能通过笼统扩展状态集合修复，更不能把未选事项的goal、正文或来源链交给P6。新适配只保留标题、状态和身份/版本字段，历史态复用P3现有严格case证明；open索引同样必须用当前已完成步骤重算case_index_lineage和精确别名指纹。

## Decision Log

P6候选包来源字节不做格式化或重新实现；适配在独立application文件。只把当前真实授权投影交给纯检查，普通纯函数异常固定code告警、不记录异常正文。PG身份、source/版本、实际回执错误不进入fail-open捕获。最终Finalizer仍做独立原子严格检查。未接P6 v2 critic、校准、自动修订、真实调用或使用提醒。

父代理授权的注释兼容是相对7c07038的独立19行小diff，不是复制覆盖P3 validation。正式集成要人工核`validation/structural.py`与当时主线注释/回执逻辑的冲突；此分支不向v4/main或main合并。所有findings只以受控code/count和前后hash记录于受保护runtime_step，不给冻结公开review结构添lint字段。

2026-10-21 08:01：主线批准在P6草稿普通合入指定P3，而非将P6并入v4/main。唯一文本冲突保留两套keyword-only构造参数和校验；RuntimeLimits/config安全上限不由P6替代。P6仍默认关闭，只能可信构造显式启用。历史/开放索引校验依赖现有P3证明与真实PG，不改11份模块候选源，也不改原测试断言。P3的socket shutdown取消候选随基线引入，但Windows证据不能替代新P6精确头Linux CI，两秒上限不放宽。

P6纯结构检查只消费records的别名集合，case回执投影只消费id/entity_kind/title，旧lint只分组fact和interpretive_claim；没有case.goal/state/source_refs规则。故所有case都采用标题/状态窄投影，保留旧校验所用真实回执标题；完整已选事项资料继续由P3上下文和独立Finalizer按原授权处理，不让P6额外读取未选目标或正文。

首轮新增夹具暴露两处测试准备错误：普通“历史事项”原话不符合Z3进展触发规则，case_list依法不可见；无痕是request字段而非core_runs独立列。只将新E2E原话补上现有合法“那件事的进展”触发，并把新反例写到真实request.incognito；不修改可见性、数据契约、旧测试或预期断言。首次67项为56通过/11失败，修正后结果另记，不能把首轮当成验收通过。

第二轮67项中57通过，10个新E2E的正文与历史引用已经成功，剩余是新监测断言误把本轮合法用户消息也当作case窄投影。监测改为只收entity_kind=case，仍严格逐项比较原六个白名单字段与状态；不删减正文、版本、原话闭包或写权限断言，也不改生产实现。

## Plan of Work

先做实际投影和持久Clock，再插入draft/final两次纯检查；旧lint使用完整交付text和有界兼容摘要，不能截断用户答案。run记录只保留受控code/count与hash，卡片仍走原严格finalizer。之后用真实PG/ScriptedPort调用真实候选模块，验证不开桥旧路径不变和严格安全闸门。

## Concrete Steps

    python -m pytest tests/v4/agent/test_p6_wire_pg.py -q
    python -m pytest tests/v4/agent/test_agent_runtime_pg.py tests/v4/agent/test_present_options_runtime_pg.py -q

早间更新基线后的第一组窄验证（在隔离PG、空凭据/关闭追踪环境，并在主线释放测试位后启动）：

    python -m pytest tests/v4/agent/test_p6_wire_pg.py tests/v4/agent/test_p6_annotation_compat.py tests/v4/agent/test_p6_case_projection_pg.py -q
    python -m pytest tests/v4/agent/test_runtime_config.py tests/v4/agent/test_runtime_limits_pg.py tests/v4/agent/test_historical_case_index_pg.py tests/v4/agent/test_historical_case_index_guards_pg.py tests/v4/agent/test_case_status_write_proofs_pg.py -q
    python -m pytest tests/v4/models/test_socket_cancellation.py tests/v4/agent/test_dispatcher_http.py tests/v4/agent/test_eval_v4_pg.py::test_x04_measures_quiet_loopback_http_and_persists_interrupted_partial -q

## Validation and Acceptance

冻结clock确定日期纠正星期；未知别名与无对应真实回执加注；长自由文本完整交付而lint不报摘要超长；纯验证器故障不吞答、不泄露异常正文。运行中撤销或取消后不得final。包内11文件hash等module源，默认关闭且没有任意动态导入或外部请求。

## Idempotence and Recovery

run/epoch固定时刻与阶段/hash记录幂等保存。重放不替换已有Clock；最终发布仍使用原租约与源撤销fence。没有迁移；移除显式桥即可回到原P3，候选包不替换旧结构接口。

## Artifacts and Notes

证据 `docs/v4/evidence/P3_wire/2026-10-21-p6-draft.md`及同名JSON。SOURCE_MANIFEST是依赖来源证明，不是模块合并或完整P6验收。

## Interfaces and Dependencies

新增P6ValidationBridge及投影/记录helper；AgentRuntime仅增加可信构造可选参数。无新依赖、模型、HTTP或数据库迁移。

## Outcomes & Retrospective

01:27初始候选在实际Loop中的离线验证：默认关闭、明确注入后真实P6星期/相对日期/未知引用/目标对应回执检查生效；完整21k自由文本交付，lint仅告警；结构或lint故障保答、不泄露异常，lint故障不撤销已完成的星期纠正；取消/撤销不final。新增22项和最终相关90项通过。P6 v2独立critic/校准、专业claim revalidator、farewell识别与正式集成未完成，farewell仍false。未访问服务器、模型或飞书；无迁移或前端修改。root统一提交/推送，仅草稿PR。

08:07早间基线更新已完成本机窄验证：新45项覆盖真实Runtime的5种合法事项状态与重复索引、精确完成步骤、伪造别名/epoch/seq/hash、撤销、跨owner/subject、无痕拒绝、非case不能借状态例外及选中事项真实单次状态写证明。旧22项保持通过；配置/限额/历史/状态证明/Runtime与恢复168项通过；socket与真实loopback HTTP取消/X04共17项通过，原两秒约束未放宽。仅3组串行使用1测试位，无skip/warning。11候选源仍冻结于ebfa22f8且字节一致，无新依赖或迁移。当前普通合并尚未提交，新精确头Linux CI、完整评测和全部回归仍未验；不能借用01:27旧头90项或P3 Windows结果当成Linux验收。

## 修订记录

- 2026-10-21 01:18 创建独立草稿，固定来源及fail-open/严格提交边界。
- 2026-10-21 01:27 冻结候选，补90项真实模块/PG相关回归、注释幂等兼容及明确的未集成边界。
- 2026-10-21 08:01 普通合入主线指定9a6f882d更新草稿基线，保留两套受信构造参数；记录历史索引投影缺口与最小修复/待测边界，11源字节不变。
- 2026-10-21 08:07 完成252项串行窄验证，记录新增夹具修正原因、全case窄投影依据、精确父提交及尚未验证的Linux CI边界。
