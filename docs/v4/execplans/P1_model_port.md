# P1：建立可替换的模型端口与契约 v2.1 评测

本 ExecPlan 是活文档，遵循 `.agent/PLANS.md`。2026-10-18 当前执行以用户明确要求的 14、15、20 号文件及分线指令为准，取代下文标注 2026-10-17 的夜间限制。历史失败和停止记录保留。

## Purpose / Big Picture

让同一业务服务通过配置切换模型供应商，支持流式文本、完整工具调用、取消、受控重试及降级。旧 ConfiguredModel 保留为关闭开关后的回滚路径，业务预算与校验保持不变。当前建立事实硬断言、独立证据评审和全文采集的 v2.1 契约；P0 v1 与旧夜间 c2 均保留。新端口默认关闭，只有完整有效 c2.1 基线之后才运行十场景端口子集。

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
- [ ] 当前：有效 c2.1 能力基线、20 条新全文候选、人工标签、一致率、真实端口子集比较未完成；stage 未获授权，不执行。原 P0 全文要求已由 14§D 改为新有效基线采集。
- [x] (2026-10-18 / 14A、15) 严格识别 HTTP403 + permission_error + usage limit，细分 quota_5h/quota_weekly；保留原429/503边界，其他403仍权限失败。公开诊断只保留已审计的供应商提示句，不采集任意响应正文。
- [x] (2026-10-18 / 14A、15) 新增共享会员调用账本：实际HTTP发送前预留、目标/评审/探针合计滚动5小时80次、每批≤10与跨批20分钟、首次5小时额度恢复后仅续一次、weekly全局停止；Mock HTTP与账本验证99项及旧诊断16个subtest通过。
- [x] (2026-10-18 / 14A、15) core_test_main隔离PG新403额度异常、旧端口、LangGraph上下文传递实际POST计数与旧诊断回归8项及3个subtest通过；现代改动11文件Ruff/format120通过；未发送真实调用。
- [x] (2026-10-18 16:12 / 14A、C、15) runner v2.1、全文、冻结与恢复、独立校准/端口子集接线完成。81事实硬断言、9隐私字面、130语义模式；C21定向91项通过。
- [x] (2026-10-18 16:12) 主线旧Core553/553（1340.335秒）、全部v4 458/458零跳过（157.69秒）、端口/评测208项与覆盖700/737（约95%）、v1/v2.1脚本均80/80、自检48/48通过。真实调用0；等待当前头CI，再按授权合并P1。
- [x] (2026-10-18) 最新九份设计已独立提交，9/9提交字节与大脑目录一致，含个人自用与U9必做决定；证明见design-sync-2026-10-18.json。

## Surprises & Discoveries

P0 报告仅保留回答前 200 字，原完整回答未保存；不能从预览伪造 20 条 P0 全文校准样本。将保留可得原样本证据，并在获准的 c2 运行中收集完整合成答复，清楚标明来源，原始 P0 全文要求交大脑决策。文档同步实际涉及八份而非用户概述五份，均为设计原文件差异，已精确同步。

探针初版合成 PNG 的 IDAT CRC 校验失败，两次400不构成视觉能力证据，已保留并计入调用总数；离线修正后每模型仅补一次（该能力合计2次）均通过。`tool_choice=none` 无工具调用但仅返回 reasoning，需区分约束接受与最终文字可用。两种 reasoning 回传变体通过，但初版记录未保存签名存在性，不能证明回传必要性；默认不回传，按实测无需回传路径使用。

旧 `.gitignore` 的无根 `models/` 同时屏蔽新源代码和测试。仅对指定两个目录的 `.py` 文件放行，权重/其他模型目录仍忽略。

真实 PG + MockTransport 集成暴露旧 LangGraph 安全边界通过 `type(exc)(safe_message)` 重建错误。新错误类型改为接受但不采用位置消息参数，保持固定安全文案，未修改旧运行时。另补等待响应头时的取消/总超时关闭、未标 tool_cycle 的 reasoning 不回传、非有限工具 JSON/未闭合工具块拒绝与 SSE 额度错误单次停止。其余 provider/model 安全元数据附到原 model_call 记录，业务预算不变。

