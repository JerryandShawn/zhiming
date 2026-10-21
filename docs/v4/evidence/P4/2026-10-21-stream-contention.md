# P4 窄切片回执：合法短读锁与流式写入的有界协调

记录时间：2026-10-21 11:07，北京时间UTC+08。仅本机真实隔离PG、Scripted/quiet loopback模型替身；真实模型请求、服务器访问、飞书发送均0。测试环境为Asia/Tokyo，记录使用安全runner明确生成的UTC+08时间，不从本机显示时区推算。

- 分支 / 基底：`v4/p3-wire-p4-20261021 @ a1270174e6f64cfe1abe915a09836647c1da3484`；本片4件未提交，待root独立提交推送。
- PR：沿用Draft PR #14；本片未合并、未部署。
- ExecPlan：`docs/v4/execplans/P4_stream_contention_20261021.md`。
- 本次结果来自工作区，不是root11点a127不可变archive，不是GitHub CI。相关33项中的联合5件是未提交、原字节hash冻结的源码；它们随后由root另一个提交交付，不能把本片与联合片混成已提交候选。

## 完成了什么

- [x] 复现真实合法短读引发一次try永久失败：实际PG读事务持有同owner advisory锁，透明游标转发真实False后通知读事务释放；修复前直接LeaseConflict，真实Runtime的150ms timer刷新也失败。首红2失败、1通过保留。
- [x] 仅在获取同一owner锁时增加有界重试：第一次try前建立25ms单调deadline，每次尝试前后核stop/期限，每次停止Event退避最多1ms。没有重新调用模型、重放工具或重造事件。
- [x] 合法读释放后继续真实timer提交；第一次busy后收到stop则只尝试一次、不进入写入。新3项与原7项合跑10/10通过。
- [x] 原worker/timer/scope/真实Runtime及冻结联合HTTP消费者明确5文件合跑33/33通过。原长占锁仍LeaseConflict且<0.3秒；旧7项文件原字节不改。
- [ ] P4整体验收、历史联合两次首delta超时归因、生产启用、供应商就绪均未完成。本切片不关闭这些门。

## 评测分数与实际测试

本片没有重跑M8脚本总表或真实模型评测；10/10、33/33是下面窄测试成绩，不能替代原P3的46/47或供应商质量评测。每次只有一个窄pytest进程，11:03:16结束后已释放槽，没有目录整库或后续重测。

| 北京时间起止 | 源码状态与目标 | 实际结果 | 私有原件目录 |
| --- | --- | --- | --- |
| 11:01:58.401559–11:02:01.978936 | 原一次try实现；新增contention 3项 | 2失败、1通过，2.63秒，exit1 | `private/safe-narrow-069780f3c993484d85b3d637f246822b` |
| 11:02:27.999625–11:02:34.200056 | 修复后；contention 3项+原transaction 7项 | 10通过，5.23秒，exit0；0失败/错误/跳过 | `private/safe-narrow-d6243063953e45a0846eef303d9adfae` |
| 11:02:54.904918–11:03:16.929383 | 修复后工作区；下列明确5文件，含未提交冻结联合片 | 33通过，21.05秒，exit0；0失败/错误/跳过 | `private/safe-narrow-f12742d1861a48229a9afe3865954787` |

原红直接短读例在一次try的LeaseConflict失败；真实timer例预期已持久delta且未取消失败，未放宽断言。stop例在原实现已通过。修复后没有更改这3条测试或原7项断言。

使用root已审的私有安全runner，解释器为现有P2 Core环境；runner固定本机隔离PG、清凭据和隐式PG/代理变量、关闭追踪。命令前缀如下，第一次传入新增文件，第二次传入新增与原transaction文件，第三次传入下面5文件：

```powershell
& C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe -X utf8 C:/Users/Administrator/Documents/Codex/2026-10-17/v4-ai-claude-c-users-administrator-4/work/b1_readonly/run_narrow_safe.py C:/Users/Administrator/Documents/Codex/zhiming-v4-p3-wire-p4 <具体测试文件...>
```

第三次目标准确为：

```text
tests/v4/streaming_integration/test_stream_worker.py
tests/v4/streaming_integration/test_stream_timer_pg.py
tests/v4/streaming_integration/test_stream_candidate_scope.py
tests/v4/streaming_integration/test_stream_candidate_runtime_pg.py
tests/v4/streaming_integration/test_stream_hints_joint_http_pg.py
```

### 原始产物对应关系

原件保留在上述private目录，只记录计数、字节和hash，不复制正文、DSN或凭据。JUnit自身timestamp带runner进程时区偏移，表中北京时间来自同目录metadata明确的UTC+08起止，不把JUnit表面小时误作北京时间。

