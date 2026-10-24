# 10:00 固定源码完整回归

记录：2026-10-21T10:20:01.248421+08:00（北京时间）。本机 `ff4b4f65d762c8eef33a6e557b003050a3a808fd` → 远端 `ff4b4f65d762c8eef33a6e557b003050a3a808fd`，tree `b88d8f9a3f6cf7d5005214ee74a552bb6415c961`；独立 git archive 的 1275 个 tracked blobs 原字节逐一核对，0差异。后续工作区WIP不在该源，调度为+08、测试显式TZ=Asia/Tokyo。完整开始/结束及JUnit原时区原值见同名JSON。

| 范围 | 原始结果 | exit |
| --- | --- | --- |
| Core | 583 tests / 863.736s; 0 error/failure nodes | 0 |

## 失败与局限

本次已完成范围没有failure/error节点；严格xfail和普通skip仍单列JSON，不计作通过。

本机隔离PG、ScriptedProvider/MockTransport/回环HTTP；供应商真实请求、飞书、服务器访问均0。宽回归不替代M8原47脚本、盲评、Linux CI或发布；原X03与旧DOM真实回执等未完成门保留。原轮失败档案不覆盖，新修复须另固定source验证；不能把此结果移给后续提交或别的工作树。B1固定b9的Linux整链及删除收据往返阻塞独立保留，本次测试绿色探针不构成B1通过。

## 私有原始产物字节索引

公开只复制安全统计/节点名，不复制异常栈、正文、推理、口令或完整DSN；raw字节SHA与公开LF Git blob不同。

| 原始产物 | bytes | SHA256 |
| --- | ---: | --- |
| core.log | 6347 | `594e72e7d77d3c5477b5840e23b3412d667a90e32166df8f46fe8bfd90bcd92c` |
| core_metadata.json | 220 | `31ea5563d05e6a0ac62aa87d302d47cdce623aee935c6eeb10bb2ee5644a32e8` |
| metadata.json | 378 | `8f70b9b52dae270f71637f4dfe76f3eef24cae4a50d388178459a3bd8e736751` |
