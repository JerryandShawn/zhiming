# B1 Linux PG15 drill：可重复入口已备，真实演练仍 No-Go

更新时间：2026-10-20 23:03 北京时间（Asia/Shanghai，+08:00）。

Linux 环境阻塞见 [环境证据](2026-10-21-linux-environment-blocked.md)。本轮仅完成默认计划输出和 **22 项传输/边界测试**，没有执行 `--apply`；没有 Linux PostgreSQL 版本、镜像 digest、备份、恢复、数据库容量、权限或回滚的通过证据。不能据此满足 B1 上线继续条件，也没有生成可给 B7 使用的 restore proof。

## 固定范围

- 发布候选 `b9a89b6f84f7bebb640de080548010859aae630c`：从 Git 对象读取并校验 0001–0007 的既定 SHA256。stage 发布范围仍为 0005–0007。
- 另轨 0008 只允许指定 `0008_model_usage.sql`，LF 规范化 SHA256 必须为 `5eef5d65363baa0ab4dc8ec9763b85136f4ba249688330b9cd8448f0b39ccbcb`；仅在独立 `b1_drill_ledger` 数据库验证，不注入 B1 迁移或包。
- Docker 每次调用均使用本机固定 named pipe `npipe:////./pipe/dockerDesktopLinuxEngine`，检查 `desktop-linux` context 仍指向该 pipe，要求 Linux engine、官方 `postgres:15` 的精确 digest。
- 专属容器 `zhiming-b1-linux-20261021`；卷 `zhiming-b1-linux-20261021-pgdata`、`zhiming-b1-linux-20261021-work`；仅回环 `127.0.0.1:55481`。所有资源按 `com.zhiming.b1.drill=20261021-main` 校验归属；拒绝未知既有对象、换镜像、开放端口、绑定目录、特权容器。资源保留，不自动 stop、rm、drop 或清理。
- 仅创建四个空库：`zhiming_core_stage`、`zhiming_core_b1_restore`、`b1_drill_rollback`、`b1_drill_ledger`。只要其中任一已存在，立即停止；部分失败不自行重放或删除。

## 准备好的步骤与限制

入口准备执行：新建分离的 migration owner / writer → 固定 b9 的 schema4 合成数据 → 容器内 PG15 原生 pg_dump → 0700 目录/0600 dump 与哈希 → 恢复到独立空库 → source/restore 各迁移 0005–0007 → 账本/原消息/历史 sent 与 uncertain 收据摘要不变 → schema/表 owner 与 writer 无 DDL、账本不可写权限 → 同一 schema4 dump 恢复到另一空库对比 → 独立 0008 → 各库实际容量。

该入口是 **PG 迁移切片**。应用 backfill 二次零变化、B7 真实业务撤销/收据重放、Linux Native 控制器、跨进程 writer fence、三 unit、CHART_PYTHON 和 Hermes wrapper 切换均需另外的真实演练与证据；脚本结果明确记录这些限制。回滚切片是恢复到另一空库，不代表生产原地 rollback。容量字段只报告演练库当前大小，不冒充生产峰值估算。

环境恢复且经执行前复核后，仓库根目录命令如下；本轮没有运行第二条：

```powershell
python -m tools.b1_linux_drill
python -m tools.b1_linux_drill --apply --pull-postgres15 --run-id b1-20261021-local --p1b-migration8 C:/Users/Administrator/Documents/Codex/zhiming-v4-p1b/mingjing_core/repositories/migrations/0008_model_usage.sql --output docs/v4/evidence/B1/2026-10-21-linux-actual.json
```

默认命令不连接 Docker、不操作数据库；`--pull-postgres15` 仅在 `--apply` 下生效。真实执行会保留资源和合成 dump，无网络应用/模型/消息入口，不启动应用 writer。输出文件必须不存在；异常只输出不含命令 stdout/stderr 的错误码。所有工具子进程清除供应商密钥、DSN 和 token 环境变量并关闭追踪。

## 实际本地验证

- `pytest tests/test_b1_linux_drill_transport.py -q`：**22 passed in 0.25s**。测试使用纯命令传输替身，仅覆盖默认零副作用、远端/非 Linux 拒绝、固定本机 pipe、凭据清除、无秘密异常、镜像 digest、未知对象保留、目标/角色限定、容器内 psql 参数、有限 readiness、固定七份 SQL、0008 hash、禁止 live restore、镜像/卷/端口范围变化拒绝。
- Ruff check / format：通过。四个 Python 文件均少于 400 行；AST 检查无超过 60 行函数。
- `python -m tools.b1_linux_drill`：实际输出固定 b9 / 七份迁移 / 0008 独立 / server=0、model=0、send=0 的计划。未启动 Docker。
- 源文件 SHA256：`b1_linux_drill.py` = `8fb8b42ad5cda153b4668dd6bc0e8508d8aefecf8b8609901678e996b6257bbf`；`b1_linux_drill_sql.py` = `a1877013e82a43cece159573f8a7adb2a3ae3e37e8f50cd35c0ebe6736a9be63`；`b1_linux_drill_transport.py` = `f771aa19d03597ac7c986ecda9a0ebf3e4b1887b3e0e8a861e1d04d4288c9c76`；测试 = `4e4de6eaf32a64bea3b8809cde54765e894966da942ef3731b2284820e1200bc`。

后续继续条件：先恢复可用 Linux runtime，再取得真实 image digest / PG15 / dump / owner 与权限 / 容量 / rollback 收据；随后补上述应用与 host 切换切片。当前结论维持 **No-Go**。
