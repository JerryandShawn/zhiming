# P3：固定每轮通道安全配置

本ExecPlan遵循.agent/PLANS.md，为P3原提示词“从config/runtime.yaml读取安全上限”的独立小片。

## Purpose / Big Picture

可信运行时从仓库固定路径加载安全限制；交互40次/480秒/6工具，后台60次/1200秒/10工具，重复3次、租约150秒/续租20秒。降低配置应在真实循环生效，任何未知字段、布尔、负数、超限配置阻止安装v4，不影响默认v3。当前epoch首次领租约后把规范配置与hash固定，恢复不被后续配置变更改变。

## Context and Orientation

主树C:/Users/Administrator/Documents/Codex/zhiming-v4；蓝图§3.2的表按通道，P3提示词第1项要求runtime.yaml。复用agent/loop_policy.py的LoopPolicy/RunControl、application/agent_runtime.py的RuntimePort、RuntimeState.authority、repo._leased短事务及PG usage私有metadata。保留组件直接注入无lane的LoopPolicy、Clock、ScriptedPort、Journal重放、取消/撤销及core4冻结Schema。不得读HTTP/model自报配置路径，不改loop_cycle/codec/toolkit。

## Progress

- [x] (2026-10-21 01:41 +08:00) 完整核蓝图安全表、当前LoopPolicy/Runtime与配置入口，明确可信持久lane取代用户depth扩上限。
- [x] (2026-10-21 01:45 +08:00) 严格配置、可信加载、实际Runtime按epoch pin；首轮83 passed/10.29s。
- [x] (2026-10-21 01:50 +08:00) 补实际crash/reclaim、下一epoch、并发/身份/旧租约与超限hash反例；最终171 passed/53.80s，真实loopback HTTP取消/续租另2 passed/1.82s。
- [x] (2026-10-21 01:50 +08:00) 六Python Ruff/format、400/60检查与证据完成，交root统一提交推送。

## Surprises & Discoveries

旧LoopPolicy用request.depth选择40或60，蓝图表实际按interactive/background。深度偏好仍保留原request和prompt策略，但不能扩大交互通道执行限制。已成功旧run可能没有配置pin，不得因此阻断其兼容读取。

## Decision Log

2026-10-21 +08:00：按root确认，LoopPolicy增加可选lane，组件不带lane保留既有深度默认；生产从持久lane构造。配置只含所有确实接到循环和租约控制的键，不加入未实现并行、token、quota字段。每run/epoch在真实lease事务内pin规范配置与hash；无用户确认或真实模型请求。

恢复只读原pin；新epoch也沿用该run前一pin配置，避免清洁重生期间变更限制。deadline取既有值与配置允许值较早者，进程重启不重置墙钟，初始lease也只收紧，之后RunControl按配置续租。记录的SHA是规范配置校验而非授权签名，PG owner/lease/epoch仍是唯一准入。

扩展目标第一次153项中152通过、1失败：新旧租约反例误期待EvidenceError，实际底层正确抛LeaseConflict。只把该新case精确改期待LeaseConflict，其他scope/epoch仍EvidenceError；无旧测试或生产租约放宽。

## Plan of Work

新增config/runtime.yaml、agent/runtime_config.py、application/runtime_limits.py与专属纯/PG测试。AgentRuntime构造只接受已验证的可信RuntimeConfig对象，默认固定仓库文件；执行每epoch从PG取得原pin policy。绑定owner/run/subject/thread/lane/epoch，不信调用方字典；普通副作用、回复与公开Schema不变。

## Concrete Steps

在主树使用既有P2 Core解释器、本机隔离PG15测试库，每例独立schema、清供应商凭据/关闭追踪。只占一个pytest进程，不跑全量。目标命令完成后写入证据，不在计划预填成功数字。

    python -m pytest tests/v4/agent/test_runtime_config.py tests/v4/agent/test_runtime_limits_pg.py tests/v4/agent/test_loop_cycle_controls.py -q

## Validation and Acceptance

T01/R07/Q01相关运行控制不依赖宿主Tokyo时间；原47场景不在本片重复评测。验证标准为降低iteration/tools/repeat真实减少执行；max_seconds写入真实deadline、lease/renew实际调用；interactive深度不扩大，background标准可取后台限制；配置错误零模型步骤、v3可构造；崩溃恢复不替换pin、并发只一份、身份/epoch/hash篡改拒绝；旧成功run无pin仍返回原结果。

## Idempotence and Recovery

无新迁移、无历史回填。首次pin与重放同一run行锁保护，旧pin不回写；新epoch保留已固定配置来源。配置变更只影响新run。回退代码不得删除已存pin、事实或消息，当前版本恢复应按已pin限制继续；有不符时安全停止。

## Artifacts and Notes

计划证据docs/v4/evidence/P3/2026-10-21-runtime-config.md。真实模型、飞书、服务器、主干合并均0。P1b中央额度、实际K3 encoder、只读工具并行另片，不冒充本片交付。

## Interfaces and Dependencies

RuntimeConfig/LoopPolicy为可信Python构造接口，load_runtime_config无路径参数；不增HTTP参数。使用现有PyYAML/Pydantic/psycopg，无新依赖。PG只修改当前run usage中的bodyless受保护配置metadata和现有deadline/lease字段，公开core4/events不变。

## Outcomes & Retrospective

已完成本片可信配置加载与真实运行控制接线，所有配置键都有实际循环/PG控制测试，未修改旧夹具。目标171项及实际HTTP两项通过；未执行完整回归、精确头CI或真实模型，P3整阶段仍未验收。新配置只影响新run，已pin run/epoch保持原限制。下一片只读并行、P1b组合及旧DOM回执另交，不混入本片。

## 修订记录

- 2026-10-21 01:41 +08:00：建立可信配置/epoch pin计划，实施与证据待完成。
- 2026-10-21 01:50 +08:00：追加实际171+2项目标、首次失败原因、pin恢复/通道/租约控制与限制；代码冻结交root。
