# P3：用真实自写证据保留已选事项状态引用

本ExecPlan遵循`.agent/PLANS.md`。北京时间2026-10-21早间建立。未修复反例已交root，本片不赶08点固定头；08点全局四个测试槽占满时只写代码/静态，不开pytest。无服务器、真实模型、飞书、迁移或合并；root统一提交。

## Purpose / Big Picture

用户已选事项并说暂停/关闭时，真实case_update已保存，原初始e#仍指向同一事项，最终提交却要求只读case_list证明而拒绝。此片用独立的“本轮已选事项真实写入”证据保留原引用，不借索引授权，不把paused/closed直接加入全部实体通用状态。原L3已发字节、原alias身份、公开core4和事件Schema都不改。

## Context and Orientation

复用`application/agent_pending_effects.py`的受保护初始快照、原模型/RequestLedger、规范化参数与工具input_fp、当前用户来源、实际效果/血缘和operation事务时间核查；复用`agent_commit_versions.py:persisted_receipts/reconcile_versions`的精确写回执与依赖规则；在`application/agent_finalization.py:_aliases`按原owner/subject/lease/epoch/revocation核查后做最小委托。现有pending_case_receipts只接最后一个started工具、空output/finished_at/usage，不得为completed引用证明放松这个恢复入口。

CaseChanges的合法状态为open/paused/closed；此处只处理已选Case变成paused/closed后原初始e#引用。done/archived和case_list已由另片覆盖只读索引；其他实体状态、未选case的正文/修改权限、L3进行中筛选、运行中无痕/撤销规则均不改变。28主线储备a/c和33一§1对应P3恢复/事项收尾，原07号R08场景与分数不改。

## Progress

- [x] (2026-10-21 07:50 +08:00) 真实隔离PG复现paused/closed两条完整单轮Runtime反例：实际saved/rev+1/唯一completed case_update已核，Finalizer ScopeError，2fail/2.13秒，无assistant/result。
- [x] (2026-10-21 07:52 +08:00) root确认先严格单次：初始alias revision=call.expected_revision、当前row=+1；多写链保留独立真实反例，不赶08。
- [x] (2026-10-21 07:54 +08:00) 新独立helper与明确completed包装实现；原started入口未改，原两反例真实2pass/2.16秒。
- [x] (2026-10-21 07:56 +08:00) 单次proof/原started恢复/matrix/ownrevisions75项通过39.81秒；另两条改写initial alias并重签hash负例通过。
- [x] (2026-10-21 07:57 +08:00) 多写链另真实2fail/3.53秒组中核两次写已完成，无xfail；源码7件及本计划/最终回执共9件冻结交root，不把红文件纳已绿头。
- [ ] 固定提交全量及case索引/Finalizer组合由root后续合法窗口核；08点四槽期间不再开pytest。

## Plan of Work

新增`application/agent_case_write_citations.py`，只接真实leased current run、case、paused/closed且id已在持久request.case_ids的情况。从同epoch受保护agent_initial_context读原alias，逐字段精确匹配kind/id/旧revision；普通alias字典或case_index元数据不能越过。

查同run/epoch实际completed case_update，要求ToolResult.ok、无error、有finished_at、精确saved case/currentrevision receipt。新增明确completed证明包装，复用原pending_effects内部共享证明：受信初始快照与原模型RequestLedger、正规化CaseUpdate、步骤指纹、core_mutation_requests参数fingerprint和同一receipt、精确稳定operation+:case、当前行/事务时间、当前用户来源区间和血缘。不补写Journal，不修改旧pending恢复语义。Finalizer只有真实写证明或真实索引证明两条路径，不能仅凭状态放行。

root已确认首片严格单次：初始alias revision=该call.expected_revision，current=+1。现有_attest要求当前row.revision=call.expected_revision+1，直接复用只能核最后一笔；本片不拿最后一张receipt偷渡未证实的中间版本。多写链真实2条反例保留在独立pending文件且不设xfail。后续完整链需按初始revision→每笔真实completed正规intent/receipt/mutation/operation连续衔接→当前row，缺一环或外部修订都拒绝，另行实现共享证明。

## Validation and Acceptance

原反例文件`tests/v4/agent/test_case_status_own_citation_pending_pg.py`的两条paused/closed必须由真实红变绿，不能加入xfail。模型先真实case_update再引用原e#，最终保存一次core4与assistant，receipt/current状态/版本正确；没有case_list工具或未选授权扩展。

追加缺原model/RequestLedger/step、错误run/epoch/subject、fake或其他实体receipt、缺mutation/operation、参数fingerprint/状态/来源范围不符、当前row被外部修订、撤销、私密/未选case及其他实体状态反例，拒绝无result/assistant。按root裁定显式测试连续自写链，不因单例绿宣称普遍闭环。原07号R08与冻结场景不修改。

    python -m pytest tests/v4/agent/test_case_status_own_citation_pending_pg.py \
      tests/v4/agent/test_pending_case_effects_pg.py \
      tests/v4/agent/test_tool_effect_recovery_matrix_pg.py \
      tests/v4/agent/test_loop_cycle_own_revisions_pg.py \
      tests/v4/agent/test_case_index_lineage_pg.py \
      tests/v4/agent/test_agent_finalization_pg.py -q --tb=short

## Surprises & Discoveries

原alias来自L3而非索引，case_update已完成也不会给它case_index basis，这是正确的权限分离，不能以伪造basis修复。extend_aliases按kind/id复用旧e#，所以当前版本变化必须有独立真实写入证明，不能改写已发初始上下文或把模型自报revision当权威。

## Decision Log

2026-10-21早间，root批准新独立helper、当前真实选中case、初始alias身份和正规completed case_update的完整证明；确认先严格单次，多写链另做，原started恢复入口不变，不赶08点。

## Idempotence and Recovery

证明是只读，放在原Finalizer owner事务内；没有新副作用、迁移或回填。原Journal/mutation稳定operation继续去重；started恢复与completed引用各守明确状态。撤销/外部修订必须拒绝，不能恢复旧正文。回退新增委托和helper即可恢复旧拒绝行为。

## Outcomes & Retrospective

严格单次的两条原失败已真实转绿，75项窄组合及另外2条重签初始alias负例通过。原始2fail/2.13秒与最终单次结果共同记录在`docs/v4/evidence/P3/2026-10-21-case-own-status-citation.md`。多写链仍有2条真实失败，不设xfail、不宣称一般闭环；全库/部署/真实模型未验证。

## 修订记录

2026-10-21 07:52：创建；列明完整证据链、started恢复不可放松与连续写边界待定。

2026-10-21 07:57：记录root单次裁定、证明包装、75项回归与2条重签alias负例、真实多写链缺口，冻结交root。
