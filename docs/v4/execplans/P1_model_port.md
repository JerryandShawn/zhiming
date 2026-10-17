# P1：建立可替换的模型端口与契约 v2 评测

本 ExecPlan 是活文档，遵循 `.agent/PLANS.md`。夜间执行以用户明确授权的 `13_夜间并行指令.md` 为范围。

## Purpose / Big Picture

让同一业务服务通过配置切换模型供应商，支持流式文本、完整工具调用、取消、受控重试及降级。旧 ConfiguredModel 保留为关闭开关后的回滚路径，业务预算与校验保持不变。建立独立上下文、证据化的评测契约 v2，保留 P0 v1 原始分数；夜间仅探测 k3/k3-256k 并尝试一次 v3 c2 基线。

## Context and Orientation

仓库为 `C:/Users/Administrator/Documents/Codex/zhiming-v4`，分支 `v4/p1-model-port`，从文档同步后的 `v4/main@7fa5e10` 建立。P0 已合并为 a91481e，普通 main 不变。复用 `mingjing_core/domain/consultation.py:81` 的 generate 协议和 :115 的安全诊断思路、`application/consultation.py:80` 的 from_base 入口及 :197 的业务调用、`tools/eval/runner.py` 的批次/配额中止、真实隔离 PG 目标与 `tools/eval/targets/v3_target.py`。不改变 owner 隔离、原话事实、撤销、预算、修复轮次、业务提示词和旧 v1 评分。

设计依据为蓝图 §0/10/16、P1 全文、场景集 T01–T05/R01–R03/S01–S02/L01 与夜间指令。端口是供应商无关的消息/事件接口；能力矩阵是经过探测才能确认的功能清单；c2 是不可直接与 v1 相减的新测量口径。

## Progress

- [x] (2026-10-17) P0 合并、设计同步、四工作树隔离及必读文档核查。
- [x] (2026-10-17 22:30) 类型、安全错误、两个流式适配器、schema 扁平化；本地 60 项测试通过，早期模型包覆盖率93%。
- [x] (2026-10-17 22:30) 注册表、请求内降级、旧流水线垫片及 L01 替身三步工具循环通过。
- [x] (2026-10-17 22:30) v1 源文件不动，新增 c2 逐处审计/独立证据评审/校准导出；c2 scripted 80/80。
- [ ] 受额度保护的探针与一次 c2 基线；额度错误立即停止，其他实现继续。
- [ ] 回归、覆盖率、阶段回执、草稿 PR 与夜间汇总。

## Surprises & Discoveries

P0 报告仅保留回答前 200 字，原完整回答未保存；不能从预览伪造 20 条 P0 全文校准样本。将保留可得原样本证据，并在获准的 c2 运行中收集完整合成答复，清楚标明来源，原始 P0 全文要求交大脑决策。文档同步实际涉及八份而非用户概述五份，均为设计原文件差异，已精确同步。

探针初版合成 PNG 的 IDAT CRC 校验失败，两次400不构成视觉能力证据，已保留并计入调用总数；离线修正后每模型仅补一次（该能力合计2次）均通过。`tool_choice=none` 无工具调用但仅返回 reasoning，需区分约束接受与最终文字可用。两种 reasoning 回传变体通过，但初版记录未保存签名存在性，不能证明回传必要性；默认不回传，按实测无需回传路径使用。

旧 `.gitignore` 的无根 `models/` 同时屏蔽新源代码和测试。仅对指定两个目录的 `.py` 文件放行，权重/其他模型目录仍忽略。

## Decision Log