冻结的 c2 执行快照为74f83b8，包含实际 Windows 工作字节与逐文件哈希，源码摘要见 `evidence/P1/c2-execution-source.json`。后续工作只改新端口和测试/诊断字段；已经启动的 c2 进程继续使用已载入的冻结旧适配器/旧服务与评测代码。出现供应商基础设施失败时不重试；若本次不完整，不生成可比较能力基线。

唯一c2尝试在T05返回HTTP403，原因未确认，不能断定额度或排除额度；已停止全部真实调用。60条记录中36条适用尝试（含停止项）、24条N/A，仍有8条适用项未执行；混入基础设施失败的部分分数不作为模型能力基线。离线校准选择修正为20条实际存在P0预览的ID，七类齐全；原执行导出的9条完整新c2合成回答另存，不伪装成原P0全文。

2026-10-18 / 14A：旧诊断中抽取的公开格式为“You've reached your 5-hour usage limit.”与“You've reached your weekly (7-day) usage limit.”，只用这两句建立合成JSON夹具，不复制原诊断的其他字段。HTTP403必须同时有可解析的error.type=permission_error与usage limit提示；raw403纯文本不是额度证据。只截任意响应前240字仍会泄漏供应商回显的用户正文，因此诊断只提取已审计公共句，长度≤240。实际会员计数使用独立物理Clock；场景的FrozenClock不能倒退会员窗口。

2026-10-18 / 14D：冻结语料的七类校准中，decision 只有 D02 一个适用场景。保持原 targets 和基线分数，完整基线后可单独重采样一次 D02，标记 calibration_only、独立 sample_id，并沿用原会员账本；是否接受同场景两次实际回答满足覆盖要求，留给大脑判断。proactive 不在指定七类之内，无需额外请求。

## Decision Log

- 2026-10-17 / Codex：所有待用户/大脑事项写早上汇总，夜间不等待；来自用户明确指令。
- 2026-10-17 / Codex：供应商能力默认未探测，探针失败不写 true；不读取服务器配置、不运行额外真实子集、不访问 stage/生产。夜间仅一套实时基线，可从同一运行提取子集，不拿 v1 分数作差。
- 2026-10-17 / Codex：v1 场景与 rubric 原件冻结，c2 在独立目录/显式版本选择下生效，避免旧历史报告口径漂移。
- 2026-10-17 / Codex：每处自然语言 must_include*/must_not_include 均见 `eval/c2/contract-v2-assertion-audit.md`。自然语义改为固定证据评审；F01/F02/F04/P05 涉及删除/锁屏隐私的禁提词仍按字面硬检查，因为否定提及也泄露。数据库/回执/工具/问题数/计算金标不改。需要大脑验收此 c2 范围，不与 v1 作差。
- 2026-10-17 / Codex：c2 基线使用未改的 ConfiguredModel 测 v3，避免把端口改动混入历史能力基线。夜间不另发端口实测子集，5个百分点兼容比较明确留待大脑授权。
- 2026-10-17 / Codex：新增额度集成测试起初通过 V3Target 时得到预期的评测控制信号 ProviderStopped，故将运行时验收直接驱动真实 service（仅替换 HTTP），而不是修改旧配额断言。该测试随后发现并修复异常重建兼容问题。未删除或削弱旧测试。
- 2026-10-18 / Codex / 14A：旧test_protocols中(403,"usage limit")夹具过宽，按大脑明确的新三条件改成permission_error公开JSON提示；保留“一次HTTP、无重试”的原断言，新增缺type/错误type/原始文本403反例。普通旧适配器非quota行为、JSON结果契约与业务修复预算保持原样。
- 2026-10-18 / Codex / 15：使用持久化共享账本防止通过新run_id或角色绕过80次；HTTP边界ContextVar钩子覆盖旧POST及新端口内部重试/降级，默认未绑定时不改变生产。quota_5h首停写stop+5h预计恢复，resume_once限一次，第二次无自动恢复时间；weekly跨所有运行保持停止。原夜间quota-stop不删除，今日用独立运行作用域与同一会员共享账本。
- 2026-10-18 / Codex / 14C、15：恢复日期、星期、农历、节气/节假日、天数与热线等事实硬检查；明确同义格式和否定识别。隐私禁提词保持原字面硬检查；措辞交固定评审，旧 YAML、rubric 和历史报告不改。新目标 k3、评审 k3-256k 的口径标为 deterministic-eval-v2.1.0，不与 v1/c2 作分差。
- 2026-10-18 / Codex / 15F、G：用户已授权 A/C 与 CI 通过后将 PR3、PR4 依序合入 v4/main。先冻结 P1 完整执行源，再合 P2；E1 使用该独立快照，避免 P2 时间速赢污染旧 v3 基线。普通 main、stage、生产不在授权内。
- 2026-10-18 / Codex / 20：主线测试使用 core_test_main，E1 专用 core_test_e1；均限 loopback:55480。真实模型请求与 v4/main 合并只由主线执行。P10 §I 已收尾推送后移交，P8 §H 与后续计算交独立命理线，主线不再改其目录或 charts/skills/knowledge。

