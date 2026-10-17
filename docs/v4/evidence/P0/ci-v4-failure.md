# P0：push CI 的 v4 步骤失败根因与网络修复

2026-10-17。证据来自 GitHub 连接器读取的真实 job 日志；不是本地结果推测。该失败与另一条 PR run 的 25 分钟取消不同，必须分别记录。

## 实际失败

- Head：`2af491252e0130f4d886aeddba99001c916257d3`
- [push run 39006682419](https://github.com/JerryandShawn/zhiming/actions/runs/39006682419)
- [core job 117320466755](https://github.com/JerryandShawn/zhiming/actions/runs/39006682419/job/117320466755)
- run / job 实际结论：`failure`。

| 检查 | 真实结果 |
| --- | --- |
| Core service and calculator checks | `Ran 553 tests in 1121.225s`，成功 |
| Frontend checks | 成功 |
| v4 clock and evaluation framework | `55 failed, 129 passed in 3.37s`，退出 1 |
| scripted self-test | 同一步骤先前的 pytest 失败，未继续执行 |

v4 步骤在 05:53:11 UTC 开始，05:53:15 UTC 报错。55 项失败都来自真实 PG 适配器验证，错误为：

```text
tools/eval/targets/local_db.py:47
ValueError: Evaluation requires a loopback PostgreSQL 15 server
```

失败发生在 `V3Target.reset()` 调用 `verify_local_postgres()` 时，尚未进入场景业务轮次，不是 55 个模型回答或业务断言失败。

## 根因

原工作流使用 `services.postgres`，通过 Docker 默认网桥把容器的 5432 端口发布到 runner 的 `127.0.0.1:5432`。评测 DSN 的客户端连接地址正确钉住回环地址；但 PostgreSQL 的 `inet_server_addr()` 返回服务端接受连接所用的地址，在这种端口转发下是容器网桥地址。

安全检查同时要求 PostgreSQL 15 与服务端回环地址，因此合法的本机 Docker service 被拒绝。日志确认使用 PostgreSQL 15 镜像、Core 的真实 PG 检查已通过；结合原 workflow 的网桥端口转发方式和抛错位置，可定位为 **CI 网络布置与服务端回环检查不兼容**。

## 修复范围

保留评测 DSN 与 PostgreSQL 安全检查；没有放宽任何远程、stage 或 live 连接许可。只修改 `.github/workflows/ci.yml`：

- 移除 GitHub Actions 自动创建的网桥 service。
- 普通 step 用 `docker run --detach --network host postgres:15` 启动本次隔离库，并显式 `listen_addresses=127.0.0.1`。Linux host 网络使客户端与 PostgreSQL 服务端均看到回环地址。
- 用 `pg_isready` 最多 30 次、每次间隔 2 秒等待就绪。
- 安装依赖后、旧 Core 长检查前，先调用同一个 `verify_local_postgres()`；网络配置不兼容会在长测试前明确失败。
- `always()` 清理本次命名容器；保留 60 分钟时限、全部 553 项旧 Core、全部 v4 测试与前端检查。

没有使用 `services.options: --network host`，避免 GitHub services 自有网络与手工 host 网络冲突；没有修改业务、测试断言或测试选择范围。

## 验证与待完成

本地已解析工作流 YAML，核对 60 分钟时限、host 网络、回环监听、有限等待、提前验证与总是清理，原三组检查命令全部保留。

另用 Bash 的 `-n` 语法模式逐一检查 7 个 `run` step，全部通过；该模式没有执行 Docker 或模型命令。

Windows 本机没有运行该 Ubuntu host-network workflow；实际修复是否通过必须以新提交的 GitHub CI 为准。本次不把既有本机测试或旧 run 的 Core 成功当作新 CI 绿灯。
