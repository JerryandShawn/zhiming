# P3 R46：同步已批准契约的 CI 测试

本 ExecPlan 遵循 .agent/PLANS.md，保留实际失败，禁止用测试掩盖产品问题。

## Purpose / Big Picture
修复2200485上CI的20失败/8错误。本轮只改.github/tests/docs；本机完整tests/v4通过、新候选R11和CI成功才更新发布绑定。没有真实模型或服务器请求。

## Progress
- [x] 读取main v46及原CI完整日志，逐个定位28项。
- [x] 新独立树zhiming-v4-r46，基线220048573110862d378015c35d99a37c0d83503e。
- [x] 更新获批准的旧测试断言与Ubuntu固定版本；diff限.github/tests/docs。
- [x] 定向首轮192通过/1新增测试断言错（193项、434.41秒）；真实receipt补测10/10、8.15秒。分轮原件保留，不合称一轮全链。
- [x] 首轮中断保留；第二完整轮21:22:22正常结束：4501通过/1环境敏感失败/56跳过，XML与退出码1保留，原28项已修复。
- [x] v47/v48批准仅测试可控时钟；完整test_schema_registry.py 20/20，0.22秒，运行代码未改。
- [x] 第三完整轮完成2026-10-26T01:32:08.363784+08:00，4502通过/56跳过，exit0、XML无失败错误、测试文件hash未变，原28逐一通过。
- [ ] 冻结新候选、R11、推Draft PR，等CI；按最终结果交接。

## Surprises & Discoveries
checkout已有fetch-depth:0，PG镜像及客户端已经15；不能把8个合成P0 backfill错误归因为浅克隆。其真实原因是夹具只固定历史tree，没有固定历史契约版本。Ubuntu固定24.04是环境稳定措施，并非已证失败根因。

首轮完整测试最后日志16:52:58，17:57核查已没有Python/PG进程，没有正常退出记录；系统未重启，中断原因/实际停止时刻未知。一次性TaskScheduler注册遭系统拒绝访问，未改权限、认证或ACL，任务没有创建。随后改用可轮询的受控exec会话运行原隔离PG及全新完整测试；旧部分结果不与新轮拼接。旧原件另有interruption_audit.json，metadata原样保留。

19:57第二完整轮仍运行。新增失败标记定位为models/test_schema_registry.py的共享总截止时间用例，使用0.01秒真实预算；单独诊断18:48为1/1、0.39秒，完整失败不能被该单独通过覆盖。暂不改文件，待全轮错误栈确认后处理；仍没有新候选提交或CI。该新增问题不在原CI28项中，必须另外保留来源与处理依据。

## Decision Log
v48接受21:22完整轮和计时测试整文件补验，不要求重复完整轮；本次人类v50/v49要求完整通过即推送，已启动的第三完整轮保持运行，避免误将有失败的完整轮报告为绿色。v49执行单修订仅在DEV树，主线服务器执行授权已由本聊天明确给出；仍须新SHA CI/R11、37Go及31Go窗口，任何异常按执行单停止。目标北京时间10-26 06:45前上线，不跳检查，06:45–07:15不切换。

v46/R27准许更新已批准测试；R26仅github/tests/docs可继承220真实评测结论，不重新发模型。v29移除强制危机号码；v30要求评分理由；R25一重试后未评分null、累计接入30；v38/v39提示词1.2.3和批准字面overlay。R35要求当前轮无memory_write时native敏感提案：更正工具memory_update不等于memory_write，恢复测试须区分首次final的独立pending与原更正重复。仍严格验证原mutation、operation、来源、receipt不重复。若实测不符合这些不变量，按产品bug处理，不能放宽。

## Outcomes & Retrospective
最新2026-10-26T01:32:48.080374+08:00：第三完整tests/v4正常exit0；原28逐一通过，证据docs/v4/eval/v46_local_validation.json。仅github/tests/docs，R26沿用220已复核质量；新候选R11/CI仍须实际核验，服务器未执行。

定向证据已根读metadata/XML/log。首轮新增内部usage标志断言并非最终回执契约，改核真实proposal/receipt/来源和重放幂等后10/10。原28项在分轮中已覆盖，完整tests/v4仍在途，不能声称整体修复完成、CI绿或发布就绪。没有改运行代码、YAML gold或真实原分。

## Context and Orientation
工作树C:/Users/Administrator/Documents/Codex/zhiming-v4-r46；分支v4/p3-r46-ci-contracts-20261025。原CI40132087922 attempt2/core：20 failed,4474 passed,56 skipped,8 errors。原r39冻结不动；文档交付树release-prep独立，不能合回新候选触发重跑。

## Plan of Work / Concrete Steps
在本树更新明确失败的测试和.github/workflows/ci.yml。使用既有Core .venv-k3、Charts .venv-charts与官方tokenizer、隔离55480PG。先private安全定向脚本，再完整tests/v4；输出XML/log/metadata并根读。完整通过前不push；候选只允许github/tests/docs diff。失败不删原件，修精确问题后重跑必要范围。

