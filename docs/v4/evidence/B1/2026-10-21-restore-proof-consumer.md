# B1 恢复证明消费门：纯契约验证

记录时间：2026-10-21 09:00 +08:00（北京时间）。主线 `v4/p3-agent-runtime`，测试期间已提交 HEAD `a2adc40f3a86809d4b6f3d6f64ee4ee6cb49a492`，本片四个源文件尚未由 root 提交，以下逐文件摘要界定实际候选。**本报告不是 Linux 还原或 stage Go；30 号仍 No-Go。**

## 结果与命令

使用已有 P2 Core 解释器，清空 Kimi/Moonshot/OpenAI/Anthropic/飞书凭据和 Core 测试 DSN，关闭 LangSmith/LangChain/OTEL 追踪。仅持有团队共享的一个窄测试槽，不运行 PG / Native / 网络：

    ../zhiming-v4-p2/.venv-core/Scripts/python.exe -m pytest tests/v4/release/test_b1_restore_proof_consumer.py tests/test_core_incremental_upgrade.py -q --junitxml=private/b1-restore-proof-20261021/consumer-2.xml -o cache_dir=private/b1-restore-proof-20261021/consumer-cache

结果：**59 passed、41 subtests passed，0.26s，退出 0**；49 个新 consumer 用例与 10 个原 upgrade 用例，零 fail/error/skip。JUnit `tests=100` 包含 41 个子断言，不虚计为 100 个主用例。原始 JUnit timestamp `2026-10-21T10:00:17.263301+09:00` 等同北京时间 `09:00:17+08:00`，内部套件耗时 0.232s。此前用历史 46 版四探针 local 样本的组合为 59+41 / 0.25s，保留其 `consumer-1.xml`，不覆盖历史结果。

静态检查：已有主线 Core 环境的 Ruff，`--select E,F,I,B,UP,SIM --line-length 120` 通过；四文件 `ruff format --line-length 120 --check` 通过；AST 统计单文件最大 380 行、单函数最大 60 行；`git diff --check` 通过。无安装依赖、无新迁移。

## 可观察保护

真实 Windows PG15 local 回执来自 producer 作者最终 48 项测试中的观察（本代理仅只读复制 body-free 元数据）。原件为 `private/b1-restore-proof-20261021/observed-local-receipt-48.json`，记录 `platform=win32`、`admissible=false`、`posix_permissions_verified=false`，五项权限拒绝探针已经满足。测试仅将其 `schema` 改为正式 v1、`database` 改为请求恢复库，保留其余原值，消费门仍报 `RESTORE_PROOF_ORIGIN`；不是靠旧四探针不足掩盖来源失败。

新增逐字段反例覆盖 operation、dump、摘要形状、owner/writer 身份、回环地址 / 端口 / PG15、schema4 原状态与 checksum、pg_restore 实际执行及严格整数退出码、七项迁移、重放前后 hash / changed 标志 / 连续性 / 第二次不变、所有者数量、非负计数、零外部效果以及五项权限拒绝观察。只有四个结果 true 而缺少观察链也被拒绝。所有“合法 Linux 形状”均明确为合成测试输入，不代表正式演练。

`native_apply` 在 authorize、host-config 摘要之后，NativePort 构造之前，只对 migrate/backfill 解析后的 backup+restore 做静态前置。错误来源（含上述真实 local 只改两字段）、嵌套身份错误、审批摘要错误及缺证明均由 10 个参数化用例确认零 Native/PG；真实构造/连接替身一旦触发即测试失败。`apply_locked` 保留原重复核验，注入 port 的 quiesce/keep_closed 顺序不迁移。

## ABI 与历史证据

正式 schema 名保持 `b1-isolated-restore-proof-v1`，消费所需属性严格增加；旧只有四个 true 的材料不能继续使用。唯一旧 fixture `tests/test_core_incremental_support.py::restore_for` 经 root 明确批准补为合成 Linux 形状，原 `tests/test_core_incremental_upgrade.py` 所有安全断言原样保留。这不重写此前正式 / 本机验证历史。

原有 schema、审批 `restore_sha256`、备份摘要、固定 b9 manifest、恢复库、checksum、四个结果 true 和零外部调用检查全部保留。新增 SHA 字段只验证格式与相关绑定，不假称重算了文件或提供数字签名。无密钥 JSON 仍需要受保护文件和人工审批摘要；恶意修改整份 JSON 并取得新审批不在本检查的签名保证范围内。controller 摘要随工具源改变，旧审批不得复用。

## 文件与原始证据摘要

| 文件 | 字节数 | SHA256 |
|---|---:|---|
| `tools/core_incremental.py` | 9826 | `251280389372159f8f1ddd2e1eeae7c0584a61f1178a5cd7eba00edba87892ea` |
| `tools/core_incremental_contracts.py` | 16112 | `704a548b61f6e136ed30ee69a28037f3ff12fabab2a7d378f23fc10c8b7a0c12` |
| `tests/test_core_incremental_support.py` | 2451 | `9abb5d2f6ba3b186a24350fe75207fbd588e313adb612cab4a7ad68dd345d00f` |
| `tests/v4/release/test_b1_restore_proof_consumer.py` | 14703 | `a5ee0f816c19349b56b377e81c7069fcff9bb99a292ad5ef8582676253178d16` |
| `private/b1-restore-proof-20261021/consumer-2.xml` | 10679 | `f24df72c5f084597dfd3effd03eea79e27a05ce7359c4b3f1875820053996956` |
| `private/b1-restore-proof-20261021/observed-local-receipt-48.json` | 4085 | `c34655231814091bb1e35a2f36c5dea766756244efd97d36d926821d1bf503a1` |

## 未验证 / 已知风险

真实 Linux/PG/systemd 权限、正式恢复、stage、生产回切、真实模型和飞书均未执行。producer 的真实连接/导入/权限检验及其新自校验由另一代理维护，须独立取其最终成绩；本消费组不能代替它。未来 live request 的恢复库 / role 绑定仍按 Request 生效，但没有生产 proof 和授权 Go，不能据合成正例启用生产。
