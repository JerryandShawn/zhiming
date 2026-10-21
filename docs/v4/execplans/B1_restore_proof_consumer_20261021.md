# B1：拒绝误签的恢复证明

本 ExecPlan 遵循 `.agent/PLANS.md`；四个活节持续更新。所有记录使用北京时间（UTC+08）。本片不提供部署授权，也不修改固定发布包 b9a89b6。

## Purpose / Big Picture（目的与全局）

恢复证明是工具记录“在新恢复副本实际还原、迁移并重放撤销”的只含元数据的 JSON 回执。升级入口必须能区分 Linux 正式证明与 Windows 本机演练证明，并发现其内部身份、备份与重放状态不一致。增加这些检查的目的是防止错误来源或误签；无密钥 JSON 不具备抗恶意篡改的数字签名性质。

## Context and Orientation（背景与定位）

复用 `tools/core_incremental_contracts.py::validate_restore`、`Request.restore_database`、`digest`、`MIGRATIONS`；保留既有 schema、原审批摘要、备份摘要、固定包、精确恢复库、四个结果标志和零外部调用检查。调用链为 `tools/core_incremental.py::native_apply → execute → apply_locked → validate_restore`。生产端 `tools/b1_restore_proof.py::generate` 负责实际观察，消费端不得把几个布尔值替代整条观察链。

本片只拥有消费函数及其私有辅助函数、新测试、新证据和本计划。root 后续明确批准 `tools/core_incremental.py::native_apply` 的静态前置和唯一旧合成 fixture 升级。生产端五文件由另一代理维护。正式 stage 仍因 30 号复核 No-Go 禁止执行，本机 Linux 尚未通过。T/R/Q 脚本、冻结 v2.1 基线和 B1 固定包均不改。

## Progress（进度）

- [x] (2026-10-21 08:52 +08:00) 完整阅读调用链与实际 producer 字段；定位旧消费端只校验顶层四个 true，未区分 Linux / local。
- [x] (2026-10-21 08:55 +08:00) 与 producer 作者对齐实际回执 shape、重复重放 changed=false 和五个禁止权限探针（TEMP 补丁仍由作者验证）。
- [x] (2026-10-21 08:57 +08:00) 增加来源、身份、备份 / schema4 / schema7 / 重放连续状态及五个权限拒绝探针检查；首次历史 46 版 local 样本组合 59 passed + 41 subtests / 0.25s。
- [x] (2026-10-21 09:00 +08:00) 改用 producer 最终 48 版真实 Windows local 回执，只有 schema / database 被改写的反例仍拒绝；最终 49 新 consumer + 10 旧 upgrade = 59 passed、41 subtests / 0.26s，零 fail/error/skip。
- [x] (2026-10-21 09:00 +08:00) 按 root 批准只升级旧合成 fixture，原 upgrade 断言全部保留；native_apply 在 Native 构造之前预检，apply_locked 原重复检查和注入 port 的 quiesce / keep_closed 契约保留。Ruff 与尺寸检查通过，六文件冻结交 root。

## Surprises & Discoveries（意外发现）

旧 `validate_restore` 可以接受保留 `platform=win32`、`admissible=false` 和 `posix_permissions_verified=false` 的回执，只要 schema、database 与原必需字段匹配。原 `approval.restore_sha256` 仍会阻止换入未经重新批准的 JSON；本问题是受审材料误签防护不足，并非可绕过既有审批摘要。旧调用发生在 NativePort 构造和 quiesce 之后，因此 root 批准了最小静态前置，新增反例证实错误来源 / 嵌套绑定 / 审批摘要 / 缺证明四类输入均在 Native / PG 前拒绝。

JUnit 使用本机 Tokyo 偏移：最终原始 timestamp 为 `2026-10-21T10:00:17.263301+09:00`，本计划转换为北京时间 `09:00:17+08:00`；没有补造历史时段。XML tests=100 包括 59 个主用例和 41 个子断言，不记为 100 个主测试。

## Decision Log（决策记录）

2026-10-21 08:55 / Codex：只核对真实 producer 已输出字段，不增加伪造的 Linux 通过证据或远程授权协议。嵌套摘要属于一致性检查，摘要格式不等于已重算内容；真实生成器仍必须执行 Linux / PG / 文件权限观察。旧测试断言不删除、不放宽，fixture 如升级必须明确属于合成形状。