## Outcomes & Retrospective

夜间实现与本地验证完成，阶段验收仍未完成。端口/注册表/取消/错误分类/工具循环、契约v2基础设施与防额度重试均有替身及真实隔离PG证据；89定向与339全量通过、覆盖率94.36%。真实测量未形成有效c2基线，人工校准和供应商端口兼容比较留给大脑安排。服务器仅形成stage计划，未访问。最终增量保持草稿PR，CI结果由早间汇总绑定具体头提交。

2026-10-18 / 14A、15增补：严格quota分类与会员实际HTTP账本已实现，目标/评审/探针共享限制、批次间隔与一次恢复均有离线证据。此结果不等于今日E1已经运行，也不构成v2.1基线或新端口真实能力分数。没有改动或删除历史夜间停止记录，没有访问stage或生产。

14A验证命令为 pytest tests/v4/models/test_member_quota_errors.py tests/v4/models/test_member_budget.py tests/v4/models/test_protocols.py tests/v4/models/test_stream_safety.py tests/v4/models/test_schema_registry.py tests/v4/models/test_probe_guard.py tests/test_core_model_diagnostics.py::ConfiguredModelDiagnosticsTests -q：99 passed、16 subtests，9.35秒。CORE_TEST_DSN指定loopback core_test_main后，pytest tests/v4/models/test_member_quota_pg.py tests/v4/models/test_v3_port_integration.py tests/test_core_model_diagnostics.py::FailureDiagnosticPostgresTests -q：8 passed、3 subtests，2.56秒；其中完整LangGraph业务一轮的两次Mock POST恰计target=2。首次带PG批次因PG未运行而中止，不作为通过证据；恢复本机隔离PG后仅重跑上述真实PG范围。

2026-10-18 16:12：A/C离线与主线回归均通过，旧Core553、v4 458、模型/评测208、脚本两契约80/80及自检48/48已验证。最终收口额外修复共享额度预检查漏传停止类型、subset基础设施错误误报完成、C21基础设施错误自动重试；相关回归通过。当前合并条件尚待发布头CI，E1真实调用仍为0，没有有效c2.1基线、人工校准或真实分差。完整结果与命令见2026-10-18-validation.md。

## Plan of Work

端口与显式 from_base 开关已实现。当前先完成 A 额度边界与 C 事实断言的组合验证，发布测试证据并在 CI 绿后依次合并 P1、P2。E1 从提交后的 P1 源建立独立冻结快照，目标只用旧 ConfiguredModel，评审只看用户输入、完整最终回答、此刻和回执/事实证据。80 场景按最多十场景分批，批间二十分钟，实际发送共用滚动五小时八十次账本。完整有效基线后才补决策校准并运行独立新端口子集；不改今天 v2.1 的场景定义，不提前纳入 v2.2。

