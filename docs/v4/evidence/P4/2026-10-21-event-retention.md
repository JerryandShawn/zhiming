# P4 M5：手动事件清理与删除证明（2026-10-21）

记录时间为北京时间，测试环境故意保留`TZ=Asia/Tokyo`，业务用Clock/FrozenClock显式UTC。工作树`C:/Users/Administrator/Documents/Codex/zhiming-v4-p3-wire-p4`。本片8个生产文件、2个新测试、ExecPlan及本证据由root统一提交；不操作其他线文件。此记录是分片真实PG验证，不是新精确头全量或CI验收。

已提交终态的text_delta在24h后实际DELETE，其他健康事件在30d后实际DELETE；24h删行从同事务真实PG原行创建专用kind的精确、无正文墓碑，未知物理洞不借水位放行。30d关闭证明阻止ensure_terminal或RuntimeEvents重造final；原正常答案保留在run/history。默认没有后台注册或自动启动；只有明确调用EventRetentionSweep.tick才清理。

来源撤销/无痕退役原路径未改：payload={}的原seq/kind行留存，正文与步骤按旧门立即擦除。终态锚在成功/失败/queued取消原事务写入、绑定owner/run/subject/thread/attempt/epoch/status；updated_at与旧Journal完成时间不被当作提交锚。没有可信锚的旧终态仅skip并计数。

## 真实结果与失败历史

| 北京时间 | 阶段 | 结果 | 原始目录 |
| --- | --- | --- | --- |
| 11:12:50–11:12:58 | 精确a1270174归档+原9例首红 | 4 failed / 5 passed，6.47s | task的`private/p4-event-retention-baseline-20261021-a1270174-1/source/private/safe-narrow-386c1c8d83e4492e918df372e770cb4b` |
| 11:17:36–11:17:43 | 首轮实现 | 1 failed / 8 passed，5.94s | P4的`private/safe-narrow-c9a6cad65e0540e6ac90845389fd87de` |
| 11:20:25–11:20:38 | 新TTL/证明/锁/回滚目标 | 26 passed，11.33s | P4的`private/safe-narrow-d4aee04735394034b2c829fb15515c63` |
| 11:21:15–11:21:41 | 原明确8文件 | 51 passed，24.85s | P4的`private/safe-narrow-50ab7b759257430196f9d9932b3580b5` |
| 11:24:08–11:24:10 | 筛选饿死、closed失败与stale拒绝 | 3 passed，1.45s | P4的`private/safe-narrow-3300025b5c6e4aa68010c0eb63a406d3` |

首红的四失败准确为24h物理删行、30d物理删行、删尾后seq复用、真实删行与未知洞的精确cursor证明。基线为local `a1270174e6f64cfe1abe915a09836647c1da3484` / tree `a1bc41370850b1e554328d99d7b5e4cf5683cf99`，只额外加入新9例；archive SHA256为`8730f0b2d724ddacfdf5c47dfe77d5fe5506a8c393d31455641cbeaa188c2294`，新测试原件SHA256为`da517516208891fec9d072e19049ff8a516595f1c4b9870ab4cd4b97cc086ab5`。初次准备曾因共享HEAD已前移触发断言退出，留下自己的空private目录；未复用/删除它，也未触碰root正在跑的11点归档。

首轮实现的单失败是新fixture把运行中撤销误当作有成功提交锚；批准范围本来不改撤销路径，因此以捕获Clock只确定观察窗口，继续断言两期限后原元数据行及空payload不变，没有制造锚或放宽断言。TTL成功/失败测试的时钟helper则改为读取真实新增terminal锚；act从旧PrivacyMaintenance换为显式EventRetentionSweep，均为root事先批准的新测试接点更换。

合计29个新参数例、51个旧例分片通过，所有完成轮次0error/skip/xfail；绿轮0warning。最后3例后未重复无变化目标，故不把前两轮通过回签成“最终头全量80绿”。源码后续CI、全量由root另排；本片未启动全目录回归。所有真实模型调用、飞书发送、服务器访问均为0。

## 保护与公开读取行为

