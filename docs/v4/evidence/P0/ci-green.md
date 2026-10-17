# P0：最新修复提交的 PR CI 通过证据

核对时间：2026-10-17 19:03:52（UTC+08:00）。以下结论对应固定提交，不能用于宣称后续其他 head 已通过。

- Head：`dffc1842c86e6a58afc0de72e5baaaa2fad29428`
- [PR workflow run 39026173478](https://github.com/JerryandShawn/zhiming/actions/runs/39026173478)
- [core job 117377478737](https://github.com/JerryandShawn/zhiming/actions/runs/39026173478/job/117377478737)
- GitHub 连接器 `fetch_commit_workflow_runs` 与 `fetch_workflow_run_jobs` 实际结论：**completed / success**。

已读取该 job 的真实日志，未用本机测试结果替代远端证据。

| 远端检查 | 日志结果 | 日志耗时 |
| --- | --- | --- |
| Start loopback PostgreSQL 15 | success | 未单独统计 |
| Verify loopback PostgreSQL 15 | `Loopback PostgreSQL 15 verified` | 未单独统计 |
| Core service and calculator checks | `Ran 553 tests in 722.663s`，成功 | 722.663 秒 |
| Frontend checks | 六项命令全部成功 | 未单独统计 |
| v4 新测试 | `230 passed in 32.03s` | 32.03 秒 |
| 场景 schema 校验 | `Validated 80/80 scenarios` | 未单独统计 |
| scripted / fake 评测 | `Result: 80/80; n/a on v3: 0` | 未单独统计 |
| 框架 self-test | `48 passed in 1.09s` | 1.09 秒 |
| Stop isolated PostgreSQL | success | 未单独统计 |

前端六项分别为 `npm test`、`node tests/dom.test.cjs`、`node tests/report-settings.dom.test.cjs`、`node tests/method-limits.dom.test.cjs`、`node --check static/app.js`、`npm run build`。同一步骤在 Bash `-e` 下全部执行结束并得到 success。

这一运行已经实际验证 host-network PostgreSQL 15 的回环启动与原安全检查兼容，随后完整旧 Core、前端、v4、scripted 检查均通过。先前 Docker 网桥导致的 v4 初始化失败已在该提交远端通过验证；25 分钟旧 PR run 的取消也不能覆盖本次真实成功结论。

## 同提交 push 运行的最终状态

19:03 的初始核对时，push 仍在旧 Core 步骤，因此当时只记录为进行中。随后于 **19:16:57（UTC+08:00）** 重新读取 [push run 39026169977](https://github.com/JerryandShawn/zhiming/actions/runs/39026169977) / [core job 117377467580](https://github.com/JerryandShawn/zhiming/actions/runs/39026169977/job/117377467580)：工作流唯一 job 已为 **completed / success**，所有步骤成功。

该 push job 的真实日志为：

| 检查 | 最终结果 | 日志耗时 |
| --- | --- | --- |
| 回环 PG 启动与 preflight | success | 未单独统计 |
| 旧 Core | 553 项，成功 | 1630.387 秒 |
| 前端六项命令 | success | 未单独统计 |
| v4 新测试 | 230 passed | 64.79 秒 |
| scripted / fake 评测 | 80/80 | 未单独统计 |
| 框架 self-test | 48 passed | 1.86 秒 |
| PG 容器清理 | success | 未单独统计 |

两条运行的耗时明显不同，但固定 head 相同，实际检查均已成功；不使用单次 runner 的耗时线性推断其他运行的结果。两条完成后已停止轮询。

## 验证边界

这是固定 head `dffc184` 的 GitHub PR CI 绿灯。scripted / fake 的 80/80 验证框架回放与断言，不代表 v4 产品能力或真实模型基线通过。真实 live 评测由独立报告记录；后续若修改源码形成新 head，仍须核对新 head 的实际 CI。

## 场景契约修复后的 PR CI（fe9e35a）

最终代码head `fe9e35af15d46993b88ad4e6fdd6a81b245f49f4` 的 [PR run39028870575](https://github.com/JerryandShawn/zhiming/actions/runs/39028870575) / [job117385161079](https://github.com/JerryandShawn/zhiming/actions/runs/39028870575/job/117385161079) 已由GitHub实际状态确认 **completed/success**。读取真实日志：Core553/1087.283秒；前端六命令通过；新测试250 passed/84.05秒；schema80/80；scripted80/80；self-test48/13.32秒；loopback preflight及清理成功。该结果覆盖场景契约与离线补元数据工具的20项新增回归。

后续证据/结果提交如形成新head，最新状态须另外核对；本节不替代尚未完成的后续CI。

同head push [39028867570](https://github.com/JerryandShawn/zhiming/actions/runs/39028867570) / [job117385152644](https://github.com/JerryandShawn/zhiming/actions/runs/39028867570/job/117385152644) 也已实际 completed/success、所有步骤成功。真实日志：Core553/1637.216秒；前端六命令；新测试250/110.49秒；schema及scripted80/80；self-test48/16.76秒；PG preflight与清理成功。两条fe9e35a运行均已结束，不再轮询。
