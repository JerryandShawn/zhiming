# K3刷新公开边界接线补充（2026-10-21）

本轮只新增9项独立流程测试与证据，没有修改K3产品、旧token基线或原测试/黄金。
原接线基线见[Q6 K3与流式Outbox](Q6_p9_v2_20261021.md)。接口不变，本补充不启用任何实际回调。

## 公开端口与失败边界

`K3TokenService(store, clock=..., lookup=...)`仍复用旧原子consume及稳定operation；
`issue(**claim)`返回`IssuedActionToken`，`consume(token, **claim)`返回`TokenClickResult`。
只有`should_execute`为真才取得本次能力消费许可，主线随后仍须核验实体/来源并查业务operation账本。
不同新token即使绑定同一业务，operation也保持相同；不能据新token绕过已完成业务的幂等账本。

`MemoryTokenMetadataLookup`只读取公开不可变record tuple。host snapshot异常、list或混入坏成员的tuple
会失败关闭，不挑选局部合法项。多owner记录按完整digest/claim查找，撤回另一digest不改变目标授权。
内存记录只含摘要及绑定元数据，不持久保存raw token或业务正文。

可选`lookup.guard()`入口失败时不进行lookup或consume。若本地consume已经记账而guard退出报错，
调用方得到统一无效错误，本次没有返回执行许可；同一能力后续只有同operation重放，不能再次取得许可。
这只说明内存参考状态，不代表PG回滚、事务提交或业务效果已发生。PG host应在同owner权威事务内完成
当前metadata/撤回/实体读取、原子consume和业务effect账本；未知结果由该账本对账，不能重开旧能力。

Clock在consume阶段抛错或返回naive值时，统一失败、不误报过期、不烧掉能力；恢复合法aware Clock后仍可
首次消费。只核外部可观察行为，不依赖内部读取次数。Clock仍须注入，不依赖Tokyo主机时区。
格式合法但与公开issue.operation_id不符的metadata不能因已过期而取得刷新意图。

K3原时效保持：普通提问/决策/记忆回执/晨报24小时；删除原话/记忆及应用整理确认15分钟。
仅当前、完整绑定且真实过期的metadata返回“这张卡已过期，我重新发一张”。这是意图，不代表新卡已发送，
也不执行原动作；错误owner、撤销、未知token或坏host投影均不能靠该文案泄漏卡片是否存在。
真实回调字段和官方平台接线继续由已有官方候选适配层处理，本轮无业务接口调用。

## 证据与边界

原9项首测9/9通过；经root另授权，两套`p9_v2`、`p9_official_v3`兼容1976/1976通过，24.34秒，
实际结束北京`2026-10-21T11:14:05.641202+08:00`。48份窄相关材料集合/字节before/after一致，
排除无关legacy bridge及runner整文件。运行环境复用runner.environment清12类key并关闭tracing。

覆盖仅两个产品原分母：

| 文件 | 行 | 分支 | 综合 |
| --- | --- | --- | --- |
| action_token_policy_v2.py | 61/62 | 15/16 | 76/78 = 97.43590% |
| action_token_refresh_v2.py | 65/71 | 14/20 | 79/91 = 86.81319% |
| 合计 | 126/133 = 94.73684% | 29/36 = 80.55556% | 155/169 = 91.71598% |

coverage报告另列6行协议等排除项；不把排除项当覆盖通过。缺行：policy73；refresh29、53、101、106、109、111，
均按原报告保留，未新增R10–R14构造器镜像测试。覆盖不代表所有输入、PG真实性或平台效果。
没有本轮性能、全项目回归、CI、模型、服务器、PG或飞书发送结论。

证据索引：

- [冻结9行矩阵](../../evidence/MOD_2026-10-21/K3_public_frozen_matrix_20261021.json)，SHA`387974c21ef77e8c07748093ca98ec14917cc7938a9936a9d53b76ab873b91c1`。
- [首测9项](../../evidence/MOD_2026-10-21/K3_public_first_target_20261021.json)。
- [两套兼容及48材料快照](../../evidence/MOD_2026-10-21/K3_public_compat_coverage_20261021.json)，SHA`503cb53f25d2cab83f610a26675dde12b1d70a11ae6e9cadd5521fe1f7742c10`。
- [两文件原始覆盖](../../evidence/MOD_2026-10-21/K3_public_coverage_final_20261021.json)，SHA`d8ffa66f5b075e4069e7e41805144d243569992e797f9505ce07de511f468416`。

generated token只在进程内登记；pytest输出先在内存精确脱敏后落日志，short traceback且无locals。
实际替换0次，没有raw token写出。覆盖JSON无CR且保持工具原始字节/末尾状态，不为排版改SHA。
