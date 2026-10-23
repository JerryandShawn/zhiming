# 10:00 固定源码完整回归

记录：2026-10-21T10:23:24.035040+08:00（北京时间）。本机 `4f042e7cc17749c3f37a8bf17c80e32ea8c0eeea` → 远端 `6f8c44aa5c892af988a0310db10b2842561ed529`，tree `58c5381e648effd34d71c06008a3afe28a051c2f`；独立 git archive 的 1236 个 tracked blobs 原字节逐一核对，0差异。后续工作区WIP不在该源，调度为+08、测试显式TZ=Asia/Tokyo。完整开始/结束见同名JSON；当次未生成JUnit时只保留console计数，不补造XML或节点身份。

| 范围 | 原始结果 | exit |
| --- | --- | --- |
| tests/v4 | 2299 passed, 1 xfailed, 1 warning in 1301.22s (0:21:41) | 0 |
| Core | 582 tests / 841.537s; 0 error/failure nodes | 0 |

## 失败与局限

已完成范围summary没有failure/error；若未生成JUnit，只保留console计数，不能补造节点或XML。严格xfail不计通过。

本机隔离PG、ScriptedProvider/MockTransport/回环HTTP；供应商真实请求、飞书、服务器访问均0。宽回归不替代M8原47脚本、盲评、Linux CI或发布；原X03与旧DOM真实回执等未完成门保留。原轮失败档案不覆盖，新修复须另固定source验证；不能把此结果移给后续提交或别的工作树。B1固定b9的Linux整链及删除收据往返阻塞独立保留，本次测试绿色探针不构成B1通过。

## 私有原始产物字节索引

公开只复制安全统计/节点名，不复制异常栈、正文、推理、口令或完整DSN；raw字节SHA与公开LF Git blob不同。

| 原始产物 | bytes | SHA256 |
| --- | ---: | --- |
| core.log | 6346 | `9031e663ac171b9d1750929c92d14be860503eab3cf4189536fac50fcc39e84d` |
| core_metadata.json | 220 | `4b85a003d1eb4f288c1f3edceb24893c32a107563791b87692125313bae14691` |
| metadata.json | 312 | `f1d399699f6801d340c3cb67f6a762148572b5b8a686b1bb1d2bf25a35cded61` |
| v4.log | 3215 | `5e6c1e1468211e52e63abe3128e5e6f49e9e64e1f681c94dee62e7ffc42fbc30` |
