# 储备b：新模块性能与Python分配峰基线

全部为本地合成、顺序执行；每项1次预热、5个墙钟样本和独立tracemalloc。下表时间为中位秒，内存为字节。不能解释成进程RSS、并发容量、PG事务或真实模型/通知时延。各JSON保留实际时间、完整5样本和源码SHA，不选最快样本。

| 范围 / 每次单位 | 中位秒 | Python峰 | 原始证据 |
| --- | ---: | ---: | --- |
| U4普通1000解析 | 0.081406 | 61658 | [Q1](Q1_timeparse_perf.json) |
| U4历法1000解析 | 0.471829 | 73256 | [Q1](Q1_timeparse_perf.json) |
| 记忆1000来源×10全文检索 | 0.317474 | 107616 | [Q2](Q2_memory2_perf.json) |
| SSE1000追加/编码/重放 | 0.038386 | 624352 | [Q3](Q3_sse_perf.json) |
| SSE5000增量合并 | 0.038305 | 3915 | [Q3](Q3_sse_perf.json) |
| 调度120混合循环 | 0.595090 | 38206 | [Q4](Q4_scheduling_perf.json) |
| 1000投递计划 | 0.022787 | 5999 | [Q4](Q4_scheduling_perf.json) |
| 整理1000分类 / 100话题 | 0.132744 / 0.017068 | 182426 / 390196 | [Q5](Q5_performance.json) |
| token1000签发/消费/重放 | 0.207545 | 1148349 | [Q6](Q6_k3_performance.json) |
| 500 namespace CAS | 0.237852 | 19568 | [Q6](Q6_metadata_performance.json) |
| 1000状态metadata回转 | 0.037627 | 3649 | [Q6](Q6_metadata_performance.json) |
| 100完整卡片生命周期 | 0.242586 | 22111 | [租约实路径](RB_stream_lease_performance.json) |
| 1000已dispatch崩溃恢复/拒重领 | 0.852855 | 21552 | [租约实路径](RB_stream_lease_performance.json) |
| 100写/100重放/50撤销 | 1.500014 | 282214 | [记忆生命周期](RB_memory_lifecycle_performance.json) |
| 1000到期归档并还原 | 2.689038 | 10650460 | [记忆生命周期](RB_memory_lifecycle_performance.json) |
| 1000事实反思提案 | 1.118485 | 908926 | [记忆生命周期](RB_memory_lifecycle_performance.json) |
| 1000英文/资料绝对化 | 0.134621 | 38566 | [RA](RA_timeparse_extended_performance.json) |

记忆生命周期的1000条事实共享一条合成来源，原文锚点真实保留；不是1000独立原话的查询成本。token末尾命中和错绑定另有满1000容量实测，fixture准备排除计时，首个完整签发场景含准备。卡片生命周期实际逐步执行claim/dispatch两次freshness，包含完整manifest、ack同卡和seq断言；没有transport。

这里只给基线，没有声称优化收益。后续应先定位记忆归档/撤销分配热点，保留相同负载和字段还原验收再比较；不能靠缩小输入或删来源校验获得速度。合成分数、盲评质量和CPU时延是不同证据；Q5弃权目标未达仍未验收。

跨模块完整链的额外性能在RC_pipeline_performance.json及RC回执，单独计量，避免把各步骤单位混在一起。
