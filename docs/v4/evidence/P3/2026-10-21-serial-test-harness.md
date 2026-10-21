# P3 M7 同线程串行：组件测试收尾适配证据

2026-10-21 01:19 +08:00（Asia/Shanghai）。工作树C:/Users/Administrator/Documents/Codex/zhiming-v4，分支v4/p3-agent-runtime。本片只有10个测试文件和ExecPlan/证据，无生产源码、claim、容量或串行规则修改。没有服务器、真实供应商、真实飞书、部署、合并或自主提交。

## 为什么改测试

01:00固定76c62b8全v4回归42fail/1484pass。生产M7同owner/thread只准一个running的规则正确；旧组件测试连续setup遗留旧run running，原来等同假设同线程可同时取得多个lease，已与新契约冲突。root另行处理真实chart计算长PG事务和v3 M04，不属于本片测试适配。

Harness.finish只对测试自己持有的run ID/lease调用真实repo.fail_run(status=cancelled)，核真实terminal和lease清空；没有宽扫其他run、伪造core4 final、把组件工具结果冒充成功对话。每个顺序调用点在旧组件断言结束后明确finish。ContextUsage所有计量/幂等/Journal重放先在有效lease内验证，再收尾。反馈helper的真实工具/Journals写入结束后逐轮收尾，own_revisions/self_revision的原断言无需修改即可通过。

Journal需要同时检查两run独立序号与旧日志重放，使用同owner两个真实获准subject的不同life线程；两个run依旧同时running，日志仍在有效lease内重放。没有通过终止旧run让重放断言空过。

原塔罗“两个同线程同时running再竞争”不再是合法状态。现在第二run真实留queued，claim真实抛LeaseConflict（同一线程）、无牌；首轮取得固定deck并显式结束后，第二run才claim且命中同一draw_id/recent_draw_exists，牌堆仍仅1。24小时边界、用户明示重抽、取消不绕过、固定牌面与scope/撤销断言保留。

旧note删除后旧工具的negative仍保留，但由于旧lease也已结束，额外直接调用MemoryService对同一撤销原话重导必须抛Withdrawn source range；确保真实撤销保护也被验证，不能仅靠terminal lease产生假绿。

## 验证

本机隔离PG15回环55480/core_test_main，每例独立schema。已锁定Core环境，测试进程清供应商和追踪凭据、关闭LangSmith；所有业务/事务/Journal/撤销真实，外部仅替身或禁止传输。

    python -m pytest -q tests/v4/agent/test_toolkit_pg.py tests/v4/agent/test_context_usage_pg.py tests/v4/agent/test_journal_pg.py tests/v4/agent/test_loop_cycle_case_versions_pg.py tests/v4/agent/test_loop_cycle_own_revisions_pg.py tests/v4/agent/test_tool_tarot_pg.py tests/v4/agent/test_tool_case_privacy_pg.py tests/v4/agent/test_tool_interactions_pg.py tests/v4/agent/test_tool_tarot_bounds_pg.py tests/v4/agent/test_tool_visibility_pg.py tests/v4/agent/test_computation_wiring_pg.py tests/v4/agent/test_tool_self_revision_pg.py

结果：**138 passed/40.24s，0skip、0warning**；测试进程exit0。改动10个测试文件通过Ruff E/F/I/B/UP/SIM（120列），9文件format120列，原test_tool_visibility_pg保留88列原布局仅改.finish并过format88列；全部<400行、函数≤60行。未改生产代码。

## 原42fail映射

只读原记录：任务目录private/regression-20261021-0100-76c62b8/v4.log。12目标文件覆盖41个原失败nodeid，完整文件执行均通过。表中chart类通过依赖root生产修复（other_run亦需本片明确前轮收尾），不是测试改写放过计算事务；唯一未覆盖为v3_seed M04，归root。此处仅目标复验，不代表新固定头整库回归/CI已绿。

