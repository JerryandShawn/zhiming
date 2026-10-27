# 11:00 固定源码完整回归

记录：2026-10-21T11:24:09.735608+08:00（北京时间）。本机 `a1270174e6f64cfe1abe915a09836647c1da3484` → 远端 `a1270174e6f64cfe1abe915a09836647c1da3484`，tree `a1bc41370850b1e554328d99d7b5e4cf5683cf99`；独立 git archive 的 1336 个 tracked blobs 原字节逐一核对，0差异。后续工作区WIP不在该源，调度为+08、测试显式TZ=Asia/Tokyo。完整开始/结束见同名JSON；当次未生成JUnit时只保留console计数，不补造XML或节点身份。

| 范围 | 原始结果 | exit |
| --- | --- | --- |
| tests/v4 | 2876 passed, 1 xfailed, 1 warning in 831.66s (0:13:51) | 0 |
| Core | 583 tests / 779.84s; 0 error/failure nodes | 0 |

## 失败与局限

已完成范围summary没有failure/error；若未生成JUnit，只保留console计数，不能补造节点或XML。严格xfail不计通过。

本机隔离PG、ScriptedProvider/MockTransport/回环HTTP；供应商真实请求、飞书、服务器访问均0。宽回归不替代M8原47脚本、盲评、Linux CI或发布；原X03与旧DOM真实回执等未完成门保留。原轮失败档案不覆盖，新修复须另固定source验证；不能把此结果移给后续提交或别的工作树。B1固定b9的Linux整链及删除收据往返阻塞独立保留，本次测试绿色探针不构成B1通过。

## 私有原始产物字节索引

公开只复制安全统计/节点名，不复制异常栈、正文、推理、口令或完整DSN；raw字节SHA与公开LF Git blob不同。

| 原始产物 | bytes | SHA256 |
| --- | ---: | --- |
| core.log | 6383 | `3803fea98261dee5a9f9044d4a92a3f612463b4afe575ec88037ab7e04fb57b4` |
| core_metadata.json | 401 | `cf0b494db030222442b65584fa0377ca10d541f2b0605bb5c22eede22bff33f5` |
| m8-scripted-metadata.json | 4192 | `3462a7ef25769481669c6704bbd7bdb84d9e93a91a35ed84765a4cebaf427e02` |
| metadata.json | 955 | `b8c1f8f5467069088f94c4a43c94a379e28df4b69f4382fdfeff3a94149146a5` |
| scripted-extensions.log | 758 | `fd202ecce511f2b0d9d32f9e86d6f9f3bb7ff5af486c2dca5316483a885f4840` |
| scripted-full.log | 1531 | `6456105eaf465a2134e1500351b12033f0b516fbd95fb61756a4e707e6afddaa` |
| v4.log | 3862 | `5e3e6d60ee241b7a356eeb7bbfa33389e1c9b565a021e4271c45b60fa1c6fe3c` |
| v4.xml | 641581 | `f0925a2b955212fa31f499d695d507887ea500e69c690ae1a434e14195e91ebd` |
