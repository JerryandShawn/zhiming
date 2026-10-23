# B1：隔离既有候选 Python 的字节码读取

本 ExecPlan 遵循 `.agent/PLANS.md`。四个活节持续更新，时间均为北京时间（UTC+08）。固定 b9 源码、B1 No-Go 与服务器/模型/飞书禁令不变。

## Purpose / Big Picture

`-B` 只禁止写入 pyc，仍可读取时间戳/长度匹配的既有缓存。即使候选源码字节已核对，旧缓存也可能让真正执行的代码不同。本片给两个既有候选入口显式加 `-I -B -X pycache_prefix=<绝对空设备路径>`，让缓存查找落入不能成为目录的空设备路径；保留候选解释器的词法路径、原源码/账本/身份护栏与错误脱敏。

## Context and Orientation

工作树 `C:/Users/Administrator/Documents/Codex/zhiming-v4`，主线 `v4/p3-agent-runtime`。初始只读 HEAD `38473401fdc124c00ed9ba117f79b4affb0c68ca`。root 明确批准只改 `tools/b1_restore_replay.py::run_candidate` 和 `tools/core_incremental_pg.py::PostgresPort.candidate` 的 argv，以及新增独占测试、计划和证据；B3 producer、consumer、应用演练与 portable 支持文件不改。

复用 `run_candidate` 的 request.validate / verify_candidate / load_document、worker_environment、safe_worker_failure；复用 `PostgresPort.candidate` 的固定 release Python 路径、受控 CommandRunner、环境清理和 JSON 回执检查。`migrate_and_grant / backfill / withdrawals` 都委托此 candidate，不另加业务逻辑。源库、牌阵、撤销与 Outbox 不变量保持。

后续 B6 文本片另交：只更新本代理拥有的 B6 资产、stage runbook B6 节和 B6 ExecPlan 的候选 Python 调用，重算 13 个资产摘要；不得与本代码片混称已演练 Linux。

## Progress

- [x] (2026-10-21 09:19 +08:00) 完整阅读两个源文件、B7 CLI/PG 调用方及旧 PG port 测试，确认最小 argv 接点。
- [x] (2026-10-21 09:19 +08:00) 向 root 报告旧 PG port 测试固定 args[1]==-c 的位置断言；申请只升级位置/完整前缀断言，原安全行为保留。
- [x] (2026-10-21 09:23 +08:00) 两个旧入口添加显式 null-prefix，源码与业务 guard 不变；root 批准旧测试仅把 -c 位置断言升级为完整受保护前缀。
- [x] (2026-10-21 09:23 +08:00) 真实合成污染 pyc 对照：旧 -I/-B 读取 poison，两个入口实际 argv 读取 source，原 source/cache 不变；不调用 PG/供应商。
- [x] (2026-10-21 09:23 +08:00) 新4项 + 原B7契约17项 + 原PG port5项 = 26 passed、4 subtests / 0.73s；Ruff/format120/尺寸/diff 检查通过，六文件冻结交 root。

## Surprises & Discoveries

旧 B7 已有 -I/-B，仍读缓存；旧 PostgresPort 只有 -c，环境的 PYTHONPYCACHEPREFIX 又会被新增 -I 忽略，所以必须在 argv 显式指定 -X，不能只改环境。旧 `tests/test_core_incremental_pg_port.py` 的 args[1]==-c 是位置断言，将因合法加强而变化；其固定解释器、候选源码、清凭据契约不得删除。

## Decision Log

2026-10-21 09:19 / Codex、root 授权：使用 `os.path.abspath(os.devnull)`，Linux 为 `/dev/null`，Windows 为已有空设备绝对规范路径；不创建/清理缓存目录，不删除原缓存，不改 b9 manifest 内容。新测试如替换解释器/worker body，仅用于把实际旧入口 argv 放进本机合成模块对照，明确不算 b9 PG 业务或正式 Linux 证据。