## Concrete Steps

在上述仓库运行，Python 使用 `.venv-core/Scripts/python.exe`，Charts 使用独立 `.venv-charts/Scripts/python.exe`。

    python -m pytest tests/v4/models -q --cov=mingjing_core.models --cov-report=term-missing
    python -m unittest discover -s tests -p 'test_core*.py'
    python -m pytest tests/v4 -q
    python tools/eval/runner.py --mode scripted
    python -m ruff check mingjing_core/models tools/probe_models.py

隔离 PG 为 localhost:55480 的可丢弃数据库，WS2 使用独立数据库。真实调用只读取 Windows 用户环境配置，不输出密钥，不修改客户端标识。

## Validation and Acceptance

分片 JSON 工具应完整组装；合成 reasoning 只按能力回传；取消关闭流并抛安全错误；503 故障两次切下个模型；会员额度错误立即停止本批且不换模型绕过。L01 用端口进行工具→结果→回答三步替身循环。Intake、FinalAnswer/DecisionOption 与 ask_user/memory_write schema 应不含本地引用。模型包覆盖率目标至少 85%。所有场景 scripted 应 100%；T01–T05/R01–R03/S01–S02 的新旧比较必须使用同一 v2.1 场景、模型与评审身份，缺失则注明未验证。

## Idempotence and Recovery

P1 不迁移业务数据库。清除 `MODELS_CONFIG` 与 `MINGJING_MODEL_PORT=v2` 即回旧适配器。只在本地隔离 schema 执行评测，运行状态与会员账本持久化至受保护工作目录。恢复必须验证源码、80 场景、rubric、模型和账本身份，已完成场景不再请求；首次 quota_5h 停止加五小时后只允许自动继续一次，第二次停止到用户回来，quota_weekly 全部停止并置顶提示。原夜间停止文件保留。独立阶段分支更新使用预期旧 SHA；PR3/4 只在用户授权的条件满足后合入 v4/main。

## Artifacts and Notes

证据在 `docs/v4/evidence/P1/`；探针报告 `docs/v4/model-probe-2026-10-17.md/json`；无有效c2基线，状态为 `docs/v4/eval/baseline-v3-c2.status.json`，不完整原报告在 `docs/v4/eval/c2/2026-10-17-live-v3-k3.json/md`；P0预览校准候选 `docs/v4/eval/calibration/candidates.md`，新c2全文补充 `c2-captured-candidates.md`。不提交私人正文、请求日志、密钥或数据库；仅校准候选允许完整合成回答。

## Interfaces and Dependencies

新增 `mingjing_core/models/` 的 ModelPort stream/complete、PortBackedModel.generate、ModelRegistry.resolve 和 `config/models.yaml`。使用现有 httpx/PyYAML，无 SDK 依赖；同步执行器线程与 threading.Event 取消。旧 generate 输出 output/usage/latency_seconds/model 保持兼容，provider 元数据可附加。

## 修订记录

- 2026-10-17 创建：冻结执行边界、拆分里程碑，记录全文校准来源缺失。
- 2026-10-17 23:00 更新：记录38次探针、冻结源、集成发现/修复、本地回归与PR3状态。
- 2026-10-17 23:28 更新：记录403停止与142次调用、最终89/339回归和94.36%覆盖、独立审计修复、校准来源修正与明确未验收项。
- 2026-10-18 更新14A、15：记录严格403分类、公共诊断白名单、HTTP实际调用共享账本、批次/恢复规则与原403夹具修订原因；待PG和runner组合检查，不发送真实调用。
- 2026-10-18 更新14A验证：99项离线与8项真实core_test_main回归通过，补充失败后重跑范围与LangGraph实际POST钩子传播证据，完整E1及合并仍由主线处理。
- 2026-10-18 按14/15/20更新当前范围：v2.1、冻结P1再合P2、限定一次自动续跑、D02校准缺口、独立数据库与前端/命理交接；旧夜间记录仅作历史证据。
