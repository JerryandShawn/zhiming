# 完整来源链可复跑性能口径

新增开发工具 `tools/mod_week/benchmark_final_pipeline_v3.py`，显式依赖冻结的开发验收harness；
生产模块不能依赖本工具或测试包。未改4个冻结测试、fixture、产品和既有性能工具。

复跑命令（输出必须是仓库内尚不存在的JSON，父目录必须已存在且可写）：

```powershell
& 'C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe' tools/mod_week/benchmark_final_pipeline_v3.py --output docs/v4/evidence/MOD_2026-10-21/MOD_final_pipeline_performance_reproducible.json
```

每批120链，覆盖七区、六个明确owner时区和三种报告。固定调用现有 `performance.measure(..., repeats=5)`：
一批预热、五批不带tracemalloc的墙钟样本，再单独一批tracemalloc。总计七批840链，非840个独立用户。
计入材料JSON解析、输入构造、原话锚、memory plan/apply、reflection计划/执行前守卫、八节render、report、
撤源不改epoch、所有旧输出失效及Memory2再次拒绝的断言。模块导入、材料字节读取、源hash、报告写入不计时。

全Core源码、冻结harness、材料、现有measure和本工具均在前后核hash；有漂移就拒绝报告。
provider keys在本进程清除、tracing关闭、socket禁止，所有内容和Clock均为合成输入。

旧 `MOD_final_pipeline_performance.json` 保留历史：它在tracemalloc开启时记录120条单次链分位。
新报告是五个未插桩批次墙钟和独立分配观测；仪器与计时口径不同，不能声称性能收益，
也不能把每批平均吞吐换算值说成单链p50/p95。均不是PG、生产SLA或真实投递验收。

实际观测：2026-10-21 08:49:31（北京时间），在root明确通知三遍全量结束后运行。
五批墙钟秒数为 `0.2536054 / 0.2545763 / 0.2516469 / 0.2544114 / 0.2534226`；
120链一批的中位数为 `0.2536054s`，最大值为 `0.2545763s`。
中位批次吞吐换算为 `2.113378ms/链`，不是单链延迟分位；独立tracemalloc峰为 `136262B`。
全部840链均完成守卫与输出断言；模型、网络、PG、通知、运行态写入均为0。

287份来源文件在测量前后完全一致，来源集合也未变化。
源码树SHA-256：`ea179011e4af1e99936cc176213b0f14fde843fe989e4dd4d645434614e9cb8c`。
报告 `MOD_final_pipeline_performance_reproducible.json` SHA-256：
`ac51421e7b297a049cc4988842b3e0a23951b6ce5fcfca8b09e004090f346e22`。
工具SHA-256：`1ee01d158db36ecffb36043bdb9bb15d7251d6e7774d9dc32b5c7534cd3f19f5`。
工具与JSON均为LF。现有开发测量器的口径、旧性能报告和冻结验收内容均未修改。
