# P3：记录并验证事项的完整自写版本链

本ExecPlan遵循`.agent/PLANS.md`。北京时间2026-10-21 08:02创建。root批准完整链；当前08点四个全量测试槽全占，只写代码/文档与静态检查，收到空槽通知后最多1个窄pytest进程。root统一提交；无服务器、真实模型、飞书、依赖安装、迁移或合并。

## Purpose / Big Picture

用户同一轮先改目标再暂停/关闭同一事项时，两个实际更新都已保存，原e#应能凭完整真实证据完成引用。现有严格单次门正确拒绝缺中间证明的版本跳跃。本片在真实更新原事务内记录版本化私有前后状态与精确update输入，提交时逐revision核完整链；旧运行缺证据仍只保留单次路径，不能补造历史或拿最后一张回执跨越缺环。

## Context and Orientation

复用`application/agent_tools_cases.py:mutate_case`、`repositories/postgres.py:update/put/_operation`、`agent_pending_effects.py:_initial/_original_call/_source`、已有completed包装、`agent_case_write_citations.py`、原Finalizer租约/撤销/依赖门。repo.update传给put的是dict(old,**changes)完整输入，operation digest包括旧metadata，ContextBuild没有完整历史Case row，不能由最终行反推早期完整digest。

私有证据存现有runtime_step，带run/epoch/seq、target_case_id/case_ids/source_ids/fact_ids、版本与内容hash，接原30天保留清理和撤销闭包。证据不设置实体顶层case_id，避免私有记账改变公开事项聚合版本；范围保存在data中。原started/空output恢复的正规证明不降低，core4/SSE、L3已发字节、旧initial snapshot格式、当前用户授权与selected_case范围不改。旧07号R08和冻结评分不改；补充28储备a/c、33一§1的连续自写边界。

## Progress

- [x] (2026-10-21 07:56 +08:00) 原真实多写反例2fail/3.53秒混合组：goal rev2→paused/closed rev3均已保存，原alias rev1最终被严格单次门拒绝，0assistant/result，无xfail。
- [x] (2026-10-21 08:02 +08:00) root批准同事务versioned before/after+精确update input证据与完整链；明确旧run不可补造，先计划再实施。
- [x] (2026-10-21 08:20 +08:00) 真实case_update原事务写私有effect证据、独立协议声明和body-free run/epoch/seq标记；mutation重放不重建before，记录/标记/体积故障回滚真实effect。
- [x] (2026-10-21 08:20 +08:00) 共享正规completed intent证明，逐revision核模型/参数/来源/receipt/mutation/operation完整digest与before/after衔接；支持分轮、同响应内2–3写及两事项交错。
- [x] (2026-10-21 08:20 +08:00) 已完成50项隐私/协议/链目标（34.88秒）及42项结构/交错/Runtime分类目标（29.55秒）；后续组合含原started恢复和原08快照失败，仍在验证中。
- [x] (2026-10-21 08:28 +08:00) 第二真实effect已提交而Journal仍started的同回复/分回复恢复：首次2 fail/2.34秒，严格versioned pending链和Case专属旧receipt重放接点修复后，45项含原started/矩阵目标绿。
- [x] (2026-10-21 08:28 +08:00) 最终21文件真实PG组合227 passed/114.86秒，0skip/0xfail/0warning；25源/测Ruff/格式和400行文件/60行函数界限绿。证据冻结交root，后续固定tree合法窗口全量。
- [x] (2026-10-21 08:37 +08:00) 独立审计解冻，真实复现canonical used_fact_ids/source_fact_id撤销后proof未清（2fail/1pass，2.68秒），精确采集三种既有字段后隐私12pass/6.50秒。
- [x] (2026-10-21 08:37 +08:00) 三项effect/marker/protocol全失单写首红1fail/1.69秒；获root授权新增RuntimeState.pin独立per-epoch capability，只全新空epoch首次冻结前创建，旧journal/snapshot不追补。22文件组合236pass/123.57秒；28源/测静态检查绿。
- [x] (2026-10-21 08:38 +08:00) RuntimeState直接影响的Runtime/limits/config/merged regeneration四文件额外窄组90 passed/19.75秒；全部31件重新冻结交root。

## Plan of Work

先把原case_update payload构造抽为共享纯函数，应用写路径和验证器共用，不复制字段/来源规则。在原mutation_request effect callback、同owner事务中核实际before，保存实际repo.update输入和canonical digest，执行原更新取得after与精确receipt，再写受保护私有runtime_step。证据保存失败须整个case effect/mutation/operation一起回滚；外层mutation重放只回原receipt，不能事后新增缺失before。

