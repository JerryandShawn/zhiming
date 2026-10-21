# P3：事项原子版本证据、连续写入与恢复

北京时间2026-10-21 08:28冻结。主树候选，root统一提交；本片没有提交、推送、合并或部署。只用本机隔离PG 15、ScriptedPort和替身meter，真实模型/服务器/飞书请求均为0。测试清供应商环境变量、关闭追踪，TZ=Asia/Tokyo；业务来源带明确时区，未以宿主时区推算日期。

08:37复核补记：上述08:28候选因独立审计发现事实血缘和三项全失边界而解冻，未提交或发布为完成。227项和下方原字节manifest保留为历史证据；补强后的236项、独立capability和明确兼容边界见`2026-10-21-case-effect-audit-followup.md`。

## 结果与历史证据

最终21文件组合：**227 passed / 114.86秒，0 skipped、0 xfail、0 warning**。25个拥有的源码/测试文件Ruff E/F/I/B/UP/SIM、格式、每文件≤400行和每函数≤60行检查通过。它是当前工作树局部组合，不是固定提交整库回归、真实模型质量、上线或跨线集成验收。

原`test_case_status_write_chain_pending_pg.py`真实两次自写（goal rev2→paused/closed rev3）最初2 fail/3.53秒；本片已绿，保留原真实运行断言，没有加xfail。08点固定候选9a6f882原全v4结果仍是1934 pass/1 fail/1 strict-xfail/1 warning，唯一`test_tool_interactions_pg.py::test_case_updates_and_events_preserve_originals_replay_and_revision`的原断言未改；本片修复其严格零依赖direct服务分类，原用例加5个Runtime witness反例6 passed/3.50秒。

新增`test_case_effect_pending_chain_pg.py::test_second_effect_reclaims_same_epoch_without_rewriting_proofs_or_duplicate_revision[True/False]`首红2 fail/2.34秒：第二effect真实提交而Journal未确认，同回复旧pending证明拒model rev1/args rev2；分回复恢复重放旧receipt时当前实体rev3而receipt rev2被拒。随后严格versioned pending链和Case专属重放修复，2 passed/3.18秒；连同新增9个负例、原pending与矩阵45 passed/24.87秒。首红没有被删除或改成xfail。

过程中50项隐私/协议/链目标34.88秒、42项结构/交错/Runtime分类目标29.55秒、前一版20文件组合215项94.92秒均为较早候选证据，不与最终227项相加。

## 实际行为

真实case_update仍在原mutation_request回调事务中执行原repo.update。先核当前before，保存精确完整update输入，取得真实after和saved receipt，再写私有agent-case-effect-v1记录与body-free epoch/seq marker及独立协议声明。写记录、标记或体积保护失败时Case、operation、receipt和证据一起回滚；幂等mutation重放不执行回调，不补造before。

完整链按原initial alias revision起，核每笔正规model/RequestLedger调用、规范参数、当前授权原话、exact mutation/receipt、完整operation digest、同事务时间、重算after投影、相邻before/after与最终当前行。支持同Case分轮或同回复2–3次、双事项交错；另一事项的假proof不能提供依赖信用。独立case_effect_protocols使同时删effect和seq marker仍不能降级旧单写。后续模型usage累加和finalization保留两份body-free记录。

pending入口只读取真实started且output/finished_at为空、usage为空、无error的末笔。完整原子链允许pending目标的当前依赖仍处于写前版本或已采用的写后版本，其他事项必须精确当前版本；返回精确receipt给reconcile但不更新Journal。重放较旧Case receipt只接受当前epoch真实completed输出，完整新链必须证明当前revision；旧无链、其他工具和外部修订保留原拒绝。正常恢复后的原model/已完成tool/initial snapshot/effect字节不改，revision、mutation和operation不重复，只产生预期的一次后续Scripted模型步骤。

旧协议无新证据时，严格单次completed引用和单次started恢复仍绿；旧多写缺历史证据继续拒绝。direct工具组件只有零state_version、无agent_runtime metadata、全epoch无model Journal、无initial/model-request快照（含deleted）才返回空pending receipts；它不获版本采纳、Journal确认或final引用授权。新增private effect在direct路径仍保存并进入隐私闭包。任一Runtime痕迹存在即走完整正规证明，不能仅因versions为空绕过。

## 隐私与保留

新private runtime_step带全source_ids/fact_ids/case_ids、target_case_id、run/epoch/seq。source metadata包括before、after和字段引用中出现的旧来源，即使当前Case已经不再引用该旧原话。记录不设置实体顶层case_id，避免私有记账改变公开事项聚合依赖。