| 原失败nodeid | 本次状态 |
| --- | --- |
| tests/v4/agent/test_computation_wiring_pg.py::test_registered_chart_gets_c_r_only_after_real_completed_step | 138目标内通过；含root生产修复依赖 |
| tests/v4/agent/test_computation_wiring_pg.py::test_model_or_stale_output_cannot_forge_c_r[text] | 138目标内通过；含root生产修复依赖 |
| tests/v4/agent/test_computation_wiring_pg.py::test_model_or_stale_output_cannot_forge_c_r[entity] | 138目标内通过；含root生产修复依赖 |
| tests/v4/agent/test_computation_wiring_pg.py::test_model_or_stale_output_cannot_forge_c_r[other_run] | 138目标内通过；含root生产修复依赖 |
| tests/v4/agent/test_computation_wiring_pg.py::test_model_or_stale_output_cannot_forge_c_r[epoch] | 138目标内通过；含root生产修复依赖 |
| tests/v4/agent/test_computation_wiring_pg.py::test_model_or_stale_output_cannot_forge_c_r[stored_content] | 138目标内通过；含root生产修复依赖 |
| tests/v4/agent/test_computation_wiring_pg.py::test_registered_memory_update_and_profile_request_use_real_mutation_receipts | 138目标内通过；含root生产修复依赖 |
| tests/v4/agent/test_computation_wiring_pg.py::test_scripted_loop_reads_registered_c_r_from_actual_tool_message | 138目标内通过；含root生产修复依赖 |
| tests/v4/agent/test_context_usage_pg.py::test_third_large_actual_alert_persists_and_replay_does_not_increment | 138目标内通过 |
| tests/v4/agent/test_context_usage_pg.py::test_unknown_actual_is_null_and_only_measured_alert_is_emitted | 138目标内通过 |
| tests/v4/agent/test_journal_pg.py::test_sequence_is_per_run_and_epoch_and_survives_replay | 138目标内通过 |
| tests/v4/agent/test_loop_cycle_case_versions_pg.py::test_case_with_two_real_feedback_events_can_freeze_context_and_run_loop | 138目标内通过 |
| tests/v4/agent/test_loop_cycle_case_versions_pg.py::test_case_lineage_registration_uses_repository_dependency_semantics | 138目标内通过 |
| tests/v4/agent/test_loop_cycle_own_revisions_pg.py::test_own_case_write_continues_and_replays_without_rewriting_frozen_bytes | 138目标内通过 |
| tests/v4/agent/test_loop_cycle_own_revisions_pg.py::test_model_step_after_selected_feedback_has_valid_journal_identity | 138目标内通过 |
| tests/v4/agent/test_loop_cycle_own_revisions_pg.py::test_external_new_revision_cannot_reuse_old_own_operation | 138目标内通过 |
| tests/v4/agent/test_loop_cycle_own_revisions_pg.py::test_missing_persisted_proof_rejects_same_epoch_replay[completed_step] | 138目标内通过 |
| tests/v4/agent/test_loop_cycle_own_revisions_pg.py::test_missing_persisted_proof_rejects_same_epoch_replay[operation] | 138目标内通过 |
| tests/v4/agent/test_loop_cycle_own_revisions_pg.py::test_missing_persisted_proof_rejects_same_epoch_replay[mutation_receipt] | 138目标内通过 |
| tests/v4/agent/test_tool_case_privacy_pg.py::test_withdrawing_source_erases_case_event_body | 138目标内通过 |
| tests/v4/agent/test_tool_case_privacy_pg.py::test_withdrawing_source_erases_projected_goal_but_preserves_case_identity | 138目标内通过 |
| tests/v4/agent/test_tool_interactions_pg.py::test_real_next_source_updates_slot_once_and_preserves_other_thread_fields[\u6211\u66f4\u5728\u610f\u7a33\u5b9a-filled] | 138目标内通过 |
| tests/v4/agent/test_tool_interactions_pg.py::test_real_next_source_updates_slot_once_and_preserves_other_thread_fields[\u4e0d\u77e5\u9053-declined] | 138目标内通过 |
| tests/v4/agent/test_tool_interactions_pg.py::test_third_same_slot_refused_then_expiry_starts_fresh | 138目标内通过 |
| tests/v4/agent/test_tool_interactions_pg.py::test_answer_application_requires_current_lease_epoch_and_live_source[cancel_requested_at=now()] | 138目标内通过 |
| tests/v4/agent/test_tool_interactions_pg.py::test_answer_application_requires_current_lease_epoch_and_live_source[retry_epoch=1] | 138目标内通过 |
| tests/v4/agent/test_tool_interactions_pg.py::test_answer_application_requires_current_lease_epoch_and_live_source[lease_token='wrong'] | 138目标内通过 |
| tests/v4/agent/test_tool_interactions_pg.py::test_reminder_requires_explicit_request_and_confirmed_time | 138目标内通过 |
| tests/v4/agent/test_tool_interactions_pg.py::test_relative_followup_needs_parser_or_uses_source_clock | 138目标内通过 |
| tests/v4/agent/test_tool_interactions_pg.py::test_proactive_optout_does_not_disable_explicit_reminders | 138目标内通过 |
| tests/v4/agent/test_tool_self_revision_pg.py::test_real_second_tool_accepts_only_proven_own_revisions | 138目标内通过 |
| tests/v4/agent/test_tool_tarot_bounds_pg.py::test_two_hundred_recent_candidates_fail_closed_but_old_history_does_not_block | 138目标内通过 |
| tests/v4/agent/test_tool_tarot_pg.py::test_twenty_four_hour_window_and_punctuation_do_not_create_new_decks | 138目标内通过 |
| tests/v4/agent/test_tool_tarot_pg.py::test_model_flag_needs_current_user_insistence_and_never_changes_old_cards[\u6211\u575a\u6301\u91cd\u65b0\u62bd\u724c-True] | 138目标内通过 |
| tests/v4/agent/test_tool_tarot_pg.py::test_model_flag_needs_current_user_insistence_and_never_changes_old_cards[\u670b\u53cb\u8bf4\u201c\u8bf7\u91cd\u65b0\u62bd\u724c\u201d-False] | 138目标内通过 |
| tests/v4/agent/test_tool_tarot_pg.py::test_model_flag_needs_current_user_insistence_and_never_changes_old_cards[\u6211\u4e0d\u60f3\u91cd\u62bd-False] | 138目标内通过 |
| tests/v4/agent/test_tool_tarot_pg.py::test_cancelled_draw_does_not_bypass_same_question_guard | 138目标内通过 |
| tests/v4/agent/test_tool_tarot_pg.py::test_two_simultaneous_runs_only_shuffle_one_deck | 138目标内通过 |
| tests/v4/agent/test_tool_visibility_pg.py::test_second_user_turn_is_not_first_meeting | 138目标内通过 |
| tests/v4/agent/test_toolkit_pg.py::test_notes_are_inferred_idempotent_and_forget_revokes_lineage | 138目标内通过 |
| tests/v4/agent/test_toolkit_pg.py::test_note_cannot_smuggle_credentials_or_ignore_optout | 138目标内通过 |
| tests/v4/test_v3_seed_corpus.py::test_v3_corpus_seed_and_first_turn_use_real_service[M04] | 未纳本片，root单独处理 |