新证据schema为agent-case-effect-v1，主体包括正规参数、before、update_input、after、receipt、operation fingerprint，metadata绑定run/epoch/seq/request、源/事实/已选case集合。body-free run usage按epoch登记所需case/seq，另保存独立case_effect_protocols协议声明，区分新运行证据丢失与真正旧运行；同时删effect和seq marker仍因独立声明拒绝降级。记录体积用明确UTF8上限保护，不向事件/公开信封投影。

抽正规intent装载器：completed入口要求真实同epochcompleted工具；独立pending入口要求真实started、output/finished_at为空、usage为空、无error。二者均核原model/RequestLedger、规范工具参数与指纹、精确mutation fingerprint/receipt和当前授权原话。旧无versioned证据仍用原_attest严格条件，不把started伪装成completed。新pending入口只有完整versioned实际链才返回当前精确receipt给版本reconcile，不写Journal；真正恢复工具调用按原流程确认。

链从受保护initial alias revision起，按标记中严格递增seq加载目标Case写。每笔expected=前revision、receipt=+1、before/after完整衔接；用共享payload重算精确update_input与core_operations digest、同事务时间和实际after投影；逐笔核来源，最后after必须等于当前行与依赖。缺环、重复、外部插写、撤销、未知schema、损坏hash/metadata或非已选scope均拒绝，不补Journal或证据。

## Validation and Acceptance

原`test_case_status_write_chain_pending_pg.py`两条真反例必须绿，且不加入xfail；追加3次同Case改稿、不同Case交错、工具同一响应内有序多写、崩溃重放无before补造。新run丢任一effect/marker项、错seq/epoch/owner/subject、正规模型/账本/参数/receipt/mutation/op digest任一不符、before/after/源/字段refs篡改、外部修订或撤销、体积超限、记录写失败原子回滚应拒绝/回滚。旧run无新证据时单次原路径绿、多写仍明确拒绝，不能借删除新证据触发降级。

验证runtime_step新证据source_ids/fact_ids/case_ids/run闭包：来源/区间撤销清正文，30d inactive清理清正文，公开已提交assistant/core4规则保持。原pending恢复25反例、工具效果矩阵、原自写修订、历史索引/全部Finalizer组合继续绿。原R08/冻结场景内容不改。

    python -m pytest tests/v4/agent/test_case_status_write_chain_pending_pg.py \
      tests/v4/agent/test_case_effect_chain_pg.py \
      tests/v4/agent/test_case_effect_privacy_pg.py \
      tests/v4/agent/test_pending_case_effects_pg.py \
      tests/v4/agent/test_tool_effect_recovery_matrix_pg.py \
      tests/v4/agent/test_loop_cycle_own_revisions_pg.py -q --tb=short

命令在root批准空槽后执行；期间只回环隔离PG/ScriptedPort，清凭据/关追踪，显式业务时区，不开整库或真实调用。

## Surprises & Discoveries

旧_attest把operation.created_at与当前row.updated_at核等，只适合最后一笔；循环调用它不是历史链验证。早期完整put input不可从最终row重建，因此需要在真实effect当时原子记录。单次旧兼容与新链证据必须有明确模式标记，不能靠“找不到文件就旧路径”掩盖新证据丢失。

08点固定快照9a6f882的原工具交互用例直接调用真实工具，只有started工具步骤、mutation/operation，没有Runtime initial/model。reconcile_versions原来即使零依赖仍强索pending证明，令该幂等重放回归。新增受信direct组件分类仅在state_version为空、无agent_runtime metadata、所有epoch无model Journal且无initial/model-request快照（deleted也算）时返回空pending回执，不采纳版本、不补Journal、不授final引用。原用例和五个“真实Runtime仅剩一项痕迹”反例6 passed/3.50秒；原断言不改，原固定快照失败不抹去。

现有隐私closure按来源ID传播，所以同一旧before来源撤回任意片段都会清整条私有effect，包括不相交的尾句。此处是保守清除，不宣称字段/片段精确保留。完全不同来源与其他owner保持不受影响；只有schema/stage均匹配的新Case证据runtime_step加入closure，DERIVED_KINDS和其他runtime_step行为不扩大。

root另要求复现第二效果已存而步骤未确认的崩溃窗：同回复第二调用仍用model原rev1，args.expected_revision已是2，旧_attest故意不接受；分回复恢复虽能过snapshot，重放第一张旧receipt时loop_codec会拒当前rev3。首红两条保留2 fail/2.34秒。只对带原子versioned证明的Case引入完整pending链验证；旧receipt登记必须是真实当前epoch completed输出，完整链可允许尾started但绝不改其状态。原snapshot、model/tool输出和effect字节在恢复前后不变，实际revision/mutation/operation不重复。