只有schema和stage均匹配此协议的runtime_step加入closure；公共DERIVED_KINDS、其他runtime_step和旧snapshot格式不扩大。真实PG验证message/source_span/fact/Case撤销清私有正文；同一旧来源的**不相交尾句撤销也保守清整条proof**，不宣称片段精确保留。完全不同来源和其他owner不清；无关其他协议runtime_step不因本hook被广泛删除。

原30天inactive保留清理实际删除私有effect正文，running run跳过；已发布core4结果及assistant正文按既有规则保留。没有新增迁移、依赖、公开Schema、SSE字段、L3字节或其他实体状态权限。单条私有effect输出有明确2,000,000 UTF8字节上限；本片没有600写最大规模性能验收。

## 验证范围

最终命令使用本机CORE_TEST_DSN、PYTEST_DISABLE_PLUGIN_AUTOLOAD=1、追踪关闭，下面21个文件顺序在一个pytest进程执行（团队总并行≤4）：

    python -m pytest tests/v4/agent/test_case_status_write_chain_pending_pg.py \
      tests/v4/agent/test_case_effect_chain_pg.py \
      tests/v4/agent/test_case_effect_boundaries_pg.py \
      tests/v4/agent/test_case_effect_interleaved_pg.py \
      tests/v4/agent/test_case_effect_compatibility_pg.py \
      tests/v4/agent/test_case_effect_privacy_pg.py \
      tests/v4/agent/test_case_effect_before_privacy_pg.py \
      tests/v4/agent/test_case_effect_pending_chain_pg.py \
      tests/v4/agent/test_case_direct_replay_pg.py \
      tests/v4/agent/test_pending_case_effects_pg.py \
      tests/v4/agent/test_tool_effect_recovery_matrix_pg.py \
      tests/v4/agent/test_loop_cycle_own_revisions_pg.py \
      tests/v4/agent/test_tool_interactions_pg.py \
      tests/v4/agent/test_case_status_write_proofs_pg.py \
      tests/v4/agent/test_case_status_own_citation_pending_pg.py \
      tests/v4/agent/test_case_initial_alias_tamper_pg.py \
      tests/v4/agent/test_historical_case_index_pg.py \
      tests/v4/agent/test_historical_case_index_guards_pg.py \
      tests/v4/agent/test_case_lifecycle_index_pg.py \
      tests/v4/agent/test_case_lifecycle_index_component_pg.py \
      tests/v4/agent/test_agent_finalization_pg.py -q --tb=short

这些覆盖原started恢复25项、工具效果矩阵、连续自写、原历史索引、Finalizer、缺/改initial alias、旧epoch/租约、未选Case、空/假回执、正规model/ledger/mutation/op篡改、外部同文revision、撤销、原子回滚和新协议证据降级等。未改冻结v2.1语料或评分。

## 文件与冻结范围

08:28的25个源码/测试文件按下列顺序取当时原始工作树字节SHA256，再连接`path + 空格 + sha256`（行间LF、无末尾LF）求SHA256，结果为`1ca190aadd84b59d13e6c768deec9f3bb174256459440d3b83d036c965dc8457`。这是历史候选的本机原始字节清单，不冒称补强后字节、Git归一化blob或提交SHA；提交映射由root给出。

    mingjing_core/domain/case_effects.py
    mingjing_core/repositories/privacy_case_effects.py
    mingjing_core/repositories/privacy_foundation.py
    mingjing_core/application/agent_case_changes.py
    mingjing_core/application/agent_case_completed.py
    mingjing_core/application/agent_case_direct.py
    mingjing_core/application/agent_case_effect_attestation.py
    mingjing_core/application/agent_case_effect_chain.py
    mingjing_core/application/agent_case_effect_marker.py
    mingjing_core/application/agent_case_effect_records.py
    mingjing_core/application/agent_case_write_citations.py
    mingjing_core/application/agent_case_receipt_replay.py
    mingjing_core/application/agent_pending_effects.py
    mingjing_core/application/agent_tools_cases.py
    mingjing_core/agent/loop_codec.py
    tests/v4/agent/case_effect_chain_support.py
    tests/v4/agent/test_case_effect_chain_pg.py
    tests/v4/agent/test_case_effect_compatibility_pg.py
    tests/v4/agent/test_case_effect_privacy_pg.py
    tests/v4/agent/test_case_effect_boundaries_pg.py
    tests/v4/agent/test_case_effect_before_privacy_pg.py
    tests/v4/agent/test_case_direct_replay_pg.py
    tests/v4/agent/test_case_effect_interleaved_pg.py
    tests/v4/agent/test_case_effect_pending_chain_pg.py
    tests/v4/agent/test_case_status_write_chain_pending_pg.py

另有本证据和`docs/v4/execplans/P3_case_effect_chain_20261021.md`，合计27件由root审查提交。原21个组合文件中不在上述列表的既有测试均未编辑。