2026-10-21 09:23 / Codex、root 明确批准：只改 `tests/test_core_incremental_pg_port.py` 的一条 argv 位置断言，核 `-I/-B/-X/null-prefix/-c` 完整前缀。固定解释器路径、候选 source、payload、禁止 freeze、清供应商凭据等其他原断言完全保留。没有修改 portable 支持文件或 B3/App/consumer。

## Outcomes & Retrospective

完成两个既有启动向量的最小隔离，定向组合26主用例+4子断言通过，零 fail/error/skip。真实合成导入验证不是 mock import；B7 测试替换源码验证函数与 worker body，PostgresPort 测试通过注入 runner 将记录的 Linux 词法解释器映射到现有 Windows Python，均只证明 cache/argv 边界，不声称验证 b9 PG 业务或 Linux。既有原 guard 生产源码和原契约回归保留。正式 Linux、stage/生产、真实模型/飞书均未执行；null-prefix 不是签名认证。随后独立片处理旧 PG 首连路由，第三片才更新 B6。

## Plan of Work

先修改两个 argv，每处继续使用原候选 Python 路径与 -c body，加入 -I/-B/-X 的可信固定值。测试构造同长 poison/source 文件和实际时间戳有效 pyc，证实旧 -I/-B 启动读取 poison，而经实际两个入口的固定 argv 读取 source；源和缓存字节不变。测试实际输出同时核 isolated/dont_write_bytecode/pycache_prefix，不靠模拟 import 结论。

固定 b9 的完整验证仍由其原 guard 和既有回归保护。B7 新测试明确替换 source verifier 为“记录已调用”的边界替身、worker 为无数据库的合成导入；实际 request/ledger 校验不替换。PostgresPort 用注入 runner 将记录的 Linux 词法可执行路径映射到已有 Windows 解释器，保留所有 flag/body/env 后真实启动。两者均不伪造正式业务 proof，不称原生 Linux 执行。

## Concrete Steps

凭据清空、追踪关闭，单个窄槽，先新增测试再补原受影响目标：

    ../zhiming-v4-p2/.venv-core/Scripts/python.exe -m pytest tests/v4/release/test_b1_existing_candidate_bytecode.py tests/test_b1_restore_replay_contracts.py tests/test_core_incremental_pg_port.py -q
    .venv-core/Scripts/python.exe -m ruff check --select E,F,I,B,UP,SIM --line-length 120 tools/b1_restore_replay.py tools/core_incremental_pg.py tests/v4/release/test_b1_existing_candidate_bytecode.py

当前不能在 10:00 前启动整库；正式 Linux 环境尝试额度已用尽，不再探测或修环境。

## Validation and Acceptance

合成 unsafe 对照实际读 poison；两个真实入口函数构造的隔离 argv 实际读 source；无新增 pyc、原缓存和源不变。-I/-B/-X 不丢失、null-prefix 不受环境覆盖，候选解释器路径与业务 payload 不变。坏 ledger/source 仍在子进程之前拒绝；异常仍只输出安全 code。07 号 F03/X03 的撤销/幂等是必须保留的背景契约，本片不改其断言或评测分数。

## Idempotence and Recovery

本片无数据库迁移/写入；测试临时合成源使用独立 pytest 目录。失败不重试正式入口，不清理用户缓存，不修改固定候选。工具摘要改变后旧审批不可复用，root 在最终提交后重新核当前 controller / proof 工具摘要。

## Artifacts and Notes

证据路径 `docs/v4/evidence/B1/2026-10-21-existing-candidate-bytecode.md`；原始 JUnit/安全日志放 private。只含合成标记、摘要、计数和 argv flag，不含 DSN、凭据、真实正文。

## Interfaces and Dependencies

现有函数签名、CommandRunner 协议、request/receipt Schema 均不变。只用已有 Python 标准库和锁定依赖，不新增安装或 lock。B6 文本片待本片冻结后另提交。

## 修订记录

- 2026-10-21 09:19 +08:00：按 root 新授权创建，区分缓存边界测试、真实 b9 PG 与 Linux 证据。
- 2026-10-21 09:23 +08:00：完成两入口与获批旧断言加强，记录实际26+4子断言及测试替身边界；六文件冻结。
