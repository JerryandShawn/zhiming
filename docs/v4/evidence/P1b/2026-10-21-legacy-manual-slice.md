# P1b 旧入口与人工开始门第二切片（阶段未完成）

时间：2026-10-20 23:45，北京时间（Asia/Shanghai，+08:00）。真实模型请求 0，服务器访问 0，飞书发送 0。

## 当前结果

`ConfiguredModel` 的已知会员 endpoint、显式 guard 或 k3 模型（含自定义 proxy）在原 v3 请求体与解析之间加入 `quota_legacy.post_legacy`：实际 HTTP request → 原1.8MB体积检查 → 同一中央 PG permit → 原计数回调 → send → 类型化错误/usage → 释放。旧算法、v3业务预算与请求体未重写；不能把该历史请求体当作新端口U39 wire验收。原新端口 U39 思考/推理/effort 保护未削弱，完整配置切换仍需后续验证。

退役 `hermes/chat_agent.py`、`hermes/v6_agent.py` 的实际 post 经 `quota_retired.retired_post`：实际 HTTP transport 明确拒绝，即使对象加 offline 标记也不能发送；只允许真正 MockTransport，或没有 HTTP transport 且明确标记的测试 I/O 对象。旧 compare 的 ObservedClient 在自身实际 post 前同样核验，非 dry-run CLI（含 worker）直接拒绝。历史算法和冻结 `tests/legacy/production_v5` 源未删除或改动，离线回归只给无 HTTP 的 FakeClient 明确加 `_zhiming_offline_transport=True`。

`ModelHandle.adapter` 对 known Kimi Code provider / endpoint 即使漏设 membership 也会在可信构造绑定角色；critic 不会误用默认 primary。端口运行时改角色仍零 POST 拒绝。

## 人工批次入口

仓库根目录：

    python -m tools.member_start --suite E1 --batch-number 1 --scenario T01 --scenario T02 --receipt private/manual-e1-1.json

允许 E1 / E2 / PROBE（最多十个不同 scenario）。只有用户在线在真实本机 stdin TTY 输入完整 `开始 E1 第 1 批` 才继续；探针对应 `开始 探针 第 1 批`。重定向、管道和确认环境变量不能通过，CLI 没有 `--yes`、`--confirm`。它只在已配置的中央账本创建一个15分钟当前批授权，不发模型请求、不解除停止、不授权下一批。

中央字段为 `MEMBER_CENTRAL_DSN`、`MEMBER_CENTRAL_SCHEMA`、`MEMBER_ACCOUNT_ID`、`MEMBER_LEDGER_IDENTITY`。收据仅有 schema / suite / batch_number / batch_id / authorization_id / scenario_ids / expires_at / automatic_next_batch=false / model_calls=0，不含凭据或正文。输出文件必须不存在；失败不自动恢复或开始另一批。旧批阻塞与停止解除仍须另行人工处理，不能用新 CLI 绕过。

调用已授权批次时，应用使用既有接口（读取收据不等于创建新授权；PG每个POST仍校验）：

    with call_scope(CallScope(lane="probe", run_id="synthetic-run", batch_id=receipt["batch_id"], authorization_id=receipt["authorization_id"], scenario_id="T01")):
        port.complete(...)

角色由构造绑定，scope不接受模型自报角色。批结束调用 `guard.finish_batch(batch_id, authorization_id)`；20分钟间隔在中央账本继续有效。eval/probe 的收据加载及 runner 全流程 scope 接线仍待下一切片；≤20等价脚本由root准备。不能因为 CLI 已存在宣称 E1 已能运行。

## 实际检查

P2 Core解释器、本机PG15/core_test_main、回环55480，各新PG例独立fixture schema；只替代 HTTP / 终端输入，实际 quota / 业务解析 / PG不替代。清凭据、关追踪，Charts使用既有独立 `.venv-charts/Scripts/python.exe`。

目标八文件：新 legacy PG、manual CLI、retired HTTP、HTTP边界，加旧会员错误、Core模型诊断、Core四臂比较、v5算法离线回归，最终 **59 passed、19 subtests passed / 11.51s，0 skip**。保留两条旧 pytest 收集 imported `test_dsn` 返回 str 的警告，未改无关 helper。早期57通过时唯一 skip 经 -rs 确认为未显式设置 CHART_PYTHON；设置既有解释器后该实际三引擎/固定牌用例单独1 passed / 5.11s，最终整目标已零skip。没有安装依赖。

新增/修改类型化模块与新测试 Ruff E/F/I/B/UP/SIM、120列通过，六份新文件<400行、函数≤60。老 Hermes/compare/adapter文件只改必要调用行，不整体格式化既有长文件。

另一次失败来自旧 `legacy_other_403` 夹具未固定 model，继承宿主 KIMI_MODEL=k3 后正确触发新会员闸门；该例原保护非会员旧403诊断与正文隐私。因此仅显式指定 `model="synthetic-nonmember"`，保留全部原错误类型/HTTP原因/隐私断言，并新增 k3自定义proxy不能绕过中央的反例。失败轮不计绿。

没有新迁移，没有部署/合并。剩余为 eval/probe授权scope、等价脚本、整阶段回归/CI、真实供应商、实际256k切换与中央账本部署。