独立审计指出两处原227项目标未覆盖的事实。其一，Case canonical事实血缘还有used_fact_ids和source_fact_id；真实direct版本为空时，撤销这两类事实原先会留下effect旧正文，已真实PG首红并精确补齐，未做泛递归采集。其二，同时丢effect、marker、protocol的单写能落回旧_attest并发布，原“独立协议”实际仍随同一效果写入，不能代替运行开始时的版本见证。新增usage.agent_runtime.case_effect_capabilities，带真实owner/run/subject/thread/epoch/协议及规范hash，在RuntimeState.pin最先调用：只有零state_version、无当前epoch任何Journal和initial/model snapshot（含deleted）才创建。坏值拒绝，已有工作时缺失值不补；旧运行恢复不被强行升级。

直接Loop/工具组件没有RuntimeState.pin时仍属旧组件兼容边界，新proof也不能冒称具备独立开始见证。本片防三项丢失的强声明限真实安装Runtime的fresh epoch；旧运行或直接组件全部局部证据丢失时无法据此反推出新协议。合法隐私路径在原owner事务中将run置stale/revoked并清租约，30d清理仅inactive且保留usage，两者没有主动删除这两个marker的路径，但不能用此解释替代已复现的相关丢失fault。

## Decision Log

root批准新私有versioned证据与完整链，要求无新依赖/迁移、不改冻结Envelope/L3/旧snapshot；旧run继续严格兼容。所有新effect在原业务事务内存证据，失败回滚；source/区间撤销与30d清理属于完成条件。root另明确批准严格零依赖direct组件分类；任一Runtime痕迹存在均走原正规证明，不能以versions为空直接跳过reconcile。

## Idempotence and Recovery

operation和证据ID都绑定run/epoch/seq。外层mutation_request重放直接返回原receipt，回调不再执行；不能在重放时补before。证据与marker随实际effect同事务提交，崩溃不会留下半条链。旧缺证据不会自动升级；撤销或清理后的证据不可重建。

## Outcomes & Retrospective

完整自写链、严格pending恢复、canonical事实隐私闭包和fresh Runtime独立协议见证已完成。审计补强后22文件真实PG组合236 passed/123.57秒，Runtime/limits/config/merged regeneration四文件额外90 passed/19.75秒，28源/测Ruff/格式/尺寸绿；31件重新冻结。证据为`docs/v4/evidence/P3/2026-10-21-case-effect-chain.md`及`2026-10-21-case-effect-audit-followup.md`，原227项保留为审计前候选。旧单次协议（含started单写恢复）继续兼容，旧多写缺证据仍拒绝，direct/旧epoch不宣独立开始见证。未改变08点固定快照结果或首次失败；尚未整库复验、部署或真实模型验证，待root统一审查提交和后续固定tree回归。

## Interfaces and Dependencies

无新增外部API、公开Schema、依赖或迁移。应用写接点`agent_tools_cases.mutate_case`委托原子`update_with_evidence`；最终旧e#引用委托`assert_case_effect_chain`。`pending_case_receipts`仅新协议委托`pending_chain_receipt`，旧协议仍原_attest。`loop_codec.verified_versions`仅Case旧成功receipt版本较小时委托`assert_case_receipt_replay`，其他工具和旧无链保留原拒绝。私有证据通过schema/stage定向hook进入原隐私closure；清理SQL等价提取为`clear_runtime_outputs`使函数保持60行以内。

RuntimeState.pin最小接点调用`agent_case_capability.pin_case_effect_capability`，capability只在usage.agent_runtime内；marker、最终引用与pending分别核其结构和需求，不改initial/model request snapshot内容。旧兼容fixture同时模拟旧writer及旧pin，恢复时重用新pin实现验证“不追补”，避免只替换writer而假称运行历史旧协议。

## 修订记录

2026-10-21 08:02：创建；记录版本化原子证据、正规intent共享、完整digest链、隐私和旧run兼容边界。

2026-10-21 08:20：记录已实现链、原子回滚、独立协议声明、定向隐私closure及旧direct重放的精确兼容边界；组合回归进行中。

2026-10-21 08:28：记录第二pending崩溃窗的首红与严格修复、227项最终组合、25源/测静态界限与完整证据；冻结交root。

2026-10-21 08:37：因独立审计解冻，补canonical事实血缘与fresh Runtime独立协议见证；保留首红，记录236项及旧/direct边界，待Runtime窄组。

2026-10-21 08:38：记录Runtime/limits/config/merged regeneration额外90项通过，31件重新冻结交root。
