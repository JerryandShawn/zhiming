# 11:00 固定源码完整回归

记录：2026-10-21T11:24:10.725444+08:00（北京时间）。本机 `1fe5149cbe9de10632f97f84003ac833a4a4f65f` → 远端 `d8d92bb60dcaf808043174c5e34fa4020199b31a`，tree `d5505507c9ade137dc1214be1231571711bfae63`；独立 git archive 的 1255 个 tracked blobs 原字节逐一核对，0差异。后续工作区WIP不在该源，调度为+08、测试显式TZ=Asia/Tokyo。完整开始/结束见同名JSON；当次未生成JUnit时只保留console计数，不补造XML或节点身份。

| 范围 | 原始结果 | exit |
| --- | --- | --- |
| tests/v4 | 2414 passed, 1 xfailed, 1 warning in 1207.70s (0:20:07) | 0 |

## 失败与局限

已完成范围summary没有failure/error；若未生成JUnit，只保留console计数，不能补造节点或XML。严格xfail不计通过。

本机隔离PG、ScriptedProvider/MockTransport/回环HTTP；供应商真实请求、飞书、服务器访问均0。宽回归不替代M8原47脚本、盲评、Linux CI或发布；原X03与旧DOM真实回执等未完成门保留。原轮失败档案不覆盖，新修复须另固定source验证；不能把此结果移给后续提交或别的工作树。B1固定b9的Linux整链及删除收据往返阻塞独立保留，本次测试绿色探针不构成B1通过。

## 私有原始产物字节索引

公开只复制安全统计/节点名，不复制异常栈、正文、推理、口令或完整DSN；raw字节SHA与公开LF Git blob不同。

| 原始产物 | bytes | SHA256 |
| --- | ---: | --- |
| metadata.json | 957 | `d035c04485afd9d14ac79b93463973de7b1db33e3af256003f9736e2b75bc51f` |
| v4.log | 3377 | `f55f29fde0f8a1a7c505410a71a2c50658c8641e4ffafd8203ecb085f8d0b780` |
| v4.xml | 545758 | `a9acb45e82b815d461841231709cc0afe51e7dd70ad5ff3c1976d54e5d6193b7` |