- 2026-10-17 / Codex：所有待用户/大脑事项写早上汇总，夜间不等待；来自用户明确指令。
- 2026-10-17 / Codex：供应商能力默认未探测，探针失败不写 true；不读取服务器配置、不运行额外真实子集、不访问 stage/生产。夜间仅一套实时基线，可从同一运行提取子集，不拿 v1 分数作差。
- 2026-10-17 / Codex：v1 场景与 rubric 原件冻结，c2 在独立目录/显式版本选择下生效，避免旧历史报告口径漂移。
- 2026-10-17 / Codex：每处自然语言 must_include*/must_not_include 均见 `eval/c2/contract-v2-assertion-audit.md`。自然语义改为固定证据评审；F01/F02/F04/P05 涉及删除/锁屏隐私的禁提词仍按字面硬检查，因为否定提及也泄露。数据库/回执/工具/问题数/计算金标不改。需要大脑验收此 c2 范围，不与 v1 作差。
- 2026-10-17 / Codex：c2 基线使用未改的 ConfiguredModel 测 v3，避免把端口改动混入历史能力基线。夜间不另发端口实测子集，5个百分点兼容比较明确留待大脑授权。

## Outcomes & Retrospective

执行中。尚未声称 P1 完成。人工校准一致率和服务器配置确认留至早上；其他未完项在回执逐条披露。

## Plan of Work

先实现端口类型、取消与脱敏错误，拆开 HTTP 传输和 SSE 解析以保持文件/函数大小限制。随后实现 OpenAI 与 Anthropic 消息编码、工具分片、schema 与注册表；先替身验证再接入 from_base 的显式开关。评测使用独立 c2 场景副本/断言审计与固定 rubric，评审仅看用户输入、最终回答、此刻和回执/事实证据。最后运行受配额保护的小探针，若可用再启动唯一一次 c2 语料；不为校准补发额外请求。

## Concrete Steps

在上述仓库运行，Python 使用 `.venv-core/Scripts/python.exe`，Charts 使用独立 `.venv-charts/Scripts/python.exe`。

    python -m pytest tests/v4/models -q --cov=mingjing_core.models --cov-report=term-missing
    python -m unittest discover -s tests -p 'test_core*.py'
    python -m pytest tests/v4 -q
    python tools/eval/runner.py --mode scripted
    python -m ruff check mingjing_core/models tools/probe_models.py

隔离 PG 为 localhost:55480 的可丢弃数据库，WS2 使用独立数据库。真实调用只读取 Windows 用户环境配置，不输出密钥，不修改客户端标识。

## Validation and Acceptance

分片 JSON 工具应完整组装；合成 reasoning 只按能力回传；取消关闭流并抛安全错误；503 故障两次切下个模型；会员额度错误一次即全局中止夜间实测且不访问兄弟模型。L01 用端口进行工具→结果→回答三步替身循环。Intake、FinalAnswer/DecisionOption 与 ask_user/memory_write schema 应不含本地引用。模型包覆盖率目标至少 85%。所有场景 scripted 应 100%；T01–T05/R01–R03/S01–S02 的真实结果仅取同一 c2 运行，缺失则注明未验证。

## Idempotence and Recovery

不迁移数据库。关闭 `MODELS_CONFIG`/`MINGJING_MODEL_PORT=v2` 即回旧适配器。只在本地隔离 schema 执行评测，运行的状态文件与全局配额停止标志持久化至受保护工作目录；恢复只能读缓存，遇会员额度错误不重试。远端仅草稿 PR，预期旧 SHA 检查后更新独立分支，不合并。

## Artifacts and Notes

证据在 `docs/v4/evidence/P1/`；探针报告 `docs/v4/model-probe-2026-10-18.md/json`（实际执行日期写报告）；c2 基线 `docs/v4/eval/baseline-v3-c2.json`；校准候选 `docs/v4/eval/calibration/candidates.md`。不提交私人正文、请求日志、密钥或数据库；仅校准候选允许完整合成回答。

## Interfaces and Dependencies

新增 `mingjing_core/models/` 的 ModelPort stream/complete、PortBackedModel.generate、ModelRegistry.resolve 和 `config/models.yaml`。使用现有 httpx/PyYAML，无 SDK 依赖；同步执行器线程与 threading.Event 取消。旧 generate 输出 output/usage/latency_seconds/model 保持兼容，provider 元数据可附加。

## 修订记录

- 2026-10-17 创建：冻结执行边界、拆分里程碑，记录全文校准来源缺失。
