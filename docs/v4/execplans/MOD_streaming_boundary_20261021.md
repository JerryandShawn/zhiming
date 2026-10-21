# MOD：补强流式重放、修订与保留边界验收

本计划遵循 `.agent/PLANS.md`。全部时间为北京时间；本轮只新增独立测试和证据，不修改已发布产品、原测试或黄金材料。

## Purpose / Big Picture

断线重连后，用户应看到本运行的完整事件，不因重复操作、序号空洞或修订而重复展示旧答案。
本轮用独立离线输入补验错误载荷、竞争写入、重放隔离和清理计划，证明拒绝行为不会返回其他人的正文。
覆盖率是这些行为被实际执行的附带证据，不替代数据库事务、HTTP 路由或真实浏览器验收。

## Context and Orientation

工作目录为 `C:/Users/Administrator/Documents/Codex/zhiming-v4-mod`。
复用 `mingjing_core/streaming/memory_event_store.py:35` 的 `MemoryEventStore.append`、
`pg_event_store.py:77` 的 `PgEventStore.replay`、`resume.py:14` 的 `parse_last_event_id`、
`codec.py:54` 的 `decode_sse`、`text_projection.py:35` 的 `reduce_event`、
`cleanup.py:70` 的 `plan_delta_cleanup`，以及公开 Clock 与事件模型。
冻结依据是大脑 28 号第三节事件契约 v1、蓝图 §9、现有主线事件 Schema；不得新增事件种类或改变字段。
SSE 是文本事件传输；序号是有空洞也合法的全局递增身份；清理计划只是描述拟清理对象，不执行删除。
不得放松 owner/run 隔离、同操作同载荷幂等、24 小时从提交时刻计算、text_reset 覆盖旧文和心跳不占序号。

## Progress

- [x] (2026-10-21 08:52 +08:00) 读取指令板 v1、冻结契约、现有流式产品/测试及 DAY 覆盖缺口。
- [x] (2026-10-21 08:55 +08:00) 冻结独立行为清单，新增错误传输、失真行投影与状态边界测试。
- [x] (2026-10-21 08:59 +08:00) 新增目标测试 131 passed/0.22s；没有确认的产品缺陷。
- [x] (2026-10-21 08:59 +08:00) 全部流式离线套件 597 passed/2.32s，20 产品文件及本套件测试/样例前后身份一致。
- [x] (2026-10-21 09:00 +08:00) 完成新覆盖证据和回执，待 root 独立提交；未执行 Git 或外部调用。

## Surprises & Discoveries

初始 DAY 覆盖报告中，流式组件主要未覆盖错误时间、错误行映射、错误 SSE 外壳以及清理元数据拒绝分支。
现有内存存储已有线程竞争验收，PG 只有注入事务端口；本轮不会把替身并发当作真实 PG 事务证明。

## Decision Log

本轮先按冻结行为写输入与期望，再运行产品。错误载荷不为了执行某条分支而放松断言。
错 scope、外部游标和未知游标均不得泄漏正文或归属；同操作重放不得重新分配序号。
原始 DAY 证据保持历史；新报告将列出该模块实际行、分支和综合分母，未达 90% 也据实保留。
公开端口的错误类型不同可以有固定原因码，但不得在异常中包含输入正文。
首轮新增测试错误地在异常显示文本中匹配机器原因码，而产品的既定公开异常文本固定为中文，
机器码位于 `reason_code`。本轮改为核对该属性，拒绝行为与原因期望不变；巨大合成参数改用短 ID，
避免 Windows 下超长 nodeid 导致测试生命周期报错。这是新增测试接入修正，不修改原测试或产品。
首轮不是 132 个独立用例：121 passed + 9 failed = 130 个执行了 call 阶段的用例，另一个
200001 字符合成参数用例在 setup、teardown 各记一次 ERROR，合计显示 132 条结果事件，
但独立测试节点仍是 131。修正短 ID 后，该用例正常执行 call，最终 131 passed。
没有删除或合并用例、参数、保护断言；超长输入仍验证被拒且缓冲未改变。此前把错误归为
“临时路径超长”过于具体，现纠正为超长 nodeid 生命周期错误：原始巨大输出已被截断，未保留
完整 OS 调用栈，不据此声称已确定临时目录故障。静态检查本机 pytest runner 可见 setup 与
teardown 均把完整 nodeid 写入 `PYTEST_CURRENT_TEST`，这也说明两个 ERROR 不等于两个用例。

## Outcomes & Retrospective

