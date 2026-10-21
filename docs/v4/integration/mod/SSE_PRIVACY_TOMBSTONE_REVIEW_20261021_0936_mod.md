# SSE 接线核对：撤回后的空载荷行不是完整事件

只读核对时刻：2026-10-21 09:37，北京时间。本轮只新增本文，没有改产品、测试、fixture 或别线文件，
没有运行测试、服务、PG、模型或飞书请求，也没有提交或推送 Git。

主线本地已入 Git 的契约明确：消费时跳过因撤销而清空的旧事件，不能重建旧正文。
模块 PgEventStore 则只接受完整合法的事件行。两者不能直接互换；应先定义可信隐私墓碑的读取适配。
这是尚未接线的差额，不是当前功能缺陷、数据泄漏或生产验收结论。

## 核对范围与身份

主线本地 HEAD 为 `edfc95e96f9c6877bcf38521c92a70da475790fa`。
读取时相关契约、reader、撤回和无痕退役文件没有未提交改动；未核远端推送、CI 或服务器状态。
模块线只读当前冻结文件，不将本地主线引用误称已部署版本。

本项不重复 08:25 跨线审查中的今日页、短依据别名、画像来源类型或 Schema JSON 对象一致性。
Q3 指南已有“24小时清理后需保留游标墓碑”的一般提醒；这里核对的是主线**现在已经存在的隐私清空行**
与完整事件存储端口之间的具体差额，隐私撤回与24小时保留策略不能混为一项。

## 已直接读到的事实

1. [线程运行契约](C:/Users/Administrator/Documents/Codex/zhiming-v4/docs/v4/contracts/thread_runtime_api_v1.md)
   规定 owner/subject 授权、Last-Event-ID、不可用游标的受控错误，以及消费时跳过清空旧事件、不重建正文。
   契约明确模块线的 SSE hub 和24小时 worker 尚未接入。
2. [clear_runtime_outputs](C:/Users/Administrator/Documents/Codex/zhiming-v4/mingjing_core/repositories/privacy_foundation.py:119)
   对当前 owner、目标 run 集合把 core_run_events.payload 设为 `{}`；没有删除其 owner/run/seq 行身份。
   [无痕退役](C:/Users/Administrator/Documents/Codex/zhiming-v4/mingjing_core/application/private_retention.py:68)
   也先撤销运行并清空私密结果，再清空对应事件载荷。
3. [RunEventReader.page](C:/Users/Administrator/Documents/Codex/zhiming-v4/mingjing_core/application/run_event_read.py:107)
   每页重新核运行权限；从 owner/run 限定的查询读行，先将扫描游标推进到该行 seq，载荷为空则跳过。
   因此“没有向客户端发正文”和“已经扫描过这个序号”是两个独立状态。
   validate_cursor 当前核整数范围及当前 owner/run 的最大 seq，不要求游标行含完整事件正文。
4. [row_event](C:/Users/Administrator/Documents/Codex/zhiming-v4-mod/mingjing_core/streaming/store_serialization.py:75)
   要求精确列集合、owner/run 一致，以及含 v/run_id/seq/ts 的完整 wire 对象；`{}` 会受控拒绝。
   [PgEventStore.replay](C:/Users/Administrator/Documents/Codex/zhiming-v4-mod/mingjing_core/streaming/pg_event_store.py:67)
   不只逐页转换每一行，也对非零 after_seq 所指游标行执行同样的完整事件转换。
5. [EventTransaction](C:/Users/Administrator/Documents/Codex/zhiming-v4-mod/mingjing_core/streaming/event_store.py:33)
   只声明完整事件读取与当前 run 检查端口，没有隐私墓碑类型或授权证明。
   端口声明本身不认证 PG 当前来源；实现由主线提供。

## 由代码推出的接线后果，尚未执行

以下仅用虚构序号说明控制流，不包含真人正文，也不是一项已运行的 PG 测试。

假设已认证的同 owner/run 中，seq=11、12 为撤源清空后的旧事件，后续 seq=13 是合法的当前终止事件。
主线 reader 从较早游标扫描，会跳过11、12并继续；即使某页全部是清空行，也以最后扫描序号继续读取。
在注入事务允许读取该运行安全终态的前提下，若把同一批原始行直接传模块 PgEventStore，完整事件转换会在11处拒绝。
若客户端重连游标恰为12，模块也会因该游标行缺完整 wire 而报告 unavailable。

这是**合法隐私清空与完整事件模型的接口不匹配**。当前模块的拒绝是 fail closed，不能描述成它泄露正文；
当前主线又没有使用该模块替换 reader，不能据此宣布现有 SSE 损坏。
不同 reader 的游标可用口径也须显式冻结，不能悄悄以“同是数字游标”假定等价。