## Validation and Acceptance
原28项全部通过且完整tests/v4 exit0；隐私撤销零POST、未知在途禁止重发、错误评分null、历史P0字节来源校验不弱化、恢复原mutation不重复。新R11核assessment及四原report。新CI核精确SHA、run与终态；成功才更新DEV日报首段及两单候选引用。

## Idempotence and Recovery
所有测试只可丢弃本机schema和测试库，禁止stage/live、其他PG进程、Docker和密钥。保留每轮原XML/log。不会修改旧候选、原评测成绩或重复付费请求。

## Artifacts and Notes
原CI日志已根读；本轮证据位于private/safe-narrow-*及private/r46-full-*。28项分类如下（逐项列出，0项已证产品bug；环境固定另列，不伪造归因）：

1. `FAILED tests/v4/agent/test_agent_runtime_pg.py::test_life_runtime_commits_once_and_persists_each_original_meter` — 测试过时：v38/v39 批准 system 1.2.3，旧断言仍为 1.2.1。
2. `FAILED tests/v4/agent/test_agent_runtime_prompts.py::test_prompt_hashes_versions_and_resolved_placeholders` — 测试过时：v38/v39 批准 system 1.2.3，旧断言仍为 1.2.1。
3. `FAILED tests/v4/agent/test_eval_core30.py::test_exact_selection_preserves_all_twenty_eight_original_scoring_contracts` — 测试过时：v39 批准字面 overlay/契约版本摘要变更；保留原场景文件不变断言。
4. `FAILED tests/v4/agent/test_eval_judge_journal_pg.py::test_incomplete_real_mock_response_is_unknown_and_cannot_repost` — 测试过时：R25/R38 两次无效外评应持久化未评分/null，禁止伪造业务零分与重复 POST。
5. `FAILED tests/v4/agent/test_eval_judge_journal_pg.py::test_withdrawal_after_inflight_before_native_send_blocks_payload_and_clears_state` — 测试过时：R25 native 最后发送前撤销直接拒绝 LifecycleError；仍断言零额外 POST 和正文清除。
6. `FAILED tests/v4/agent/test_eval_live_proof_pg.py::test_verified_proof_selects_same_model_for_actual_agent_meter_and_external_judge[True]` — 测试过时：v30/R25 的合法外评响应要求 reason/deductions/expected_clauses；Mock 缺字段。
7. `FAILED tests/v4/agent/test_eval_live_proof_pg.py::test_verified_proof_selects_same_model_for_actual_agent_meter_and_external_judge[False]` — 测试过时：v30/R25 的合法外评响应要求 reason/deductions/expected_clauses；Mock 缺字段。
8. `FAILED tests/v4/agent/test_eval_x01_review_pg.py::test_overlay_preserves_original_contract_and_uses_only_declared_model_responses` — 测试过时：v39 批准字面 overlay/契约版本摘要变更；保留原场景文件不变断言。
9. `FAILED tests/v4/agent/test_first_release_r11_pg.py::test_named_deferred_cases_remain_failed_without_weakening_required_sets` — 测试过时：v29/v30 首发选择29题，原81延期门不变。
10. `FAILED tests/v4/agent/test_k31_core_chain_pg.py::test_k31_actual_core_lifecycle_primary_and_external_score` — 测试过时：v30/R25 的合法外评响应要求 reason/deductions/expected_clauses；Mock 缺字段。
11. `FAILED tests/v4/agent/test_r31_ax_contracts.py::test_ax01_script_uses_three_originals_without_divination` — 测试过时：v38/v39 批准 system 1.2.3，旧断言仍为 1.2.1。
12. `FAILED tests/v4/agent/test_tool_effect_recovery_matrix_pg.py::test_effect_committed_before_ack_reclaims_same_epoch_without_second_mutation[memory_update_proposal]` — 测试过时：R35 首次 final 的独立敏感 pending 与原更正重放区分；原更正/receipt/operation 仍严格只一次。
13. `FAILED tests/v4/models/test_contract_v2.py::test_wording_negation_cases_keep_s01_phone_facts_hard` — 测试过时：v29 已移除 S01 强制危机号码；保留其他事实与否定检查。
14. `FAILED tests/v4/models/test_k31_r18_pg.py::test_twenty_call_guard_counts_old_candidate_attempts_before_any_new_post` — 测试过时：R25 原生累计上限为30，20条夹具无法触达上限；不改运行上限。
15. `FAILED tests/v4/test_eval_framework.py::test_critic_rejects_inconsistent_or_malformed_issues[output0]` — 测试过时：R25/R38 两次无效外评应持久化未评分/null，禁止伪造业务零分与重复 POST。
16. `FAILED tests/v4/test_eval_framework.py::test_critic_rejects_inconsistent_or_malformed_issues[output1]` — 测试过时：R25/R38 两次无效外评应持久化未评分/null，禁止伪造业务零分与重复 POST。
17. `FAILED tests/v4/test_eval_framework.py::test_critic_rejects_inconsistent_or_malformed_issues[output2]` — 测试过时：R25/R38 两次无效外评应持久化未评分/null，禁止伪造业务零分与重复 POST。
18. `FAILED tests/v4/test_eval_framework.py::test_critic_rejects_inconsistent_or_malformed_issues[output3]` — 测试过时：R25/R38 两次无效外评应持久化未评分/null，禁止伪造业务零分与重复 POST。
19. `FAILED tests/v4/test_eval_framework.py::test_critic_rejects_inconsistent_or_malformed_issues[output4]` — 测试过时：R25/R38 两次无效外评应持久化未评分/null，禁止伪造业务零分与重复 POST。
20. `FAILED tests/v4/test_eval_framework.py::test_critic_errors_never_turn_into_passed_cases` — 测试过时：R25/R38 两次无效外评应持久化未评分/null，禁止伪造业务零分与重复 POST。
21. `ERROR tests/v4/test_eval_comparison_contracts.py::test_backfill_preserves_original_execution_scores_calls_and_unfingerprinted_na` — 测试过时：v39 后当前契约已升版；合成 P0 归档夹具须显式固定 legacy v1，不放宽生产 FrozenSource。
22. `ERROR tests/v4/test_eval_comparison_contracts.py::test_lf_archive_cannot_impersonate_original_crlf_execution_source` — 测试过时：v39 后当前契约已升版；合成 P0 归档夹具须显式固定 legacy v1，不放宽生产 FrozenSource。
23. `ERROR tests/v4/test_eval_comparison_contracts.py::test_backfill_rejects_unproven_observations[fingerprint]` — 测试过时：v39 后当前契约已升版；合成 P0 归档夹具须显式固定 legacy v1，不放宽生产 FrozenSource。
24. `ERROR tests/v4/test_eval_comparison_contracts.py::test_backfill_rejects_unproven_observations[observed_na]` — 测试过时：v39 后当前契约已升版；合成 P0 归档夹具须显式固定 legacy v1，不放宽生产 FrozenSource。
25. `ERROR tests/v4/test_eval_comparison_contracts.py::test_backfill_rejects_unproven_observations[na_calls]` — 测试过时：v39 后当前契约已升版；合成 P0 归档夹具须显式固定 legacy v1，不放宽生产 FrozenSource。
26. `ERROR tests/v4/test_eval_comparison_contracts.py::test_backfill_rejects_unproven_observations[applicable_na]` — 测试过时：v39 后当前契约已升版；合成 P0 归档夹具须显式固定 legacy v1，不放宽生产 FrozenSource。
27. `ERROR tests/v4/test_eval_comparison_contracts.py::test_changed_execution_snapshot_is_rejected` — 测试过时：v39 后当前契约已升版；合成 P0 归档夹具须显式固定 legacy v1，不放宽生产 FrozenSource。
28. `ERROR tests/v4/test_eval_comparison_contracts.py::test_partial_business_zero_cannot_be_silently_rerun_after_source_change` — 测试过时：v39 后当前契约已升版；合成 P0 归档夹具须显式固定 legacy v1，不放宽生产 FrozenSource。

