# P0：CI 执行时限调整

核对日期：2026-10-17（UTC+08:00）。仅调整 GitHub Actions job 的环境时限，不修改业务、测试、锁文件或执行范围。

## 被中止的运行

- Head：`2af491252e0130f4d886aeddba99001c916257d3`
- [PR workflow run 39006685718](https://github.com/JerryandShawn/zhiming/actions/runs/39006685718)
- [core job 117320476490](https://github.com/JerryandShawn/zhiming/actions/runs/39006685718/job/117320476490)
- GitHub API 实际结论：run 与 job 均为 `completed / cancelled`。

已读取该 job 的真实日志：

| 记录 | UTC | UTC+08:00 |
| --- | --- | --- |
| Job 第一条日志 | 05:33:22.905 | 13:33:22.905 |
| Core 测试命令启动 | 05:34:35.737 | 13:34:35.737 |
| 最后一条具名测试通过输出 | 05:57:57.115 | 13:57:57.115 |
| `The operation was canceled.` | 05:58:34.644 | 13:58:34.644 |

Job 从首条日志到取消约 **25 分 12 秒**，与该 head 的 `.github/workflows/ci.yml` 中 `timeout-minutes: 25` 一致，判断为运行时限中止。API 的取消结论与日志已确认；日志未给出测试断言失败摘要。

取消时仍在 `Core service and calculator checks`。日志中可识别 **92 条带测试名称的 `... ok` 完成记录**，最后一项为：

```text
test_core_88_fusion_snapshot_denials.FusionSnapshotDenialsPG.test_safe_caveat_cannot_excuse_a_positive_in_another_field
```

这是旧 Core 前段的否定语义与多体系回归区域；不能把局部通过记录当作整个 553 项套件完成。没有 `FAIL:` / `ERROR:` 或 `FAILED (...)` 摘要。环境安装成功，后续 `Frontend checks` 与 `v4 clock and evaluation framework` 因 job 取消而跳过。

## 修改与理由

将同一 core job 的 `timeout-minutes` 从 **25 调整到 60**。旧 Core 的 553 项检查使用真实隔离 PG、真实排盘子进程及较密集的比较/修复回归；随后仍需执行前端检查、184 项 v4 测试及 scripted 自测。原 25 分钟预算在 GitHub 托管 Ubuntu 环境中已经实际耗尽。

60 分钟为这些完整检查提供更大的有限执行窗口；没有删除测试、跳过断言、缩减真实计算，或使用 `continue-on-error`。测试耗时不均匀，前段通过数量不能线性外推总耗时；60 分钟是否足够，仍须由新提交上的实际 CI 结果确认。

## 本地验证与待验证

已用现有 PyYAML 解析工作流，确认 `jobs.core.timeout-minutes == 60`。工作流 diff 只有该时限值一处变化，不新增低价值测试。

本次没有提交、推送或重跑 CI；由主执行者提交后另行发布并运行。新 CI 未验证，不能将被取消的旧 run 写成通过。
