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
- [x] (2026-10-17) 38次探针及唯一一次c2尝试已结束；T05发生HTTP403即停止，全夜142次，无重试/降级/再次调用。
- [x] (2026-10-17 23:28) 最终89项端口/契约/真实服务集成通过，模型包619/656=94.36%覆盖；v4最终339通过零跳过；旧553中1项PATH问题补齐后恢复3项均通过；v1脚本80/80与self-test48/48。
- [x] (2026-10-17) 独立复核六项边界缺陷均修复并复现通过；草稿PR3此前代码头c65f597的完整CI已绿，最终增量另取CI结果。
- [ ] 有效c2能力基线、20条原P0全文与人工标签、一致率、真实端口子集比较、stage验收未完成；夜间不补跑。

## Surprises & Discoveries

P0 报告仅保留回答前 200 字，原完整回答未保存；不能从预览伪造 20 条 P0 全文校准样本。将保留可得原样本证据，并在获准的 c2 运行中收集完整合成答复，清楚标明来源，原始 P0 全文要求交大脑决策。文档同步实际涉及八份而非用户概述五份，均为设计原文件差异，已精确同步。

探针初版合成 PNG 的 IDAT CRC 校验失败，两次400不构成视觉能力证据，已保留并计入调用总数；离线修正后每模型仅补一次（该能力合计2次）均通过。`tool_choice=none` 无工具调用但仅返回 reasoning，需区分约束接受与最终文字可用。两种 reasoning 回传变体通过，但初版记录未保存签名存在性，不能证明回传必要性；默认不回传，按实测无需回传路径使用。

旧 `.gitignore` 的无根 `models/` 同时屏蔽新源代码和测试。仅对指定两个目录的 `.py` 文件放行，权重/其他模型目录仍忽略。

真实 PG + MockTransport 集成暴露旧 LangGraph 安全边界通过 `type(exc)(safe_message)` 重建错误。新错误类型改为接受但不采用位置消息参数，保持固定安全文案，未修改旧运行时。另补等待响应头时的取消/总超时关闭、未标 tool_cycle 的 reasoning 不回传、非有限工具 JSON/未闭合工具块拒绝与 SSE 额度错误单次停止。其余 provider/model 安全元数据附到原 model_call 记录，业务预算不变。

冻结的 c2 执行快照为74f83b8，包含实际 Windows 工作字节与逐文件哈希，源码摘要见 `evidence/P1/c2-execution-source.json`。后续工作只改新端口和测试/诊断字段；已经启动的 c2 进程继续使用已载入的冻结旧适配器/旧服务与评测代码。出现供应商基础设施失败时不重试；若本次不完整，不生成可比较能力基线。

唯一c2尝试在T05返回HTTP403，原因未确认，不能断定额度或排除额度；已停止全部真实调用。60条记录中36条适用尝试（含停止项）、24条N/A，仍有8条适用项未执行；混入基础设施失败的部分分数不作为模型能力基线。离线校准选择修正为20条实际存在P0预览的ID，七类齐全；原执行导出的9条完整新c2合成回答另存，不伪装成原P0全文。

## Decision Log

- 2026-10-17 / Codex：所有待用户/大脑事项写早上汇总，夜间不等待；来自用户明确指令。
- 2026-10-17 / Codex：供应商能力默认未探测，探针失败不写 true；不读取服务器配置、不运行额外真实子集、不访问 stage/生产。夜间仅一套实时基线，可从同一运行提取子集，不拿 v1 分数作差。
- 2026-10-17 / Codex：v1 场景与 rubric 原件冻结，c2 在独立目录/显式版本选择下生效，避免旧历史报告口径漂移。
- 2026-10-17 / Codex：每处自然语言 must_include*/must_not_include 均见 `eval/c2/contract-v2-assertion-audit.md`。自然语义改为固定证据评审；F01/F02/F04/P05 涉及删除/锁屏隐私的禁提词仍按字面硬检查，因为否定提及也泄露。数据库/回执/工具/问题数/计算金标不改。需要大脑验收此 c2 范围，不与 v1 作差。
- 2026-10-17 / Codex：c2 基线使用未改的 ConfiguredModel 测 v3，避免把端口改动混入历史能力基线。夜间不另发端口实测子集，5个百分点兼容比较明确留待大脑授权。
- 2026-10-17 / Codex：新增额度集成测试起初通过 V3Target 时得到预期的评测控制信号 ProviderStopped，故将运行时验收直接驱动真实 service（仅替换 HTTP），而不是修改旧配额断言。该测试随后发现并修复异常重建兼容问题。未删除或削弱旧测试。

## Outcomes & Retrospective

夜间实现与本地验证完成，阶段验收仍未完成。端口/注册表/取消/错误分类/工具循环、契约v2基础设施与防额度重试均有替身及真实隔离PG证据；89定向与339全量通过、覆盖率94.36%。真实测量未形成有效c2基线，人工校准和供应商端口兼容比较留给大脑安排。服务器仅形成stage计划，未访问。最终增量保持草稿PR，CI结果由早间汇总绑定具体头提交。

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

证据在 `docs/v4/evidence/P1/`；探针报告 `docs/v4/model-probe-2026-10-17.md/json`；无有效c2基线，状态为 `docs/v4/eval/baseline-v3-c2.status.json`，不完整原报告在 `docs/v4/eval/c2/2026-10-17-live-v3-k3.json/md`；P0预览校准候选 `docs/v4/eval/calibration/candidates.md`，新c2全文补充 `c2-captured-candidates.md`。不提交私人正文、请求日志、密钥或数据库；仅校准候选允许完整合成回答。

## Interfaces and Dependencies

新增 `mingjing_core/models/` 的 ModelPort stream/complete、PortBackedModel.generate、ModelRegistry.resolve 和 `config/models.yaml`。使用现有 httpx/PyYAML，无 SDK 依赖；同步执行器线程与 threading.Event 取消。旧 generate 输出 output/usage/latency_seconds/model 保持兼容，provider 元数据可附加。

## 修订记录

- 2026-10-17 创建：冻结执行边界、拆分里程碑，记录全文校准来源缺失。
- 2026-10-17 23:00 更新：记录38次探针、冻结源、集成发现/修复、本地回归与PR3状态。
- 2026-10-17 23:28 更新：记录403停止与142次调用、最终89/339回归和94.36%覆盖、独立审计修复、校准来源修正与明确未验收项。