新目标覆盖：24h前不删/24h后真实删、30d其他行真实删且page/ensure_terminal重复不造final、正常答案保留；删尾后重试seq更大；删行精确游标可用而同范围未知洞/跨owner不可用；元数据无正文、规范TEXT编码、kind/scope/seq/指纹/布尔版本/多余字段/非规范JSON篡改拒绝；批量1行/幂等；中途异常整事务撤销墓碑与DELETE；旧updated_at伪龄无效、未知legacy锚skip；run锁SKIP与排队竞态、active lease不删、queued取消真实锚；30d后再撤销不重开；其他效果kind及run_event_v1操作账本保留；构造服务不启动任务；尚未到期的前排run不饿死到期run。

清理最多50个run、合计最多1000个事件/墓碑，按run锁同事务复核；每行证明由实际owner/run/seq非空行产生。usage只保存常量级水位/锚/关闭状态和scope指纹，不保存无界seq数组。墓碑在core_operations的专用kind `run_event_retention_v1`，规范元数据编码在`result_id TEXT`，不是不存在的result/JSON列；30d仅删除自己的kind+精确run哈希命名空间，不清普通幂等/效果回执。不新增权限、表、迁移、Schema字段或依赖。

24h至30d，`GET /api/runs/{id}/events`的非零cursor必须有当前owner/run实际元数据行，或真实清理创建的精确墓碑；未知洞仍固定拒绝。可信30d关闭后非零cursor固定不可用（HTTP前置校验422），起点0为空终态流，不再发final/error正文；已提交答案改走已授权GET run/history。正常清理证明与普通丢失严格区分：旧测试要求的“无清理证明丢final可修复”“原件损坏/擦除不能覆盖”仍保持。没有把到期时间、墓碑、水位或关闭字段加入公开events_v1载荷/Schema。

30d closed的failed/stale运行若请求恢复，固定EvidenceError“事件历史已过期，请明确发起新请求”，状态/预算/epoch/事件零变化。root选择当前保守拒绝；未来是否允许显式新epoch清洁再生成，列为待大脑产品决定。未closed正常重试仍保原预算/来源门，清旧终态锚并保HWM。不能借删旧started或Journal后再生成绕过旧幂等原件保护。

旧8文件的行为断言逐字未改：test_event_notify_pg、test_event_cursor_pg、test_event_cursor_http_pg、test_run_event_replay_pg、test_privacy_maintenance_pg、test_privacy_maintenance_boundaries_pg、test_p2_privacy_closure、test_stream_transaction_pg。公开Schema与旧迁移git diff为空。postgres.py只做11行最小局部差异，不整体格式化；其余9个普通源/测试文件Ruff与format通过，新增生产292/123行、新测试224/270行，函数均≤60行。

## 原始记录完整性（SHA256）

| 阶段 | pytest.log（bytes / SHA256） | pytest.xml（bytes / SHA256） |
| --- | --- | --- |
| 基线首红 | 2088 / `3095f771c5b2094371fb5ef788c5ba39c3aa0e949b35101cf6b40762be9f6b64` | 3550 / `c3609e982472636aa4e9391ec45b1d088e046edd205d01a6fb80741fff93375d` |
| 首轮fixture失误 | 814 / `9618feef50371e26c18cf628a8fc57dd6805a79f6561e8a62f994898715db8b1` | 2767 / `9cd05238188902782460610b6bff9643114e1c5887ef48eac2b4be14e445e48e` |
| 新26 | 102 / `141b78ca5251e298ac86199c34d6cb5a795db2ec71d84876de4008a562185371` | 6559 / `7253eb6a89bc94fe3ecd990297049da1f35b74cc8c4de5f00e864f7b5822bdc1` |
| 旧51 | 102 / `c738fd790f6717664efa2d92e9d60dea10d81d7c6b4857687cdd032d130f72bd` | 12145 / `7e9551e5386caf4d307e9253c6deb1c615cc533d3103908bba7cb66b451865c5` |
| 最后3 | 100 / `ce08d4f2d5c0be4cd28613e200e661c7b750ddfbed678fd44469976c2316ebc7` | 1018 / `8ef5c9f0ba36442eb9775834395ba1659e25193fe8c967f23388d7af8b450659` |

## 未完成与待决

默认小时后台仍未接线，不把显式手动能力说成自动清理已上线。未知legacy提交锚保守跳过；升级前无记录丢尾无法从现存行证明或还原，本片只保障新增写水位及本服务证明删除之后不重用序号。跨进程长压测、最终精确头全量/CI、全部P4/旧DOM、真实模型首字和线上期限均未验证。后台启用及过期旧运行能否显式新epoch恢复待后续审查；不访问服务器或修改b9。
