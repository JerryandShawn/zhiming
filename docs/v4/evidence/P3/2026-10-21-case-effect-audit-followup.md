# P3事项链：独立审计补强

北京时间2026-10-21 08:37。08:28候选未被提交或发布；独立审计发现两项遗漏后解冻。原227项和旧manifest保留在`2026-10-21-case-effect-chain.md`，本证据不把它们改写为通过新反例。

## 真实反例与修复

`test_case_effect_before_privacy_pg.py::test_linked_fact_revocation_clears_new_private_case_proof`改成三种canonical血缘对照。真实PG创建事实F和带F的Case，实际工具更新、取消组件run，effect记录的versions={}，排除了“本轮version已含F，原run失效顺带清掉”的旁路解释。fact_ids对照清除成功，used_fact_ids和source_fact_id撤销后effect仍active且有旧正文，首红**2 failed/1 passed，2.68秒**。修复linked_metadata只显式采集before/after里的fact_ids、used_fact_ids、source_fact_id，复用既有canonical语义，不做泛递归；隐私组**12 passed/6.50秒**。

`test_case_effect_protocol_loss_pending_pg.py::test_new_single_write_cannot_downgrade_when_effect_marker_and_protocol_are_all_lost`从真实Runtime单次关闭Case、完成model/tool后，在final之前同时删除effect runtime_step、usage.case_effect_evidence和usage.case_effect_protocols。原代码最终发布，首红**1 failed/1.69秒，DID NOT RAISE CoreError**。这是确定的相关丢失反例，未用“DB受信”忽略。

root授权RuntimeState.pin最小接点后，新增usage.agent_runtime.case_effect_capabilities。每epoch见证绑定schema、协议、owner/run/subject/thread/epoch和规范hash，严格区分布尔与整数。只有该epoch零state_version、无任何Journal、无initial/model-request snapshot（active或deleted均计）时，在冻结上下文与首个model前创建；坏值拒绝，已有工作时丢值不静默重建。最终selected Case自写引用和真实pending需要效果证明时，独立cap已声明新协议就不能回落旧_attest。首次尚未实际写入时无需marker，避免误拒正常第一写。

目标实测cap先于snapshot/Journal创建；epoch布尔值拒绝；坏/缺cap不补；active/deleted旧snapshot阻止补pin；三项局部证据全部丢失后0final。旧兼容fixture显式模拟旧writer和旧pin，实际效果仍由原PG repo.update产生，恢复时使用新pin实现验证不追补；原既有测试断言没有改动。

## 兼容边界

强声明限真实安装Runtime的fresh epoch。直接AgentLoop/工具组件或带旧Journal的既有epoch不新建cap，仍走旧组件兼容边界；它们的新proof不等于已有独立开始见证，不能宣称所有入口任意相关丢失均可区分新旧协议。旧单次completed引用与started恢复保留，旧多写缺历史证据拒绝。

合法隐私处理的`repositories/postgres.py:invalidate_derived`在同owner事务中清派生正文并将相关run置stale/revoked、清lease_token/lease_until；`private_retention._scrub_runs`同样撤销并清租约。`PrivacyMaintenance._old_steps`仅选inactive且超过30天的run，清私有正文但保留usage并加过期标记。这些路径不删除两个效果marker，不能解释或掩盖真实的三项相关丢失反例；新fresh Runtime仍有单独cap保护。

## 当前验证

审计补强后22文件单进程真实PG组合：**236 passed/123.57秒，0skip、0xfail、0warning**。命令是在原21文件组合中增加`test_case_effect_protocol_loss_pending_pg.py`；原三canonical测试也在同组。覆盖此前227目标、三canonical血缘和7项cap目标。没有修改冻结v2.1场景/评分。

额外Runtime/limits/config/merged regeneration四文件窄组：**90 passed/19.75秒**，不与前组相加宣称去重总数。命令为`pytest tests/v4/agent/test_agent_runtime_pg.py tests/v4/agent/test_runtime_limits_pg.py tests/v4/agent/test_runtime_config.py tests/v4/agent/test_merged_regeneration_pg.py -q --tb=short`。所有运行仅本机隔离PG、ScriptedPort和替身meter，TZ=Asia/Tokyo，供应商凭据清除、追踪关闭；无真实模型、服务器、飞书或依赖安装。

28源/测文件Ruff、格式和400行文件/60行函数界限绿。原25文件清单顺序后追加如下3个文件，按原证据的raw字节manifest算法计算，SHA256为`4f2ebabd227f2cb5cdbd4c3cb045bcdc45e9238d19fa35c3e97eb8e932f09219`：

    mingjing_core/application/agent_case_capability.py
    mingjing_core/application/agent_runtime_state.py
    tests/v4/agent/test_case_effect_protocol_loss_pending_pg.py

另含旧证据、本补强证据及ExecPlan，总计31件交root统一审查提交。cap只在私有usage.agent_runtime，不改变initial/model-request snapshot格式或正文、冻结core4/events、L3、旧实体权限；没有迁移或新依赖。本片仍未整库复验、跨线验收或上线。

08:38重新冻结；当前没有测试进程，本片文件全部释放。
