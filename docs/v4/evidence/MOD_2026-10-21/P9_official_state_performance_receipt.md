# P9 官方状态机完整路径性能

实际本机合成观测见P9_official_state_performance.json，源hash绑定纯状态机、builder、Q6租约及本次fixture/runner；这不是HTTP或持久化性能。

1. 每轮100条完整create→send→update→finalize→close路径，五份实际wire描述、每次claim/dispatch完整当前来源/产物核对、合成ACK，并在后三步分别metadata restore：中位0.659565秒，Python分配峰76124字节。每条最终必须两个关闭ACK、closed、acked seq=3。
2. 每轮200条先create/send确认，再update已dispatch后崩溃或租约过期恢复；全部必须uncertain、保留同card且拒绝重发：中位0.754900秒，峰47655字节。

每项预热一次、正式测三次、另单独tracemalloc一次；包括合成host快照构造、JSON/指纹、守卫及断言，不计真实等待。FrozenClock每次推进400ms，不能把模拟时长当真实网络节流吞吐。独立重复无共享存储，不能证明数据库原子性、并发事务、实际ACK真实性或设备显示；峰为Python分配而非进程RSS，缓存可能影响结果。

命令：

```text
python tools/mod_week/benchmark_cardkit_official_v3.py --output docs/v4/evidence/MOD_2026-10-21/P9_official_state_performance.json
ruff check --select E,F,I,B,UP,SIM --line-length 120 tools/mod_week/official_synthetic_fixture.py tools/mod_week/benchmark_cardkit_official_v3.py
ruff format --check --line-length 120 tools/mod_week/official_synthetic_fixture.py tools/mod_week/benchmark_cardkit_official_v3.py
```

实际脚本全部断言通过，Ruff/format通过。只新增工具和观测，不改已通过9560回归的产品代码；没有模型/服务器/飞书/PG请求。
