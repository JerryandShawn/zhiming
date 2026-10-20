# P3：本机运行时路由管理入口

本 ExecPlan 遵循 `.agent/PLANS.md`。时间一律为北京时间（UTC+08）。

## Purpose / Big Picture

提供提示词指定的 `python -m mingjing_core.tools.set_runtime` 管理命令，只修改既有 owner 的运行时路由。默认预览；显式写入须匹配旧值并提供稳定请求标识。该命令不安装模型、不验证模型就绪、不启动工作进程，也不代表部署授权。当前只允许可核验的本机隔离 PostgreSQL 15；stage 在连接前拒绝，后续需受审的 P3 部署窗口再扩展。

## Context and Orientation

复用 `application/thread_queue.py:owner_runtime` 的 v3 默认值与合法值约束；复用 `repositories/postgres.py:transaction` 的 owner 事务锁及 `mutation_request` 的持久幂等账本。既有 `application/runtime_assembly.py:route_submit` 已将新运行固定到 owner 设置，旧 operation 保留原 runtime。不得修改这些行为，不得创建未知 owner，不得改写其他 settings、既有 run、撤销账本或 Outbox。新增 SQL 放在 `application/runtime_settings.py`，工具层只做目标检查与委托。

## Progress

- [x] (2026-10-21 01:36) 阅读路由、仓库幂等与隔离 PG fixture，确认 stage 本片不启用。
- [x] (2026-10-21 01:39) 实现本机目标验证、预览、CAS 写入与持久幂等收据。
- [x] (2026-10-21 01:39) 真实隔离 PG 验证 v3→v4→v3、新旧运行固定、并发旧值冲突、未知 owner 零写、其他设置与 revision 保留、账本失败时整体回滚。
- [x] (2026-10-21 01:39) 新目标 40 passed / 6.60s；单个窄进程，无跳过；详细证据见下文。
- [x] (2026-10-21 01:40) 显式 E,F,I,B,UP,SIM、格式与 AST 复核通过：6 个 Python 文件，最大 263 行、最长函数 53 行。已冻结待父代理提交。

## Surprises & Discoveries

提示词要求 local/stage，但当前授权未覆盖 P3 stage 切换；B1 的 b9 授权不能挪用。因此 stage 明确 Unsupported 且零连接。现有仓库无 settings CAS 服务，需要新增应用服务，不能把 SQL 放进工具层。路由开关不增加 owner 内容 revision，避免将运维路由改变误作用户事实修改；既有 run 的 runtime 不变。

首轮真实 PG 暴露 SQL 模板将 JSON 路径花括号解释为格式占位符；已经改成参数外的 `ARRAY['runtime']` 路径，并以完整目标复验。测试没有放宽原断言。另发现旧请求重放时，后续请求可能已经改变当前路由，因此收据同时返回原 old/new 与当前 `current_runtime`，不会把原意图误报为本次写入。

## Decision Log

2026-10-21 01:36：父代理确认仅本机隔离入口，不新增专项授权文件、令牌或 provider_ready 字段。apply 采用 expected_runtime 与 request_id，精确重放先读幂等账本，之后才检查当前旧值；不同意图重用请求标识拒绝。preview 用数据库只读事务；apply 使用 owner 事务锁和 owner 行锁，只更新 settings.runtime。

2026-10-21 01:39：目标验证固定 hostaddr，拒绝服务与 options 路由、继承 PGSERVICE/PGOPTIONS，并将 passfile 指向空设备以避免隐式读取真实凭据文件。实际连接必须为 PG15、loopback、指定数据库/角色/端口，当前 schema 的全部校验和必须正确。缺失 schema 只拒绝、不初始化。

## Outcomes & Retrospective

本机管理入口与独立应用服务已实现。40 项目标包含 19 项真实隔离 PG、21 项纯护栏；证明路由和幂等约束，不验证模型供应商。当前没有 stage、生产、真实供应商或飞书证据；不得将命令存在写作 P3 可上线。父代理另做旧页面真实 DOM/HTTP 演练，本片不替该演练声称结果。

## Plan of Work

新增应用服务、工具包、目标校验和独立测试。新 CLI 从指定环境变量读取 DSN；先拒绝 stage、服务配置、非 loopback、非隔离数据库，再验证真实 PG15 身份和当前 schema 校验和。错误使用固定中文与代码，不回显异常、DSN、owner 或 settings。全部测试只使用合成 owner 与隔离 schema。

## Concrete Steps

在仓库根目录、清除供应商凭据并禁用追踪后执行：

    python -m pytest tests/v4/agent/test_runtime_settings_pg.py tests/v4/agent/test_set_runtime_cli.py -q
    python -m ruff check mingjing_core/tools mingjing_core/application/runtime_settings.py tests/v4/agent/test_runtime_settings_pg.py tests/v4/agent/test_set_runtime_cli.py

预览：

    python -m mingjing_core.tools.set_runtime --owner alice --runtime v4 --schema <隔离schema>

显式本机切换及反向切换：

    python -m mingjing_core.tools.set_runtime --owner alice --runtime v4 --expect-runtime v3 --request-id local-enable-1 --apply --schema <隔离schema>
    python -m mingjing_core.tools.set_runtime --owner alice --runtime v3 --expect-runtime v4 --request-id local-disable-1 --apply --schema <隔离schema>

## Validation and Acceptance

此片支持 P3 路由灰度验收，并保护评测场景 X03 的幂等、X04 的既有运行身份及 R07 的历史连续性；不声称重跑这些场景。直接验收为真实隔离 PG 上新运行 v3/v4/v3、旧运行不漂移、重复请求零变化、并发相同旧值仅一方成功、未授权目标在连接前拒绝、异常输出不含合成密钥。

## Idempotence and Recovery

相同 request_id 与意图返回原收据；不同意图拒绝。事务失败整体回滚，旧值不符无 settings 或账本写入。回切使用新的请求标识、期望当前值和 runtime=v3；不能删除账本或覆盖并发修改。无数据库迁移。

## Artifacts and Notes

证据预定为 `docs/v4/evidence/P3/2026-10-21-set-runtime.md`。真实 PG 测试不代替 stage 路由、部署、供应商或浏览器上线验证。

## Interfaces and Dependencies

`RuntimeSettingsService(repo).preview(owner, runtime)` 与 `apply(owner, runtime, *, expected_runtime, request_id)` 返回无私人内容的路由收据。CLI 默认 DSN 环境变量 `CORE_TEST_DSN`，只连接明确 loopback 的 test/eval/p0 库，校验 PG15 及完整 schema；无新增依赖。stage 参数只返回未启用错误。

## 修订记录

- 2026-10-21 01:36 创建：限定本机、持久幂等与前置旧值，先记未验证。
- 2026-10-21 01:39 更新：记录真实 PG 40 项结果、SQL 路径修复和当前路由收据语义；静态终验待记录。
- 2026-10-21 01:40 更新：显式 Ruff、格式及文件/函数长度终验通过，冻结交父代理提交。