尤其不能为了通过事件 Schema，从旧信封、operation ledger、缓存或模型回复中补回已撤回的11、12正文。
同理，不能把任意损坏载荷当成“合法已撤回”跳过；空载荷状态必须来自可信当前持久记录及隐私处理链。

## 建议的后续小里程碑，不在本轮实施

保留完整事件模型的严格校验，在主线真实 owner/run 授权之后添加独立的扫描适配层。
该层区分“可见完整事件”和“权威隐私墓碑”，返回已扫描位置、可见事件以及是否仍有后页；
输入不能由 HTTP 参数或模型自行标记为 revoked。

1. 主线先冻结最小内部墓碑证明：owner/run/seq、当前隐私状态及用于并发复核的 revision/epoch。
   这不是新增公共 events_v1 事件类型，不向 SSE 发空 JSON 或伪造 text_delta。
2. 同 owner/run 的可信墓碑只推进扫描游标，不交给完整事件 encoder；完整事件仍逐一执行原 Schema 校验。
   连续全空页也须继续，避免误判结束或固定在同一游标无限轮询。
3. 非零游标须按明确政策验证归属及可用性；缺失、外 scope 与损坏记录保持受控拒绝，不能扩大可读范围。
   合法隐私墓碑是否允许作为重连锚点，由主线契约确定后统一 reader 与模块适配。
4. 读取前和实际发出前的当前授权/撤销竞态仍由主线处理；纯内存结果、哈希或旧已提交信封不授予再次展示权。
5. 24小时 text_delta 清理保持独立：现有 cleanup 只产计划，不执行删除，也不等同隐私撤回。
   后续清理不能自动把 final、回执或错误当作可删正文重建材料。

未来采用替身及隔离 PG 验证时，至少固定如下真值；本轮没有写测试或宣称通过：

| 场景 | 应保留的行为 |
| --- | --- |
| 正常完整页 | owner/run/wire 身份与 Schema 严格核对，按 seq 输出 |
| 空行、完整行混合 | 权威隐私墓碑不输出正文，扫描位置继续推进 |
| 连续多页全部为空 | 不丢游标、不重复扫描、不凭可见事件数误判结束 |
| 游标正好指向可信墓碑 | 按新冻结政策恢复或受控重读状态，不能重建旧正文 |
| 错 owner/run 或未知游标 | 不因相同 seq 猜归属，不泄露其他 owner 的存在性 |
| 非空但坏 wire | 不冒充隐私墓碑吞掉校验失败 |
| 翻页间撤源/无痕退役 | 不从旧缓存继续发送刚失效的正文，保留当前终态语义 |
| 24小时清理与撤回重叠 | 两种证明分开，幂等、并发校验和终止事件不被绕过 |

## 读取来源 SHA256

以下是读取时的**工作文件原始字节 SHA256**；不是 Git object ID、运行授权或动态行为证据。
未修改这些文件。若接线时版本变化，须重新核对。

| 仓库与相对路径 | SHA256 |
| --- | --- |
| 主线 `docs/v4/contracts/thread_runtime_api_v1.md` | `81ac1477df0389cb2baa0643c5d75d25d873107a909c9844cd06acce092f507a` |
| 主线 `mingjing_core/application/run_event_read.py` | `01b0015e17d2792b5ef8459c72ff5df4daa1f0707b8bd2d4c0743ed640bf5b56` |
| 主线 `mingjing_core/repositories/privacy_foundation.py` | `3f512fc9d3e5cc3264647f1dd6ac68252c4931ac51e5102c3e1dfb0a84abfc1e` |
| 主线 `mingjing_core/application/private_retention.py` | `d154e23bb48c880cb7450f202a16fca5e9f5e7a58fadadb4f6b7fa90c4e341c1` |
| 模块 `mingjing_core/streaming/pg_event_store.py` | `e28df8b9b618fff83263edc5214a616fd7057d64c8b743c287c66dfa3ebad479` |
| 模块 `mingjing_core/streaming/store_serialization.py` | `b63e561388976136bd5951af0764d3da0119fb03f61e973748807135cc45f68f` |
| 模块 `mingjing_core/streaming/event_store.py` | `7ab20963120d7cef942855c7eb9c43cae5a3f3ce79a0739ca60af8b06421ff6b` |
| 模块 `mingjing_core/streaming/cleanup.py` | `5b2a833e63b253bc6b4530a1b4b7d657e1ed93becf9a66a1c2990d39a3950a9b` |

未决项是主线内部墓碑与扫描游标契约，不需要离线用户立即回答。本轮到此完成只读审查，后续继续其他队列。
