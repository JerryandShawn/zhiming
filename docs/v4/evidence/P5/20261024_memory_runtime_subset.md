# P5：真实 v4 scripted 子集 22/22，尚未完整验收

2026-10-24 01:48 +08:00；指令板 v3，v4/p5-memory2，PR #17 Draft。运行时提交 23ec602；本片新增执行语料构造器及覆盖清单，运行前处于未提交工作树状态。报告保留 source_sha256，未冒充已冻结完整候选。

## 范围与结果

需求合计 37 个 ID：M01–M13、R01–R09、F01–F04、Q06，及附录 B 的 A01–A03、MS01–MS03、KU01–KU02、TM01–TM02。当前实际以 --target v4 --mode scripted 执行其中 22 个：M01–M07、M09–M13、R01–R09、Q06。22/22 passed，32 次脚本 ModelPort 调用，评审 0 次，外部供应商请求 0，报告耗时 7.23s。单独的语料契约检查 2 passed /1.24s。

执行语料从原场景只保留模型文本/工具调用，剔除 scripted db/receipt/event 等状态注入；逐题 scenario_contract_sha256 必须与原评分契约一致。没有修改源 scenarios、scenarios_v4 或 v2.1 基线，输出目录若已存在直接拒绝覆盖。真实隔离 PG、原 AgentRuntime 和实际工具/提交守卫负责效果与回执，脚本不能提供观察到的数据库状态。公开 JSON 仅保留分数/ID/哈希等聚合信息；完整合成报告留 private。

## 未跑的 15 项

- M08：需补实际记忆确认动作驱动和有真实来源的 P3 pending 提案种子，不能把旧 scripted owner_settings/db 注入当授权。
- F01–F04：原契约涉及撤销/来源删除/运行中撤销动作及遗留派生种子。当前 v4 动作驱动只支持塔罗等既有路径；需要通过实际应用服务和真实来源构造，不能靠改状态断言凑绿。
- A01–A03、MS01–MS03、KU01–KU02、TM01–TM02：07 附录 B 中有设计，尚无独立场景文件；当前共享 schema 也未识别 A/MS/KU/TM 前缀。下一步按 v2.2 隔离补齐，不改正在保留的旧基线。

这只是 37 项中的 22 项实际执行成功，complete_memory2_acceptance=false。七节画像及归档/槽等服务检查不能代替剩余产品场景，第七节专业档案和主线接线仍待完成，日报不写就绪。

## 复现

在清供应商凭据、追踪关闭、Python loopback-only 守卫和本机隔离测试 DSN 下，调用 write_memory2_corpus(Path('tools/eval/scenarios'), 一个尚不存在的私有目录)，然后：

```text
python tools/eval/runner.py --mode scripted --target v4 --scenarios private/p5-offline-tests/memory2-corpus-20261024-0144 --output private/p5-offline-tests/memory2-report-20261024-0144
```

不重跑先前完整回归。本次一个评测进程，没有访问应用服务器、飞书或下载模型；所有业务时钟由场景冻结，记录按北京时间。
