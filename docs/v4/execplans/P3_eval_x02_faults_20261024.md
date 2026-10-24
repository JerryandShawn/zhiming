# P3：X02 的实际503故障与重试观察

本活计划遵循AGENTS与`.agent/PLANS.md`。时间为北京时间；仅隔离本机PG与MockTransport，不调用真实模型，不访问服务器或外发。

## Context and Orientation

指令板v8要求首发核心完整脚本通过后才可真实评测。原f18报告原80题展开81用例为69/81，不能通过改gold、注入事件或标N/A解除失败。此次在已有干净eval-resume树从7996c0b新建v4/p3-wire-x02-faults-20261024，不动另一树在途的first_release控件/fixture、模块记忆区或暂停线。

复用实际`mingjing_core/models/registry.py`的RegistryPort与其单层重试、实际HTTP适配器的503分类、`tools/eval/targets/v4_protocols.py`的wire_output及既有真实V4Target/AgentRuntime/PG持久层。现v4_target只读provider_failures而原X02声明primary_errors=[503,503]，FaultScriptedPort没有有限错误序列，原报告的一次调用不能证明两次503。

原X02还要求两次503后切DeepSeek；当前TRANSIENT允许四次尝试，而首发生产configured_agent锁定同一会员主模型。该冲突待大脑裁定，本片不更改错误策略、配置、场景/金标或业务模型路由。

## Purpose / Big Picture

X02声明的503现经实际HTTP适配器和RegistryPort，以真实Mock请求和PG运行结果报告发生了什么。有限两次503后同主模型第三次返回，未凭脚本中声明的model.error/fallbacks伪造降级。原题降级断言仍如实失败，原报告与金标保留。

## Progress

- [x] (2026-10-24 06:34 +08:00) 按先写设计实现独立离线fault driver206行、V4Target必要小接线及一个104行真实PG目标；根与独立代理完整静态审阅通过，未动gold/生产策略/配置/记忆区。
- [x] (2026-10-24 06:33 +08:00) 仅占槽2跑唯一新增目标，首轮1/1通过、5.93秒；实际503/503/200与单逻辑步骤、原题仍红均有XML/PG实证，未重跑旧项或真实评测。
- [ ] 小提交/推自己的分支，保持Draft/未合main与v4main；源CI绿后再普通集成。

## Surprises & Discoveries

原X02的期望不是当前运行时事实。两次503及DeepSeek原先仅存在YAML脚本声明，原报告使用的V4Target没有执行这个故障边界，不能把其单次脚本文字成功解释为真实重试或降级。

本片实际三次Mock请求保持同一请求hash、同一合成主模型，前两次分类unavailable且原生max_attempts=4，成功action只消费1次；原题仍失败于turn[1].db[1]与turn[1].events。真实PG为succeeded/core4.0、一个completed模型Journal，助手model为synthetic-http-primary；没有DeepSeek请求或fallback记录。单个工具测试绿证明观察驱动正确，不能写成X02通过或改原69/81报告。

## Decision Log

2026-10-24 06:34 +08:00：采用真实首轮1/1作为此观察片验收，不扩大成模型质量/会员守卫/完整脚本放行；不按原题改生产4次尝试或主模型锁。非法503列表、provider/crash/撤销冲突、protocol及Live覆盖装配均在临时配置/PG之前拒，普通无primary_errors路径保持。静态小片已验证，后续仅有根审后提交推送，不重复稳定性测试。

2026-10-24 06:28 +08:00：driver使用真实ModelRegistry构造与resolve，不以绕过构造/重写resolve冒充原生配置路径。只在有限503输入已校验后，在TemporaryDirectory写唯一固定合成配置、显式稀疏合成environment，实际registry读取后立即清理；后续resolve须确认只读已装载data。这是测试输入，不是会员/K3/中央授权证明，不读取宿主凭据或改生产配置。

2026-10-24 06:21 +08:00：只修离线评测观察驱动；真实RegistryPort和适配器必须执行，MockTransport仅替代外部响应，PG/Agent业务不替身。若复用单个合成ModelHandle，需明确它仅证明既有错误策略，不能冒充受中央授权的会员配置或真实K3能力；不得为凑两次错误更改生产尝试上限。任何错误事件/元数据只能从实际已观察到的HTTP错误及选择推导，不能复制expected/scripted声明。

## Plan of Work

新增独立driver承接有限primary_errors。仅支持明确有限503序列，拒绝非法状态/过长序列/与现故障驱动冲突；只向synthetic.invalid的MockTransport响应，不读真实凭据或配置。成功响应复用现wire编码和脚本文字/工具，错误响应不能提前消费成功动作。V4Target选择该driver并通过现生命周期执行，保留生产RegistryPort重试和已有安全边界。

## Validation and Acceptance

只新增一个必要真实隔离PG目标：加载原X02不改gold，以实际三次Mock请求确认503/503/200；同主模型、无DeepSeek物理请求，实际run成功与Journal/答案可读；原题降级断言仍失败。报告区分物理Mock请求、模型逻辑轮数、外部真实请求0；不得把RegistryPort的单轮算成只有一次HTTP。既有原报告和场景hash不变。原非法输入若新增契约须在同目标内于首副作用前验证，不另开无意义稳定性套件。

## Idempotence and Recovery

仅既有eval_v4随机schema；由原target关闭清理其自有测试schema。失败保留安全runner原记录，不改报告补绿或自动重试整套；不得连接stage/生产或使用真实供应商凭据。

## Outcomes & Retrospective

已实现并首轮验证实际HTTP503错误路径、生产RegistryPort重试和隔离PG持久结果。唯一证据为本树private/safe-narrow-d6729abd83cc4c72bcb4fbccb9ba2d9c/metadata.json及同目录pytest.xml，2026-10-24 06:33:18–06:33:25 +08:00，1 passed in5.93s；XML固定属性为503/503/200、logical_model_steps=1、external_provider_requests=0、original_x02仍failed。测试清凭据/关追踪/TZ Tokyo，真实模型/服务器/外发0。206行helper与104行测试均函数≤60、120列，旧target408行仅必要接线，Ruff E/F/I/B/UP/SIM、format、AST与diff通过。

首发完整脚本门、真实等价/30题评测和发布继续关闭。待大脑裁定X02跨模型路由要求与当前同会员主模型锁冲突；本片配置是显式合成nonmembership/non-K3，不证明真实K3/中央授权、真实配额停止、质量或生产降级。原f18全题报告和原场景契约hash均保留。

## 修订记录

- 2026-10-24 06:34 +08:00：记录唯一新目标首1/1的真实HTTP/PG范围，更新四活节并保留原题红与待裁定，不重复测试或扩大真实门。

- 2026-10-24 06:28 +08:00：选真实registry解析固定临时合成配置，避免扩大成生产授权声明或跳过构造验证，尚未测试。

- 2026-10-24 06:21 +08:00：根据原题与运行时只读核对先写实施方案；选择真实错误策略观察，保留跨模型冲突和全部真实调用门。
