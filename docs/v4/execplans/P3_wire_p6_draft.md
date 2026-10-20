# P3 储备：隔离 P6 结构与旧 lint 接线草稿

本计划遵循 `.agent/PLANS.md`。独立工作树 `zhiming-v4-p3-wire-p6`，分支 `v4/p3-wire-p6-20261021`，基准7c07038；不合并主线或模块线，记录使用北京时间。

## Purpose / Big Picture

让真实P6纯结构检查和旧lint在实际Loop的交付路径运行，修正确定星期/未知引用/虚假回执并保留原答。旧lint只告警；普通校验故障开放，最终租约、取消和撤销闸门仍严格拒绝。默认关闭，只能由可信构造注入，HTTP和模型不可自行开启。

## Context and Orientation

已全文读模块线Q1–Q4接线说明和P6源码。模块结构检查与当前P3的`validation.structural.check_structure`同名冲突，故保留原P3接口；将模块线固定ebfa22f的11个纯依赖字节相同放入`validation/p6_candidate/`，SOURCE_MANIFEST逐项核源SHA和blob。复用AgentRuntime、RuntimeState.authority、persisted_receipts、真实实体/别名、clock.FrozenClock与原Finalizer；不改原模块工作树、前端、P8或现有P3工作树。

## Progress

- [x] (2026-10-21 01:18) 核四份说明与实际依赖；从固定module SHA复制11纯模块，保留原字节和相对导入，未覆盖P3 structural。
- [x] (2026-10-21 01:27) 持久固定单次Clock、真实scope/receipt/alias投影，Runtime显式可选桥及只告警lint。
- [x] (2026-10-21 01:27) 新增22项通过；最终相关90项20.40秒通过、零warning。18文件Ruff/format通过，7适配文件400/60通过；冻结离线草稿。

## Surprises & Discoveries

P6 StructuralResult与P3 StructuralResult字段不同，不能直接覆盖或强行转换。现有critic proof绑定真实模型行，P6确定性改稿后不能冒称critic审过该稿；本草稿对改稿明确evidence_only，保留review=skipped，不伪造模型步骤。

模块把未保存提示加在整句之后，P3旧检查又在“已经保存”词组后加同一注释。经root授权，仅wire目录的P3结构检查补句内精确注释幂等；完整原注释不再重复，但unsupported_save_claim告警仍保留。跨句旧注释、新保存句、近似拼写/他处/引用中的注释均不能抑制新警告。实际saved规则原样保留。

## Decision Log

P6候选包来源字节不做格式化或重新实现；适配在独立application文件。只把当前真实授权投影交给纯检查，普通纯函数异常固定code告警、不记录异常正文。PG身份、source/版本、实际回执错误不进入fail-open捕获。最终Finalizer仍做独立原子严格检查。未接P6 v2 critic、校准、自动修订、真实调用或使用提醒。

父代理授权的注释兼容是相对7c07038的独立19行小diff，不是复制覆盖P3 validation。正式集成要人工核`validation/structural.py`与当时主线注释/回执逻辑的冲突；此分支不合并。所有findings只以受控code/count和前后hash记录于受保护runtime_step，不给冻结公开review结构添lint字段。

## Plan of Work

先做实际投影和持久Clock，再插入draft/final两次纯检查；旧lint使用完整交付text和有界兼容摘要，不能截断用户答案。run记录只保留受控code/count与hash，卡片仍走原严格finalizer。之后用真实PG/ScriptedPort调用真实候选模块，验证不开桥旧路径不变和严格安全闸门。

## Concrete Steps

    python -m pytest tests/v4/agent/test_p6_wire_pg.py -q
    python -m pytest tests/v4/agent/test_agent_runtime_pg.py tests/v4/agent/test_present_options_runtime_pg.py -q

## Validation and Acceptance

冻结clock确定日期纠正星期；未知别名与无对应真实回执加注；长自由文本完整交付而lint不报摘要超长；纯验证器故障不吞答、不泄露异常正文。运行中撤销或取消后不得final。包内11文件hash等module源，默认关闭且没有任意动态导入或外部请求。

## Idempotence and Recovery

run/epoch固定时刻与阶段/hash记录幂等保存。重放不替换已有Clock；最终发布仍使用原租约与源撤销fence。没有迁移；移除显式桥即可回到原P3，候选包不替换旧结构接口。

## Artifacts and Notes

证据 `docs/v4/evidence/P3_wire/2026-10-21-p6-draft.md`及同名JSON。SOURCE_MANIFEST是依赖来源证明，不是模块合并或完整P6验收。

## Interfaces and Dependencies

新增P6ValidationBridge及投影/记录helper；AgentRuntime仅增加可信构造可选参数。无新依赖、模型、HTTP或数据库迁移。

## Outcomes & Retrospective

实际Loop中的离线候选已验证：默认关闭、明确注入后真实P6星期/相对日期/未知引用/目标对应回执检查生效；完整21k自由文本交付，lint仅告警；结构或lint故障保答、不泄露异常，lint故障不撤销已完成的星期纠正；取消/撤销不final。新增22项和最终相关90项通过。P6 v2独立critic/校准、专业claim revalidator、farewell识别与正式集成未完成，farewell仍false。未访问服务器、模型或飞书；没有迁移、合并或前端修改。root统一提交/推送，仅草稿PR。

## 修订记录

- 2026-10-21 01:18 创建独立草稿，固定来源及fail-open/严格提交边界。
- 2026-10-21 01:27 冻结候选，补90项真实模块/PG相关回归、注释幂等兼容及明确的未集成边界。
