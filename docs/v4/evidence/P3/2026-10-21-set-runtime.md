# P3 本机运行时开关证据

记录时间：2026-10-21 01:39 北京时间（UTC+08）。范围仅本机合成数据。没有访问 stage/生产、真实模型或飞书，没有部署与合并操作。

## 结果

在隔离 PostgreSQL 15 的独立 `p2_test_<uuid>` schema 执行：

    python -m pytest tests/v4/agent/test_runtime_settings_pg.py tests/v4/agent/test_set_runtime_cli.py -q

实测输出：`40 passed in 6.60s`，没有跳过。19 项使用真实隔离 PG，21 项为连接前护栏/错误脱敏测试。只使用一个测试进程，供应商凭据已清除、追踪已关闭。真实 PG fixture 最终清理自己生成的 schema；没有使用真实用户数据或复制生产数据。

01:40 静态终验：显式 Ruff `E,F,I,B,UP,SIM`、format --check、git diff --check 通过；6 个 Python 文件最大 263 行，最长函数 53 行，所有行不超过 120 字符。仅存在其他在途文档的 CRLF→LF 提示，无 diff 错误。

## 已证明的行为

本机 CLI 默认 dry-run，数据库事务为只读，不插入幂等账本、不创建 owner 或 schema。显式 `--apply` 必须提供 `--expect-runtime` 与 `--request-id`。应用服务只更新 `core_owners.settings.runtime`，保留所有其他 JSON 字段和内容 revision。

真实业务提交证明新 run 按 v3→v4→v3 路由，切换前创建的 operation 仍按其固定 runtime 重放；未执行任何供应商请求。独立并发测试中，两个不同请求以同一个旧值写入，仅一个成功，另一个返回旧值冲突；相同 request_id 的两个并发调用仅一个实际写入，另一个返回持久重放收据。不同意图重用 key 被拒绝。

精确旧请求在后续回切后重放不会再切换；返回原 old_runtime/new_runtime，同时给出真实 current_runtime，changed=false。通过真实 PG CHECK 约束让幂等账本 INSERT 失败，证明此前路由 UPDATE 被同一事务回滚。未知 owner、撤销本人授权和无效持久 runtime 都不产生路由或账本写入；其他 owner 不变。

stage 参数在连接前明确拒绝。DSN 必须显式 loopback、指定 user、test/eval/p0 库名且不含 stage/live/prod；拒绝远程、多主机、Unix socket、service、options、非法端口与继承路由。localhost 固定为 loopback hostaddr，passfile 指向空设备。实际 PG 身份、版本和完整 schema 校验通过后才委托应用服务。错误输出不含测试密钥、DSN、异常详情、owner 原文或 settings 正文。

## 命令

在仓库根目录、设置本机隔离 `CORE_TEST_DSN` 后使用；没有自动读取 `.env`：

    python -m mingjing_core.tools.set_runtime --owner <id> --runtime v4 --schema <隔离schema>
    python -m mingjing_core.tools.set_runtime --owner <id> --runtime v4 --expect-runtime v3 --request-id <稳定标识> --apply --schema <隔离schema>
    python -m mingjing_core.tools.set_runtime --owner <id> --runtime v3 --expect-runtime v4 --request-id <新的稳定标识> --apply --schema <隔离schema>

收据仅含路由状态、模式、是否本次写入/重放和 owner/target 的 SHA256。无迁移；反向切换用新的稳定标识与明确旧值，不删除幂等账本。

## 修复与限制

首轮真实 PG 测试发现 SQL 模板的 JSON 路径花括号被 psycopg 作为占位符解析，已经改为 `ARRAY['runtime']`，保留原测试断言后复验通过。

当前 stage 明确未启用，需要受审的 P3 部署窗口后另行扩允许目标；B1 的授权不能复用。本片不证明真实 provider、K3 计量器、工作进程或生产切换已就绪，也不等于 P3 部署授权。旧页面真实 DOM/loopback HTTP 演练由父代理单独交证据。没有运行宽回归或更改冻结评测基线。