新增 131 项独立边界验收通过，流式离线完整套件 597 项通过。只统计 20 个流式产品文件：
行覆盖 855/859=99.5343%，分支 240/244=98.3607%，综合 1095/1103=99.2747%，均超过 90%。
保留四处未执行行及分支：codec 的二次 +08 校验已受前置严格正则约束，另外是两种重复选项 ID
和 public validation=false 拒绝分支；不使用 monkeypatch 伪造标准库行为去刷最后的覆盖。
本轮只新增测试和证据，没有产品变更，没有确认产品失败。真实 PG、跨进程锁、授权路由、代理断线
和通知仍不在本轮范围。首次测试自身的 9 failed/121 passed/2 setup/teardown errors 保留为接入历史，
修正后没有更改任何拒绝行为真值。

## Plan of Work

新增 `tests/v4/streaming/test_codec_coverage_acceptance_mod.py`：单帧完整性、字段重复、UTF-8、
JSON 对象/版本/时间、嵌套重复键、历史 core3 读取边界和只读结果拷贝。
新增 `test_state_coverage_acceptance_mod.py`：缓冲/时钟非法状态、reset 后 generation 竞争、
error 终止、非文本事件保留文本、清理证明与元数据错误以及批次顺序不改变计划身份。
新增 `test_store_coverage_acceptance_mod.py` 和必要唯一 helper：失真数据库行、游标和端口返回，
同操作跨 owner/run 竞争、bigint 边界、重连只补后续事件，全部通过公开 API 验证。

## Concrete Steps

在本工作目录执行目标测试，Core 解释器是 `C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe`。
清除本进程 provider keys、关闭 tracing、TEMP 指向 `private/mod-week/tmp`；现有 conftest 禁止 socket。

    python -m pytest tests/v4/streaming/test_codec_coverage_acceptance_mod.py tests/v4/streaming/test_state_coverage_acceptance_mod.py tests/v4/streaming/test_store_coverage_acceptance_mod.py -q

覆盖测量仅运行 `tests/v4/streaming`；不运行全项目，不访问 Q5 B 或校准 75 条材料。
实际覆盖命令和源哈希将写入新 evidence，不覆盖 DAY 原报告。

## Validation and Acceptance

对应 `07_评测场景集.md` 的 X08：重连从合法 Last-Event-ID 后补发；同操作重放、seq 空洞、
相同 run_id 的其他 owner 均不会造成缺失、重复或泄漏。F03 的撤销删除由主线负责，本轮只核对
清理计划不携带正文、不跨 owner/run、不删除 final/reset，不能称为撤销数据库验收。
在 150ms、40 字、15 秒、提交加 24 小时的精确边界，行为遵循冻结契约。
错误时间、无效序号、被篡改的行/外壳和违反状态转移的旧写入者必须受控拒绝。
源码前后身份一致且目标测试通过后，才记录本轮统计；行、分支、综合目标均为 90%。

## Idempotence and Recovery

所有输入为显式合成数据，测试只用进程内对象和注入端口；无数据库或业务状态可回滚。
失败不改真值，保留最小反例交 root；覆盖数据放私有目录，证据写全新文件。

## Artifacts and Notes

计划：本文件。预期新证据位于 `docs/v4/evidence/MOD_2026-10-21/STREAMING_boundary_*`。
原始依据：`docs/v4/evidence/MOD_2026-10-21/DAY_new_code_coverage.json`，只读保留。
最终覆盖证据：`STREAMING_boundary_coverage_20261021.json`，SHA-256
`f694ccef9ade8da4223f7c187bda66718f73b0ccca31583116308db602c25732`。
其中包含实际命令、08:59:39–08:59:43 北京时间、597 项输出、全部 20 文件覆盖与未执行分支、
源及测试/fixture 哈希；本轮没有新增产品接口需要主线接线。

## Interfaces and Dependencies

没有产品接口、数据库结构、依赖锁文件或运行配置变更。仅使用公开流式接口和已有 pytest/coverage。
公开 SSE 不含 owner；host 仍必须在进入存储端口前完成 owner/run 授权。

## 修订记录

- 2026-10-21 08:52 +08:00：创建，冻结新增边界验收范围与证据限制。
- 2026-10-21 09:00 +08:00：记录实际目标与覆盖结果、测试接入修正和剩余未执行分支，完成本轮回执。
- 2026-10-21 09:03 +08:00：静态补充首轮结果事件与独立节点计数差异；测试代码、覆盖报告和真值不变。
