# P5 单值槽应用服务：本地相关证据

2026-10-24 00:22 +08:00，指令板 v3，v4/p5-memory2，PR #17 保持草稿。不是阶段验收或产品场景分数。

新增 10 槽的有限表、存量事实原话/授权检查、真实 PG 更新和撤销服务；没有启用未协调的工具参数或绕开 updated 提交证明。8 个 single 槽均有实际更新正例；multi 爱好与重要人物不允许替换。临时状态不覆盖长期值，未知名称不推断，历史旧事实仍 active、当前事实仅新值。

在清供应商凭据、关闭追踪、loopback-only Python 网络守卫下，用现成 .venv-k3 和独立 schema 的本机 PG15，显式 FrozenClock/来源时刻：

```
python -m pytest tests/v4/memory2/test_slots.py tests/v4/agent/test_memory2_slots_pg.py -q -p no:cacheprovider
44 passed in 4.75s

# 新增严格时间/有效期、多个候选、链式更新、撤销缓存和敏感原话守卫后，仅重跑受影响 PG 文件：
python -m pytest tests/v4/agent/test_memory2_slots_pg.py -q -p no:cacheprovider
26 passed in 6.97s
```

两批重叠，不相加；中间另有一次增补守卫后的 24 passed / 6.61s。最后的 PG 文件含真实 P3 敏感提案确认→单值槽更新，证明没有另建敏感授权流程；也验证低敏 kind 标签不能掩盖未授权健康正文。检查包括：精确旧字段恢复、新值 retired、依赖引用失效、重复操作无新增修订、手改后拒绝覆盖、owner/人物/事项/源修订/撤销/授权、同槽多候选拒绝、逆序/同时/未来原话拒绝、外层准入事务失败整体回滚、连续两次更新后只撤销最后一次。

00:25 又补一个跨人物/事项定向检查，1 passed / 1.00s。首轮这个新用例失败是测试构造问题：试图用 put 给已有事实换事项，但仓储保留既有身份/事项，因此未构造出跨事项输入；改为先把来源合法关联事项，再经真实 writer 创建事项事实，明确断言其 case_id 后验证拒绝。未改仓储或放宽 ScopeError 断言，不把首次失败隐去。

6 个新文件通过 E/F/I/B/UP/SIM、120 字符格式及单文件≤400/单函数≤60 行检查。本轮只使用一个测试 runner，没有全量回归、模型调用、飞书投递、服务器访问或下载。

未完成：真实 memory_write 的 slot 接入、可能冲突提案消费、遗忘链两端恢复、跨变更组合撤销、指定 --target v4 scripted 场景、updated 的提交门和事件映射。原全量 CLI 文案契约失败仍保留；不能将独立服务通过当作 KU01/KU02 已通过。

本轮 00:09:29 +08:00 已 fetch 并尝试普通 merge 集成上游，返回 Already up to date；没有合并 PR、rebase 或强推。下一次同步最迟 02:09。
