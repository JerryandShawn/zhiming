# P2 白天组合回归（2026-10-18）

P1 合并基底：`7b45a781921e6fa2e875319a12af433f0cf505b4`。P2 最后代码提交：`75cbeb7b0d834bbc22550625500bfc7ee5261163`；发布时采用等价 Git tree，最终远端提交与CI链接见 PR #4/每日汇总。旧 P2 头 `2afd389` 已留恢复引用；只重写本阶段独占分支，不强推 v4/main。

| 检查 | 实际结果 |
| --- | --- |
| 旧 Core `python -m unittest discover -s tests -p 'test_core*.py' -v` | 553/553，705.625s，退出0 |
| 全部 v4 `python -m pytest tests/v4 -q --tb=short` | 615/615，163.14s，零跳过；一项上游anyio别名弃用告警 |
| 模型/评测 `coverage run --source=mingjing_core.models -m pytest tests/v4/models -q` | 208/208，62.59s；700/737语句，约95%，与P1相同 |
| 原脚本 `runner.py --mode scripted --target fake --self-test` | 80/80，框架48/48，10.31s；真实请求0 |
| 新组合 `pytest tests/v4/foundation -q` | 28/28，11.24s；真实PG、真实服务/LangGraph/供应商parser，仅HTTP替身 |
| 静态 | 35现代文件Ruff E/F/I/B/UP/SIM及format120通过；旧consultation的F821与git diff --check通过 |
| 哈希锁 | Core/Test精确版本require-hashes校验64包，P2环境仅补coverage7.11.0；Core/Charts隔离 |

测试限本机 PostgreSQL15.19/core_test_main/127.0.0.1:55480，模型凭据清空，追踪关闭，Charts只读独立解释器。Core源在完整检查开始前已固定；检查父进程退出码被独立观察为0，日志最后553/OK。原始输出在task/work/daytime下，公开证据仅计数/摘要；不复制数据库或正文。

组合用例覆盖：成功/网络/两类公开额度诊断、业务时刻在同一事务提交或异常回滚；取消/过期/token/epoch之后拒绝写入；修复身份/预算不重开；元数据不增语义revision；HTTP晚到repair保留started/unknown诊断及恰一次真实charge。相同token但新epoch的诊断原来能写入，已真实复现后补权威epoch检查。

单测隔离变更仅将未跟踪源码冻结测试ROOT置于tmp_path；原“未提交执行源拒绝”和“P2不可用于旧v3基线”的保护均保留。UTC元数据断言比较正确归一化时刻，未更改生产时钟行为。

锁重生成使用官方精确版本PyPI JSON SHA256，无升级。Test七包230个artifact哈希，coverage92条，旧六包哈希完整保留。Test锁SHA256 `4a60e429d5e2d7f616257e2624d1b5a7456191becb17d472bdb48a733ce2357a`。

首次测试库中断导致25个fixture连接失败，不记通过；恢复正确主线集群后重跑。另一次v4运行载入了尚在修改的新epoch测试，612通过/3失败；最终固定测试边界后615全通过，上表仅最终结果。没有删除旧断言、跳过测试或把这些失败归为通过。

17/18/19十份原设计、22/P5b两份原设计分别独立提交，共12文件逐字节等于源目录，证明见design-supplements-sync-2026-10-18.json。P5b仅同步与后续计划，未实现A/C，也未修改前端/命理保护目录。

真实模型比较、等价性探针、stage、生产与真实飞书均未执行。最新用户要求每个E1/E2批次明确“开始”、每批≤10、夜间零真实请求；原无人值守入口已禁用。主模型/评审目标k3-256k在P1b按授权探针验证后接入，不把P0 k3成绩直接相减。
