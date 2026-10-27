# P5 到期归档与精确撤销（本地应用服务）

记录：2026-10-24 00:07 +08:00；采用指令板 v3，分支 v4/p5-memory2，草稿 PR #17。未达到阶段验收，不写“记忆2.0就绪”。

新增真实仓储应用服务 `memory2_archive.py`、`memory2_archive_undo.py` 和纯日期边界 `memory2/expiration.py`。归档保留原话和历史，当前投影按有效事实集过滤；变更前态沿用现有 proposal 的遗忘级联。撤销检查当前用户明确操作、目标修订、来源/区间/授权，再恢复完整业务字段。未改后台调度、模型、渠道或提交门。

验证使用现存 `.venv-k3`、回环隔离 PostgreSQL 15，测试每例独立 schema、MockTransport 禁 HTTP，Python 子进程 loopback-only 网络守卫。清供应商凭据、关闭追踪，显式 FrozenClock 与 Asia/Shanghai 或指定 owner 时区，无真实模型、飞书、应用服务器访问，无下载。

相关检查：

```
python -m pytest tests/v4/memory2/test_expiration.py tests/v4/agent/test_memory2_archive_pg.py tests/v4/agent/test_memory2_archive_undo_pg.py tests/v4/agent/test_memory2_proposals_pg.py tests/v4/agent/test_memory2_proposal_undo_pg.py -q -p no:cacheprovider
55 passed in 14.20s

# 增加同槽历史不归档、无痕/迁移来源拒绝、已撤销确认拒绝后，仅重跑受影响文件：
python -m pytest tests/v4/memory2/test_expiration.py tests/v4/agent/test_memory2_archive_pg.py -q -p no:cacheprovider
32 passed in 4.97s
```

两批有重复范围，不相加计为独立用例。新增模块另有一轮早期 28 passed；代码评审后发现到期不应沿用隐私删除去清除历史回答，改用既有修订/当前事实投影过滤，增加真实 memory_search 的派生笔记不可见断言后才做上述组合检查。无失败测试被删改为迁就实现。

覆盖：本地日期结束边界、绝对时刻、事件结束、UTC/上海/纽约夏令时、无效与歧义日期、未知/反向结束、单值槽历史、目标不误过期；当前事实及其派生检索排除，历史保留，精确撤销，重复操作无新增修订，源修订/区间/人物/owner/无痕/迁移/凭据守卫，忘记后清快照且缓存回执拒绝复活。代码通过 E/F/I/B/UP/SIM、120 字符格式检查；新增函数不超过 60 行。

未验证/未完成：自动后台调用、认证操作入口、归档历史专用检索、指定 scripted 产品场景和新里程碑全量。上一轮全量仍保留 CLI 文案契约失败，不重跑旧全量来掩盖；本次仅一个测试 runner，未超过本线两个并发额度。无需结构迁移。
