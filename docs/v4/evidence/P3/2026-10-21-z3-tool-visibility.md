# Z3 工具可见性切片

时间：2026-10-20 23:16，北京时间（Asia/Shanghai，+08:00）。依据为用户指定的 28 号文件第二节 Z3。

## 实现与边界

- `agent/tool_visibility.py` 固定十二个常驻名字及八个条件名字的顺序。仅披露已经真实注册的定义，不制造未实现工具。条件项按裁定顺序取剩余槽位，总数不超过 15；重排注册输入也不改变披露顺序。
- 有已揭示真实 draw 必保留 `tarot_read`；本轮真实计算后必保留 `chart_skill`；用户纠错、修改资料和报告事项进展时保留相应工具；可信 `only_tool` 在截断之前预留。预留后的输出仍保持固定顺序。常驻和必需集合若本身超过 15，返回可区分的 `TOOL_VISIBILITY_CONFLICT`，不悄悄删除常驻或必需能力。
- 危机优先只允许 `time_context`、`memory_search`。无痕优先阻止长期记忆、笔记、资料、事项和塔罗写入；只有明确标为 private_allowed 的其他写工具才可能披露，实际副作用仍需应用授权，不能靠可见性替代 Z4 提醒确认。
- 应用状态只来自当前租赁 run 的 owner / subject / thread / epoch、有效用户原话、当前 epoch 完成且成功的步骤、实际已选 draw 和 case。模型 request 里的 `tarot_topic`、`chart_computed` 等布尔声明无效。上一 epoch 的检索结果不解锁当前轮工具。当前原话中的引用或明确拒绝抽牌不解锁 `tarot_start`。
- `ToolRegistry` 披露前走策略；`LoopCycle._budget` 仅增加 `only_tool` 的必需透传，没有改循环顺序、次数、取消或恢复语义。执行已有持久工具步骤时可保留该步骤的必需工具，模型仍必须通过 LoopCycle 的实际 exposed 集合检查；新 PG 反例证明模型直接请求未披露塔罗不会创建 case 或 draw。
- 源码当前尚未注册 `chart_compute`、`memory_update`、`profile_update_request`、`chart_skill`；此处只提供正确披露策略，不能宣称这些应用能力完成。常驻在四种限制之外有十二个设计名，当前真实注册十一项；chart_compute 由 M4 补齐。
- 当前仓库尚无 P5b topic 实体接线，“塔罗话题 / 那件事的进展”由当前有效用户原话识别。后续 topic 路由可为同一纯策略提供可信分类；没有把模型自报话题当授权。

## Decision Log（供主线追加 ExecPlan）

2026-10-20 23:16 +08:00：Z3 明确替代旧“16 个注册工具，靠塔罗互斥恰好暴露 15 个”和“任何溢出一律拒绝”的披露算法。保留已注册名字、参数 schema、真实 PG 副作用、owner/epoch/source 校验及塔罗固定牌面/防反复不变量；改为固定常驻和条件顺序、可选项截断、必需项预留、危机与无痕优先。

旧 `test_toolkit_contracts` 保护固定顺序、扁平 schema 和安全过滤：更新顺序为 Z3 顺序，保留全部 schema / 安全断言；未知未审工具保持不披露。新增正反例覆盖普通条件溢出截断及必需项不截，无法满足上限时显式失败关闭。

旧 `test_tool_tarot_pg` 同时保护互斥展示和禁止隐式重抽：展示互斥已被 Z3 替代，测试输入现在显式提出塔罗；已有 revealed draw 和塔罗话题可同时披露两工具。实际应用仍拒绝用旧步骤重抽，固定 draw 仍可读取，外 owner / 缺失 draw 仍拒绝；没有修改塔罗业务 guard。

旧 `test_tool_registered_pg` 的“恰好 15”只是旧披露算法结果，保护的真实注册调用与 PG 写入仍保留；改为 1–15 并明确断言无关事项和塔罗不出现。不存在为了掩盖业务失败删除测试。

## 本机验证

解释器：既有 P2 Core Python；PG 为本机 PostgreSQL15、`core_test_main`、回环 55480，各例复用既有独立 `p2_test_<uuid>` fixture。测试进程清除模型/追踪凭据，关闭追踪，HTTP 由既有 fixture 拒绝。没有外部模型、飞书、stage 或生产连接。

1. 首轮新策略与 schema：`pytest tests/v4/agent/test_tool_visibility.py tests/v4/agent/test_toolkit_contracts.py -q`，**28 passed / 0.46s**。
2. 新策略/PG + Toolkit/Tarot + LoopCycle 控制、恢复、来源与连续自写回归九文件：**116 passed / 28.46s**。
3. 全部 `tests/v4/agent/test_tool*.py` 目标回归：**220 passed / 34.53s**。其后新增未披露模型调用、拒绝抽牌、资料更正反例。
4. 最新切片：`pytest tests/v4/agent/test_tool_visibility.py tests/v4/agent/test_tool_visibility_pg.py tests/v4/agent/test_toolkit_contracts.py tests/v4/agent/test_tool_tarot_pg.py tests/v4/agent/test_tool_registered_pg.py -q`，**56 passed / 9.27s**。包含 15 个当前真实 PG 状态用例，实际业务未用替身绕过。
5. 全部十个修改/新增 Python 文件 `ruff check --select E,F,I,B,UP,SIM --line-length 120` 通过；四份新增文件 `ruff format --check` 通过。AST 检查均 <400 行、无 >60 行函数。旧文件只小改相关行，没有整体重排。

上述计数相互重叠，不能相加。没有运行或声称真实模型披露质量验收；没有发布或合并。