| 目录简称 | 原件 | 字节 | SHA256 |
| --- | --- | ---: | --- |
| `069780…` | `pytest.xml` | 2101 | `d36746651a44e843970850779d6fa2eb6f20c1567c1b64a8f85100bd6f9709b3` |
| `069780…` | `pytest.log` | 1659 | `29b90a0c1455ce4ea90b1aaf8a15164c9b9d4d90bea54363d750c8fed003b8f1` |
| `069780…` | `metadata.json` | 451 | `4577a33ba56a8e639dcc15fa0bf33273759f2f8af9fd7c3ac0dc1513a04cbde3` |
| `d62430…` | `pytest.xml` | 2644 | `79dd2a762490653b6b0987869ac34738c33193ceff3bda8af4503df44d1e647f` |
| `d62430…` | `pytest.log` | 101 | `039ec9bcb98c64de37b416e89af053201a76a1c1527beb92f1e44c40f5d7851d` |
| `d62430…` | `metadata.json` | 520 | `bc17c571665ee82ef6876e368a4b9f818485a183b3a23a63735b9c1c974cb805` |
| `f12742…` | `pytest.xml` | 8497 | `d7ebe7d3491b2edac54e6ce342cef4fdbc1ea998d39fbdcc2e389ce19118d91c` |
| `f12742…` | `pytest.log` | 102 | `4a9b3e198442b25e1c388bb65235ff4c388a2a1474ab787c724655bedb651209` |
| `f12742…` | `metadata.json` | 726 | `1f9dc7389eeabc641fbdd9ce6c88da7b3f52aab4d92401052cdb15c949f42230` |

### 未提交联合5件的源码身份

这些原件仅由33项消费者组合使用，本片不修改、不提交它们。以下raw SHA256是冻结身份，不是“已在a127”的声明。工作区测试包含同期源码，未生成全树不可变快照；本表只证明明确冻结原件的对应关系，最终候选须由root固定新tree复验。

| 文件 | 字节 | raw SHA256 |
| --- | ---: | --- |
| `tests/v4/streaming_integration/test_stream_hints_joint_http_pg.py` | 9030 | `d61f850d19365c3356649935cb3e31e3c7403db21a36356c370d42364c1d6f28` |
| `tests/v4/streaming_integration/stream_joint_http_support.py` | 5661 | `44d698d8d4cdc8d6bf9341305fa2b38d94e6d7cd5cf91c0d4c5175938fa4d472` |
| `tests/v4/streaming_integration/stream_joint_process.py` | 3423 | `ba5584271b63ce3e3e6b07edc2c293761df427fddbafd21ce8be7c695fc19809` |
| `docs/v4/execplans/P4_stream_hints_joint_20261021.md` | 7849 | `8c375a187e2208295e6fc868120a106cf628e7822366f85342ea9c298a0a0185` |
| `docs/v4/evidence/P4/2026-10-21-stream-hints-joint.md` | 9399 | `16ef8082996ec73fa0d7ae8f75cb19683117a5e76893d77008c2f7437fae4e6a` |

## 改了哪些关键文件

本片4件：`repositories/streaming_transaction.py`、新`test_stream_contention_pg.py`、独立ExecPlan和本证据。生产helper为65行、最长函数21行；新测试148行、最长函数24行。生产helper raw SHA256为`2c7b068a878f6e4eee87b91794a842276f7bd5ae85a18fa1d9e11e72e34c6b94`（2469字节）；新测试为`1201e0d9bd77dd4568a3bc7019f171048a9338538558656ae1217fafef56799c`（5717字节）。

原`test_stream_transaction_pg.py`不修改：4871字节，raw SHA256 `8e870d8ae3bc5c76d2eda779a64952cd1c75daddf96dc5de697cfbfa20b8915f`。Ruff E/F/I/B/UP/SIM、120列、format、AST尺寸和git diff whitespace静态检查通过；没有新增依赖、Schema或迁移。

## 数据库迁移与回滚方式

无迁移。只有本机隔离测试数据。候选开关仍默认关闭；源码回退仅还原本片仓储helper，不需改库或删除事件。已提交事件仍保留，owner/subject/epoch/lease/来源版本门不变。root负责提交与回退，不在本片执行合并或部署。

## 偏离设计的地方及理由

合法短读不是模型/领域失败；将一次try改为原25ms预算内可停止重试，避免瞬时busy永久终止actor。未改通用repo.transaction、Loop、ToolBatch、Runtime或公开events_v1，未改变长持锁异常类型。单调计时只负责内部锁预算，业务时间仍由原Clock提供。

## 未验证 / 已知风险

- 历史联合两次跨进程首delta超时没有owner acquisition及足够PG阶段记录。本片证明一个真实可行机制，没有证明它就是旧两红根因，旧日志与缺口继续保留。
- 取消状态转换尚不主动发`mj_run`；真实默认150ms回读可满足已有取消测试，人工5秒fallback下的差额仍未实现。本片没有修改通知行为。
- 25ms是重试调度预算，尝试前后都检查；不能严格限制单次数据库/网络调用或COMMIT。原pool50ms、statement100ms、row lock25ms、ack750ms、未知提交拒final及取消门都保留；网络黑洞仍未验证。
- 当前结果是本机工作区窄证据。P3 X03、旧DOM、受信encoder等既有阻塞不被清除；P4完整回归/远端CI/真实Linux或服务器行为由各自候选证据判定。

## 需要用户或大脑决定的问题

本片无需新增产品决定。历史跨进程间歇继续保留，后续若定位须先审批仅安全阶段/计数诊断；不能因本片绿而抹去旧失败。root已决定本片4件与联合5件分别提交。

## 建议后续

root固定新提交tree后纳入下一合规时窗的完整门；若需复现旧间歇，记录安全阶段、单调时间、owner acquired布尔、异常类型和计数，不记录正文、DSN、SQL参数或租约值。本片结束后不再启动pytest，测试槽已交回主线。