2026-10-21 09:00 / Codex、root 批准：正式 schema 名保持 v1，但 consumer ABI 收紧为要求来源和完整嵌套观察；旧只含四个 true 的材料不再可用。唯一旧 fixture `tests/test_core_incremental_support.py::restore_for` 补为明确的合成 Linux 形状，`tests/test_core_incremental_upgrade.py` 的顺序、审批摘要、异常关闭、回填、不可变原件与不发布断言原样保留。不得据此改写此前已提交证据或声称旧正式演练已通过。请求的 live 恢复库绑定方式保留，但无生产 proof / Go，生产仍不可执行。

## Outcomes & Retrospective（结果与复盘）

完成消费门和 Native 前置拒绝，定向组合最终 59 + 41 子断言通过；Ruff 全指定规则、format120、AST 尺寸与 diff 检查通过。全部新增测试是纯消费契约测试，模型/外部传输/Native/PG 物理入口受到失败陷阱或未被调用。真实 Windows local 原件用于拒绝反例，非 Linux 证据。正式 Linux 还原、真实 stage、生产回切、供应商与飞书均未验证；所有外部操作保持禁止。controller 摘要随源文件改变，旧审批不可复用，须在最终工具定稿后重新审查。

## Plan of Work（工作计划）

保持原有校验，在消费端核对严格的 Linux / admissible / POSIX 属性、operation_id、实际 dump 摘要、空目标与 writer 身份、schema4 原状态、七项迁移、真实 pg_restore 退出码、重放前后状态连续且第二次没有变化，以及 writer 权限拒绝探针。逐字段反例和“仅四个 true”拒绝案例已完成；root 批准的静态前置仅解析已读 JSON，不提前做需要 snapshot 的备份状态 / 真 PG 检查。

## Concrete Steps（具体步骤）

在 `C:/Users/Administrator/Documents/Codex/zhiming-v4`，使用已有 Core Python，凭据清空、追踪关闭，单个窄进程运行：

    ../zhiming-v4-p2/.venv-core/Scripts/python.exe -m pytest tests/v4/release/test_b1_restore_proof_consumer.py tests/test_core_incremental_upgrade.py -q --junitxml=private/b1-restore-proof-20261021/consumer-2.xml
    .venv-core/Scripts/python.exe -m ruff check --select E,F,I,B,UP,SIM --line-length 120 tools/core_incremental_contracts.py tools/core_incremental.py tests/test_core_incremental_support.py tests/v4/release/test_b1_restore_proof_consumer.py
    .venv-core/Scripts/python.exe -m ruff format --line-length 120 --check tools/core_incremental_contracts.py tools/core_incremental.py tests/test_core_incremental_support.py tests/v4/release/test_b1_restore_proof_consumer.py

实际命令先清空供应商/飞书/测试 DSN 凭据，禁用 LangSmith/LangChain/OTEL 追踪；使用共享的唯一窄测试槽，结束即释放。两次组合均为窄目标，不启动宽回归。不存在真实模型、服务器、飞书或 PG 调用。

## Validation and Acceptance（验证与验收）

输入真实 local 回执仅改 schema / database，仍应因来源属性被拒；输入 Linux 合成形状但错误 operation、dump、schema4、身份、权限、state continuity 或 second changed=true，也必须被拒。合法合成形状通过只证明消费契约，不证明正式部署。`07_评测场景集.md` 的撤销/隐私与重放不变量是背景；本片无新增模型场景，不改既有评测分数。

## Idempotence and Recovery（幂等与恢复）

纯校验无持久副作用，可重复运行。校验失败不修改证明、不重新签发、不重试真实操作；外层保持维护门关闭。没有数据库迁移，不改变 b9。

## Artifacts and Notes（产物与备注）

证据路径：`docs/v4/evidence/B1/2026-10-21-restore-proof-consumer.md`，含四个源文件 / 最终 XML / 真实 local 原件的 SHA256 和字节数。正式证据不含口令、DSN、聊天正文、备份内容。

## Interfaces and Dependencies（接口与依赖）

`validate_restore(request: Request, backup: dict[str, Any], proof: dict[str, Any]) -> None` 签名保持；新增私有 helper。无新增依赖，无锁文件或公开 API 变化。

## 修订记录

- 2026-10-21 08:55 +08:00：创建；按 root 授权限定消费门，保留 producer 与历史证据边界。
- 2026-10-21 09:00 +08:00：按新增授权接 Native 静态前置、升级唯一合成 fixture，并记录最终真实 local 反例 / 59+41 验证；六文件冻结。
