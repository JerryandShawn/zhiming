# P3 M6：长期线程 Runtime 候选本机证据

时间：2026-10-20 23:57（北京时间）。本记录为 Windows 隔离 PostgreSQL 15 的合成资料验证，真实模型请求 0、服务器访问 0、飞书发送 0。无新依赖、无迁移，不代表线上部署或真实回答质量。

## 已验证行为

候选 `application/agent_runtime.py:AgentRuntime` 显式注入 ModelPort 和 TokenMeter，贯通 AgentSnapshotStore、真实 LoopCycle、每次请求的 preview/mark_sent、原计量的 actual usage、AgentFinalizer 与持久事件。模型请求原件私存为附 source/fact 谱系的 agent_model_request，恢复时使用原请求和原计量，不因自调系数改变旧指纹。主/评审 cache epoch 隔离，所有原始推理保留在私有 journal 中。

独立 critic 只收用户问题、资料摘要、真实收据和初稿；严格核对问题类型、严重度和引文。revise 只再生成一次，禁止工具，保留同轮完整推理协议。评审通过或修订必须由 PG 中真正完成的 critic/revision 行证明；伪造 receipt 不发布。评审输出错误或模型不可用时跳过评审，正文仍经提交闸门。

采用来源被撤回时，凭本次租约摘要和最新账本最多重建一次干净 epoch；当前用户原话已撤回时，原请求保持空且不重生。旧快照和草稿不带入新请求。危机模式对不可用、额度耗尽、20 秒无正文使用配置内固定的 12356 / 120 / 110 模板。程序危机规则有 15 正例和 15 反例，但不是完整危机分类器。

正式 P1/P2/P4/P8 提示词和增补 H 用版本、原文 SHA 与固定 manifest 加载，system 升为 1.1.0。prompt/fallback provenance 存私有 run.usage.agent_runtime，冻结 core4/events v1 Schema 无新增字段。

## 检查

Core Python 3.11、本机专用 CORE_TEST_DSN；清供应商凭据，关闭 tracing。以下目标集合：

    python -m pytest tests/v4/agent/test_agent_runtime_pg.py tests/v4/agent/test_agent_runtime_recovery_pg.py tests/v4/agent/test_agent_runtime_prompts.py tests/v4/agent/test_agent_finalization_pg.py tests/v4/agent/test_envelope_structural.py tests/v4/agent/test_context_epochs_pg.py tests/v4/agent/test_loop_cycle_pg.py tests/v4/agent/test_loop_cycle_controls.py tests/v4/agent/test_loop_cycle_own_revisions_pg.py tests/v4/agent/test_loop_cycle_case_versions_pg.py -q --tb=short

结果：**130 passed in 18.65s**。新增/修改自有 Python 通过 Ruff E,F,I,B,UP,SIM 和 format（120 列），AST 检查未发现超过 400 行文件或 60 行函数。此次并发仅一个目标测试进程。

## 尚未完成 / 未验证

候选 RuntimeRouter 还未接入 ConsultationService；父代理负责主路由与无痕生命周期。无痕入口明确拒绝；全部 legacy reader 由另一切片逐一接 helper。真实 HTTP 取消与 dispatcher 是 M7。K3 实际 tokenizer、framing、等价性与质量均未验证；脚本计量不作为它们的证据。复杂附件/塔罗输入被撤回后拒绝自动恢复请求。普通模型原件保留清理 worker 尚未完成。生产、stage、模型实测均未运行。