## Interfaces and Dependencies
不改公共API、数据库迁移、产品提示词、tools运行代码或依赖。固定ubuntu-24.04，保留完整Git历史和PG15。

## 修订记录
2026-10-25：v46处理记录，定位28项并记录测试更新理由；本机验证待运行。
2026-10-25 15:55 +08:00：记录定向首轮失败及补测，启动完整tests/v4，完整通过前不推新候选。
2026-10-25 17:59 +08:00：核实首轮中断并保留审计，独立任务注册被拒后未改权限，改用受控exec会话从头运行完整tests/v4。
2026-10-25 19:57 +08:00：记录受控全量75%和新增时间预算失败标记，保留单独诊断原件，不改源文件或推送。


2026-10-25 22:03 +08:00：已读v47，今晚不上线。受控完整轮于21:22:22正常结束，XML/log/metadata根核4501pass/1fail/56skip，测试期间文件hash未变；原件c61f99996c064e0e899694d4db3d22de保留。唯一失败attempts=[]而非[a]，证明10毫秒在首请求前耗尽。仅测试改用registry/transport/retry_policy局部可控time对象，Mock响应推进601秒超过600秒共享预算，保持ModelUnavailable、仅首provider实际请求及无重试断言，不改全局stdlib时钟或运行代码。整文件定向20/20、0.22秒，原件7383c96628f846f5bfee19062cd918f4已根核；Ruff/check和format120过。不将分轮拼作全量通过；接着从头完整tests/v4，完整全绿前不commit/push。新R11/CI未启动，执行单SHA未改，真实模型0、远程服务器0。

2026-10-26T01:32:48.080374+08:00：根核完整测试XML/log/metadata及28项映射，准备冻结新候选；旧中断与失败轮均保留，不拼接。
