# B7 stage 恢复副本撤销 / 收据重放：本机 PG 对照

记录时间：2026-10-20 23:07:45 +08:00（北京时间）。

结论：新 stage 专用入口的 **Windows PostgreSQL 15.19 对照通过**；不是 Linux 容器演练证据，不能据此将 B1 改判为 Go。Linux 环境阻塞另见 `2026-10-21-linux-*.md`。本次没有服务器 / SSH、模型请求或飞书发送。

## 候选与隔离

- 业务包固定 `b9a89b6f84f7bebb640de080548010859aae630c`；636 个 Git 原始 blob 落入 `private/` 合成测试目录，逐项核对 SHA，发布 manifest 的 SHA-256 固定为 `49038f8c0dc6bb293ba688af91018cbe6339b319c388d290fd000a256e36b33c`。
- 外部 controller 是本次工作分支的新文件，候选的 `tools.deploy_core.apply_withdrawals`、仓储和迁移 0001–0007 均未改动；独立 Python `-I -B` 子进程从固定候选导入业务代码，核对真实导入路径。未导入 P3 新 schema 冒充候选恢复。
- 本机回环端口 55480，专属 `zhiming_core_b1_restore` 库；专属 owner / writer，无超级用户、建库、建角色、复制或 BYPASSRLS 权限。用 Python 3.11.16 与仓库既有 Core 依赖，不新增依赖。
- 每例使用唯一 `b1_replay_<32hex>` schema；只删除该例合成 schema 和该例运行的 checkpoint 行。既有 PG 集群和其它库不删除、不停服。

## 精确入口

```bash
python -m tools.b1_restore_replay \
  --operation-id b1-stage-restore-20261021 \
  --scope stage --database zhiming_core_b1_restore --schema mingjing_core \
  --candidate-source /absolute/fixed-b9-release \
  --candidate-python /absolute/fixed-b9-release/venv/core/bin/python \
  --ledger /protected/latest-withdrawals-v2.json \
  --ledger-sha256 <raw-file-sha256> \
  --quiesced --apply --output /protected/new-replay-receipt.json
```

DSN 仅来自 `B1_RESTORE_OWNER_DSN`，不放命令行、不打印；只允许回环、5432、指定恢复库及同名 `_owner`。缺少 `--apply` 只做本地输入和包校验，数据库连接数为 0。正式 stage 要求 Linux；`--local-drill` 只供本机 55480/55481 与上述合成 schema 对照，不能拓宽目标到 `zhiming_core_stage`、live 或其它库。

ledger 是候选原生 `core3-withdrawals-v2` JSON，不添加不兼容的外层 envelope。`--ledger-sha256` 核对原始文件字节；ledger 需私有权限，不得带额外正文键。正式入口核查文件和上级无符号链接、候选全文件 hash / 附加文件、PG15、当前库与角色、schema1–7 checksums、完整 owner 集、无 queued/running/有效租约、无其它客户端会话以及互斥 advisory lock。`--quiesced` 是额外显式操作承诺，工具不替代 B1 上层维护门 / writer 栅栏。

receipt 为 `b1-stage-restore-replay-v1`，包含 operation_id、固定 target、ledger_sha256、checksums、数据库内部状态前后 hash、变更与重放计数、解释器 hash、POSIX 权限验证标志及模型/外部发送数 0。receipt 只写新 0600 文件，不覆盖。Windows 本机演练明确记录 POSIX 权限未验证；Linux 下强制检查私有文件 mode。

## 已执行检查

```text
python -X utf8 -m pytest tests/test_b1_restore_replay_contracts.py tests/test_b1_restore_replay_pg.py -q --tb=short
25 passed in 27.70s
ruff check <上述三个 tools 与三个 tests 文件> --select E,F,I,B,UP,SIM --line-length 120
All checks passed!
ruff format <同上六文件> --line-length 120 --check
6 files already formatted
```

所有测试清除凭据环境变量、关闭追踪，使用专用合成数据。17 个纯输入 / 文件护栏与 8 个真实 PG 测试覆盖：

1. 真实 schema4 `pg_dump --format=custom` → 最新撤销导出 → 只在自身合成 schema 上 `pg_restore --single-transaction` → 由原样 b9 仓储向前至 schema7 → 新入口重放。
2. 已撤回事实 / 原话不能复活；旧 draw 和 create 请求 tombstone 不能复活；已撤销 run 及三张 checkpoint 表的该线程数据清除。
3. 最新 sent / sending→uncertain 元数据重放后，真实 OutboxService 拒绝再次 claim；未创建 sender，不产生外部请求。
4. 相同 ledger 再跑，第二次 `changed=false` 且状态 hash 不变；sent 收据不因 uncertain 降级。
5. 不同 sent 收据冲突时整事务回滚，之前处理的撤销也不部分提交。
6. 排队任务、checksum 错误、其它客户端会话、遗漏 owner、远程或错库 / 错角色 / 隐藏连接覆盖均拒绝；错误只输出固定代码。
7. 默认校验 0 DB 连接；明确 apply 写新收据；已存在收据拒绝覆盖；候选附加未入 manifest 代码拒绝。

## 未验证 / 停止条件

- **Linux PG15 容器未运行，Linux owner / POSIX 文件权限 / 正式 stage 接线未验证。** 本机 Windows 证据不替代 29 号要求的 Linux 演练或大脑 30 号 Go。
- 此入口只支持 schema7 的 stage 恢复副本。**不能拿来做 schema4 的生产旧包回滚**；生产恢复重放仍需独立入口及原包兼容演练，执行单应保留阻塞。
- 解释器文件 hash 被记录；本入口不单独证明发布 venv 所有依赖及二进制平台等价，必须由 Linux 部署演练补齐。
- 运行后写收据若失败，数据库可能已提交；必须停止并交审阅，不自动重试。稳定 operation_id 与不可覆盖收据提供审计标识；没有伪称跨数据库 / 文件系统原子提交。
- B1 最新 ledger 的获取、维护门、writer 栅栏、备份与 schema4→7 的前置恢复由 B0–B6 负责；本工具不启动 / 停止服务、不创建库、不自动迁移、不调用旧硬编码 live restore。
- 发布包和迁移未发现需改动的必修问题；如后续发现，则仍固定 b9 并将其记为阻塞，不悄悄补包。
