# 10:00 固定源码完整回归

记录：2026-10-21T10:22:44.900388+08:00（北京时间）。本机 `95df0f9ca850a4a52d821817c40ce3a1b9058a8f` → 远端 `95df0f9ca850a4a52d821817c40ce3a1b9058a8f`，tree `e5b8322906fd975a1d3ed88ee86d8ae5d6634e29`；独立 git archive 的 1279 个 tracked blobs 原字节逐一核对，0差异。后续工作区WIP不在该源，调度为+08、测试显式TZ=Asia/Tokyo。完整开始/结束见同名JSON；当次未生成JUnit时只保留console计数，不补造XML或节点身份。

| 范围 | 原始结果 | exit |
| --- | --- | --- |
| tests/v4 | 2751 passed, 1 xfailed, 1 warning in 883.84s (0:14:43) | 0 |

## 失败与局限

已完成范围summary没有failure/error；若未生成JUnit，只保留console计数，不能补造节点或XML。严格xfail不计通过。

本机隔离PG、ScriptedProvider/MockTransport/回环HTTP；供应商真实请求、飞书、服务器访问均0。宽回归不替代M8原47脚本、盲评、Linux CI或发布；原X03与旧DOM真实回执等未完成门保留。原轮失败档案不覆盖，新修复须另固定source验证；不能把此结果移给后续提交或别的工作树。B1固定b9的Linux整链及删除收据往返阻塞独立保留，本次测试绿色探针不构成B1通过。

## 私有原始产物字节索引

公开只复制安全统计/节点名，不复制异常栈、正文、推理、口令或完整DSN；raw字节SHA与公开LF Git blob不同。

| 原始产物 | bytes | SHA256 |
| --- | ---: | --- |
| m8-scripted-metadata.json | 4011 | `5611f673ea7a45cc2a935d3ccc45fce6f0fa4d1382d90c9b9f78660b9c1a31da` |
| metadata.json | 312 | `9031d414f96e542be3ececcf98a1404017cb2e1580fe0bd3694d32245076709b` |
| scripted-extensions.log | 748 | `8554f53609a7a84acfe5675c760626f4c1a337a511f5d579fb79448ad288061d` |
| scripted-full.log | 1521 | `4ce1729c2fe78776412dfaf1a44158bb3291bec37b0ae114c6d8daa89055cfc2` |
| v4.log | 3781 | `1f78a89179aa4d17783caf8d9473581e6327928ca3ab8116e373fb9e1d18feba` |
