# P3 本轮事项状态更新后原引用：真实反例与候选方案

2026-10-21 07:50，北京时间。**未修复反例，不属于已绿08点候选，也没有xfail。** 本片只复现、静态设计，不改生产。

## 实际复现

独立待接线文件：`tests/v4/agent/test_case_status_own_citation_pending_pg.py`，node `test_current_selected_case_status_write_keeps_original_reference[paused|closed]`。

创建有真实用户来源的open事项；新run显式选中该case，真实Runtime初始L3把它注册为原e1。ScriptedPort先输出合法case_update（当前用户原话、真实expected_revision、status=paused或closed），第二次输出“事项状态已更新〔e1〕”。实际状态已改变、revision+1、case_update的Journal已completed、saved回执与实际行一致，但Finalizer以“历史事项引用缺少当前只读索引证明”拒绝；该alias来自初始上下文，basis不是case_index。

    python -m pytest tests/v4/agent/test_case_status_own_citation_pending_pg.py -q --tb=short

**2 failed / 2.13秒。** 失败位置：AgentRuntime.execute→_finish→AgentFinalizer.finalize→_aliases→assert_historical_case_index:36，ScopeError。测试在重新抛出原错误前额外核了真实Case状态与rev+1、唯一completed case_update步骤的精确saved receipt、2次脚本模型请求且没有assistant/result。因此不是工具未执行或版本没保存。

仅本机隔离回环PG，TZ=Asia/Tokyo、显式冻结业务时钟，清API凭据/关闭追踪，HTTP和子进程拒绝夹具。单进程已退出；无服务器、真实模型或渠道消息。新文件最初有一个未使用typing导入，删除该导入后Ruff全规则与120格式通过，产品反例断言未改、未重复宣称绿色。

## 最小修复方向（待root审查，不是已实现）

独立于case_list定义“本轮已选事项的真实写入证明”。只能用于kind=case、request.case_ids已授权、paused/closed的当前实际行；初始e#应精确对应本run当前epoch受保护agent_initial_context中的同一case/旧revision，不能用模型自报alias或别人的索引。

复用现有`agent_pending_effects.py`的受信初始快照、原始模型调用/请求账本、规范CaseUpdate参数、当前用户来源区间、效果/血缘及operation事务时间核查。当前`_attest`本身会核这些，但公开pending入口只接受最后一个started步骤，不能拿“未确认效果”名义自动放行completed或写回Journal。可新增明确的completed证明包装，先要求同run/epoch实际completed case_update、output.ok、无error、有finished_at及精确receipt，再复用内部共享核查；不改现有started恢复语义。

最终必须同时吻合：原模型调用及步骤input_fp；core_mutation_requests中agent_case_update的稳定operation、规范参数fingerprint和同一saved receipt；core_operations中该operation+:case的真实效果；当前row.id/subject/status/revision；当前用户原话和source_refs/field_source_refs；selected_case授权及无撤销。回执必须精确匹配此case和当前revision，不能拿无关saved或旧operation前缀授权所有case。

Finalizer可在非活动Case状态时分开两条受信路径：真实只读case_index，或上述真实已选case_update。不得简单把paused/closed加入所有实体通用活动状态；不得自动添加case_ids、展开未选正文或把初始L3字节改写成新状态。多次同case自写的revision链还需明确逐次证据与当前行衔接，不能用最后一条回执越过未证实的中间修订。

## 建议验收

修前本2反例应红、修后绿。追加缺model/ledger/step、错误epoch/run/subject、伪造或不同实体receipt、缺mutation或operation、参数fingerprint/状态/来源区间不符、当前row被外部再修订、撤销、私密、未选case及其他实体状态负例；确保失败不写final/assistant。原pending恢复矩阵、自写修订、历史case_index和全Finalizer目标必须组合回归。没有改冻结信封或评测分数的需要。
