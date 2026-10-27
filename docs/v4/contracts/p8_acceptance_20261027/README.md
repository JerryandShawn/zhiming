# P8 第二批验收题（meta v4）

13题：DT流日3、WS择日3、AL黄历3、SY合盘3、BA交界1。每题复用原YAML字段、期望工具和可观察内容。
合成人物阿远：1994-03-12 08:20，成都104.07/30.67，Asia/Shanghai、clock、准确报告时刻；小禾也是合成资料。
`golden_facts.json`摘自已有真实计算样例，BA时柱为**甲辰**，交界前对照癸卯，距离380.536889秒；不凭印象写乙辰。

## 加载与命名空间

原`tools/eval/schema.py`只允许80个题号，因此本材料放独立目录，不污染旧80题和旧基线。
新增`benchmarks.acceptance_scenarios.P8Scenario`继承原严格字段模型，只扩展13个精确ID并限定chart/v4，
复用完整回放和确定性断言。该命名空间已在日报请求大脑确认，先按新增隔离方案准备。
主线应在自己的评测装配层加入此加载器，再和旧80题按全局唯一ID组合；不要把新题冒名C01或改写旧ID。

    python -m mingjing_core.adapters.charts.benchmarks.acceptance_replay --mode scripted --output <新的报告.json>

此命令只用既有FakeTarget，不运行任何业务工具/Agent或模型，13/13只代表材料回放自洽。
主线必须在集成候选上使用真实业务服务+ScriptedProvider跑同一组题，不能拿FakeTarget结果冒充第二批脚本门。
新增单测会删工具、改拒绝码、伪造引用、伪造写入和删除白话提示，证明错误回放确实会被判失败。

## 运行时观测约定

这是**要求主线补的只读测试观察接口**，不声称现有target已提供：

| inspect_db里的路径 | 取值来源 |
| --- | --- |
| p8_acceptance.engine_calls.<工具名> | 本轮真正进入计算服务的次数；拒绝前置校验为0，成功一次为1，不是库内部函数或子进程数量 |
| p8_acceptance.refusal_code | 预期业务拒绝的结构化code，CONSENT_REQUIRED或INVALID_ARGUMENT；不是transport error |
| p8_acceptance.long_term_writes | 本轮临时合盘派生的长期实体/档案/记忆/可复用artifact/引用账本新增及更新数量，必须0 |

这些观察须由真实调用轨迹与事务前后差分产生，不能从脚本的db动作或expect反推，也不能在缺失时默认填0。
缺观察即失败。普通运行步骤的审计日志可保留，但不能含对方生辰正文、临时完整结果或可长期复用的专业引用。
资料确认卡及授权账本的必要状态更新不计作“计算结果写长期实体”；二者必须分别审计，不能因此放行派生写入。

**工具调用与拒绝计算不同**：WS03、AL03、SY01/SY03期望调用主线带前置校验的工具护栏，
护栏返回安全拒绝，但原生计算次数仍为0。不能把tools_called中的synastry当成已算过合盘。
若主线未来改成工具调用前直接拒绝，应先经大脑裁定改对应调用断言，保留0计算/无泄漏/无写入硬门。

## 种子与模型参数

`seed.profile_overrides`显式补齐确认的IANA时区和clock_basis；主线seeder须把exact映射为P8的reported，
不能只看旧UTC偏移。`seed.controls.p8_acceptance`是测试控制面，不是运行时用户API。
subject/revision/出生资料由服务端确认档案取得，动作arguments不含birth或consent；只给日期、范围、用途或kind。
四个新工具的Agent参数名由主线装配映射到现有Core契约；本题的range等为声明的语义参数，不冒充已注册签名。

SY02的consent_fixture只能由主线测试seeder生成模拟的**按钮确认事件及授权账本**：绑定当前测试owner、双方修订、
romantic、确认卡operation_id，09:00授予、次日09:00过期、只用一次。必须用测试owner替换owner_binding标记并核归属。
聊天里“已经同意”不能产生授权；SY01缺账本、SY03uses_left=0，都必须先拒绝，不读取或输出对方生辰。
现实使用仍需对方知道且同意，所有样例均不是任何真实用户授权。

## 当前R33与第三批

本批临时合盘**不登记c/r、不写长期实体、不换前缀**；成功文本必须写“本次合盘是临时计算，没有存档”。
SY01/SY03也不能输出任何对方出生字段或专业引用。其余题的c/r只是脚本回放演示，主线须依据当前真实文档重新登记，
不能复制演示编号；BA示例引用来自现有阿远boundary文档，所有期待引用均须在主线真实账本再次核对。
日运只在用户明确询问时可见；不覆盖主动晨报受信入口（R36），无痕时四工具不暴露；每轮≤15工具仍是硬上限（R34）。

## 未覆盖

新题尚未在主线Agent目标执行、未跑真实模型、未证明现实预测效果。
旧C01–C07不在本目录改写；其迁移说明另交一页核对。临时合盘长期引用仍属第三批文档草案。
