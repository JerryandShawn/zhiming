# P3：把真实决策工具结果接入公开卡片与评审

遵循 `.agent/PLANS.md`；只用本机隔离PG、ScriptedPort和冻结events_v1，时间一律北京时间。

## Purpose / Big Picture

present_options 已能生成只读工具结果，但 core4.options 固定为null，用户无法收到公开卡片。本片从真实已完成步骤选最后成功卡片，安全提交后公开一次，恢复订阅也能幂等补齐。评审必须看到同一卡片，修订不能把已指出问题的旧卡继续公开。

## Context and Orientation

复用 agent/event_contracts.py 的 Options/Decision/PresentOptionsEvent，application/agent_finalization.py 的租约和来源版本闸门，agent_review_proofs.py 的真实模型行证明，agent_model_calls.py 的持久请求快照，以及 agent_runtime_events.py 的run行锁。不得改变冻结Schema、core3读取投影或root的U41危机兜底；不改前端和模块线SSE核心。

## Progress

- [x] (2026-10-21 01:03) 读完工具参数、真实结果、finalizer、critic、proof、公开事件与读取端；确认自由文本可逆性不能直接作为冻结枚举。
- [x] (2026-10-21 01:11) 从同run/epoch真实成功步骤投影卡片，确定稳定程序ID，逐字段引用与保存回执真实性验证。
- [x] (2026-10-21 01:11) 评审材料/证明绑定实际卡片、原请求及其对应模型步骤指纹；revise（含改写失败）抑制原卡。
- [x] (2026-10-21 01:11) 16项新增真实PG端到端/并发重放/失败/旧epoch/篡改检查通过；最终相关139项通过，公开Schema不变。

## Surprises & Discoveries

工具只保存 title/benefit/cost/risk/reversibility/first_step；公开冻结结构还要求程序ID和unknowns。当前工具没有unknowns输入，因此先给空列表，自由文本可逆性只有与明确枚举完全相同才保留，其余保守unknown。不会为此扩展公开Schema。

## Decision Log

只从PG同run/epoch completed、error为空、ok=true的present_options中选最后成功结果。最终卡片逐字段执行结构/引用验证；保存声明只能由该字段实际引用的实体写入回执支持，不用无关saved回执授权。critic材料包含规范卡片，proof绑定原工具输出hash、规范卡片hash及真实critic请求快照。任何实际revise会抑制该卡，即使一次文本改写失败而评审显示skipped。

## Plan of Work

先添加纯投影和PG选择/结构校验，再接finalizer/envelope；随后补critic绑定和失败修订抑制，最后接公开事件与终态恢复。每次窄测最多一个测试进程，不发外部请求。阶段提交由root统一处理。

## Concrete Steps

    python -m pytest tests/v4/agent/test_present_options*_pg.py -q
    python -m pytest tests/v4/agent/test_agent_runtime_pg.py tests/v4/agent/test_agent_runtime_recovery_pg.py tests/v4/agent/test_run_event_replay_pg.py -q
    ruff check <本片文件> --select E,F,I,B,UP,SIM --line-length 120

## Validation and Acceptance

真实工具调用经Loop和Finalizer产生core4.options，公开present_options与最终对象严格相同；多卡最后成功、失败/旧epoch不发布、结构引用失效拒绝；pass看到真实卡片，revise最多一次且旧卡被抑制；篡改proof/card/request不能提交。并发回放各一张卡和final。已有core3读取回归不变，D01脚本观察可后续接公开信封断言。

## Idempotence and Recovery

卡片ID由run/epoch/实际工具seq决定。已提交事件由run行锁核实际信封后复用seq，不覆盖不同内容。源撤销仍由既有版本闸门重新生成一次或失败关闭。没有新迁移；撤回接线后保留原PG工具证据，不把旧卡当成新卡。

## Artifacts and Notes

证据 `docs/v4/evidence/P3/2026-10-21-present-options.md` 与同名JSON，记录候选源码hash、16项新增真实PG检查和139项窄回归。

## Interfaces and Dependencies

新增纯 agent/options.py 与 application/agent_options.py、必要critic快照核验helper；现有finalizer/envelope增加内部options投影。公开Schema与旧工具参数不扩展，无新依赖。

## Outcomes & Retrospective

本机公开卡片链路候选已通过真实PG和ScriptedPort验证：工具→核心信封→提交后卡片事件→final→幂等回放。critic确实读取规范卡片，证明绑定实际工具行和实际请求；一次revise后原卡抑制，改写失败也不会重新发布问题卡。三类自洽篡改均拒绝提交，卡片引用进入message及信封血缘，U41和core3读端相关回归保持绿。最终139项/29.38秒通过，1个既有Starlette弃用提醒；11文件Ruff/format/400-60通过。未执行真实模型、服务器、飞书请求、前端交互、全部评测或新头CI；unknowns工具输入扩展尚未做。由root统一提交推送，PR保持草稿。

## 修订记录

- 2026-10-21 01:03 创建，明确真实步骤选择、冻结结构与critic失败修订的抑制边界。
- 2026-10-21 01:11 冻结本机候选，补139项相关回归、结构/引用安全、三个篡改反例及Schema零漂移证据。
