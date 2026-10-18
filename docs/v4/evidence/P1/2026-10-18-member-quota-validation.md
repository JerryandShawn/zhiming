# 14A / 15：会员额度识别与发送守卫验证

日期：2026-10-18。范围仅为 P1 的供应商错误边界与会员评测发送守卫；没有访问 stage、生产或真实模型，没有删除原夜间停止记录，没有合并分支。

HTTP403 仅在 JSON 中 `error.type=permission_error` 且提示含 `usage limit` 时识别为额度错误，分为 `quota_5h`、`quota_weekly`。其余403，包括原始文本“usage limit”，仍是普通权限错误。原429与503行为回归保持通过。

旧诊断只用于核对两句供应商公共提示：“You've reached your 5-hour usage limit.”与“You've reached your weekly (7-day) usage limit.”。合成夹具只含公开句与固定类型。诊断不存任意响应前缀；即使响应把用户正文放在公共句前后，也只保留匹配的公共句（最多240字），以及状态、固定错误类型和子类型。

会员账本在每次实际 HTTP 发送前预留一次，覆盖旧 ConfiguredModel、新流式端口的内部重试和降级；目标、评审、探针共用滚动5小时80次上限。账本跨进程锁与原子文件替换，换 run_id 不清零。若进程在预留后、发送前崩溃，预留继续占用窗口，保守阻止超发。批次最多10个场景，同一账号下一批在上一批结束20分钟后开始。quota_5h 首停的预计恢复为停止时刻加5小时，恢复只允许一次；第二次保持停止。quota_weekly 对所有运行停止并输出“线上可能受影响”。

## 已执行验证

使用独立 Core Python 环境执行：

    python -m pytest tests/v4/models/test_member_quota_errors.py tests/v4/models/test_member_budget.py tests/v4/models/test_protocols.py tests/v4/models/test_stream_safety.py tests/v4/models/test_schema_registry.py tests/v4/models/test_probe_guard.py tests/test_core_model_diagnostics.py::ConfiguredModelDiagnosticsTests -q

结果：99 passed、16 subtests，9.35秒。包含严格403正反例、供应商回显隐私、原协议/探针回归、跨角色/运行/并发80次上限、20分钟批间隔、5小时一次恢复、周额度全停、新端口内部重试的实际发送计数。原测试中仅将过宽的纯文本403额度夹具改成符合大脑新三条件的JSON夹具，原“一次请求、不重试”断言保留，新增纯文本403反例。

数据库仅使用 `postgresql://core_test@127.0.0.1:55480/core_test_main`，执行：

    python -m pytest tests/v4/models/test_member_quota_pg.py tests/v4/models/test_v3_port_integration.py tests/test_core_model_diagnostics.py::FailureDiagnosticPostgresTests -q

结果：8 passed、3 subtests，2.56秒。新403的5小时/周额度在真实业务库中只产生一次调用记账，不触发业务repair；仅公共诊断入库。完整 LangGraph 业务轮通过 TrackingModel→QuotaGuard→ContextVar→旧HTTP适配器，两个 Mock POST 对应账本 target=2，证明线程上下文传递没有漏记发送。

新旧现代改动11个 Python 文件通过 Ruff 与120列格式检查；新增7个 Python 文件全部UTF-8 LF、有完整类型标注、单文件最多221行、无函数超过60行。`git diff --check`通过。

## 未验证与边界

首次带PG测试批次因本机PG未启动而中止，不计通过；恢复隔离服务后执行上述明确范围。完整 Core/v4 组合回归、CI与c2.1 runner组合验收由主线收口。真实E1基线、20条人工校准、新端口真实子集尚未运行，本证据不能推导模型能力分数或线上状态。

调用账本记录的是本项目通过已绑定钩子发起的尝试；会员账号在其它客户端或线上独立发生的调用无法由该本地账本观察。
