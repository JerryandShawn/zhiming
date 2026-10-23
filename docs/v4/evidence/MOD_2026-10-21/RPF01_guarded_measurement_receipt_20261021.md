# RPF01守卫版本重观测阶段回执

- 分支/最后提交/PR：由root统一管理，本子任务无Git，不声称新提交/CI状态。
- ExecPlan：`docs/v4/execplans/MOD_RPF01_guarded_measurement_20261021.md`。
- 真实开始/结束：`2026-10-21T11:29:36.185421+08:00` / `2026-10-21T11:29:59.211580+08:00`（北京时间）。

## 完成了什么

- [x] 先建计划并预核输出为本树private新路径，再使用普通Core Python -B运行冻结工具。
- [x] 6组原工作量、固定顺序、每组1预热5墙钟样本及单独tracemalloc均不改。
- [x] 原网络阻断/parity/alias恢复与源身份断言保留；最终exit0才发布，未把中间对象当报告。
- [x] 288来源（284Core+4工具/依赖/固定synthetic）及239测试Python前后稳定，3实验产品与18反思源不变。
- [x] raw CRLF保留，仅换行发布LF；两文件JSON全等、LF→CRLF可逆还原原SHA。
- [x] 新lineage记录真实时刻、命令、工具/依赖/源hash、raw/public SHA及口径限制；旧报告完全不改。

## 评测分数

不是测试/覆盖/模型评测。本轮测量通过原语义与身份守卫；没有pytest或额外性能重跑。
原/候选parity `dd83e380ac300e931f0a0cc3aa8ee9ff8fc78488ed42d468865f10b8bac66387`，4别名已恢复。该语义fingerprint与旧最终报告一致。

| 固定工作量 | 中位墙钟秒 | 单独Python分配峰bytes |
| --- | --- | --- |
| oracle_projection_and_digest_400 | 0.129792500 | 252736 |
| candidate_projection_and_digest_400 | 0.044431400 | 124238 |
| oracle_full_enqueue_work_aboutme_100 | 0.614113000 | 306066 |
| candidate_full_enqueue_work_aboutme_100 | 0.526049700 | 244696 |
| oracle_revoked_epoch_invalidation_1000 | 0.386750500 | 45263 |
| candidate_revoked_epoch_invalidation_1000 | 0.376721400 | 43419 |

候选/原版墙钟比依次为局部400投影0.3423264056、100条完整反思链0.8566008210、1000撤源0.9740682947。
原始5样本逐值见新性能JSON；这里不把固定顺序单机比率当统计显著性或普遍收益。
局部400投影在计时外准备corpus，不可冒充完整链时延；100链包含原fixture解码/输入构造/guard/assert。

## 改了哪些关键文件

仅新增本ExecPlan、新LF报告、新lineage及本回执。原工具、3实验产品、18反思源、所有fixture/测试与旧perf均未改。

| 原件 | SHA-256 |
| --- | --- |
| guarded工具 | `3878721ba37c645cd48924973c756931ac65232f4036351b77b81fcb71393e2d` |
| `private/mod-week/RPF01_guarded_20261021_1127.raw.json` | `f8dddbb4c5e654f0848adf80096964e5827bd03987c2233864024b169596f2e9` |
| 新公开LF报告 | `dfd89ec3216ea6240fc6e46ff37ee34f3783bba115863c25e15b66256b9a9cf6` |
| 新lineage | `d451be193eeea5596efefdd1db5f100945466a697a811ce3ca606ebdc0a1c090` |
| 原始stdout/stderr LF日志 | `b54d3ab89f86e826258826136e29d6fb6418f94d6801cf6007dd693249c570c5` |
| 旧最终身份时区报告（保留） | `4d2e89e15144dbe557a6eb07b06fc2d167fca5d65a10e8902ec73c77225d4011` |

真实来源数明确288，逐项在lineage两份来源映射中；另239测试Python树SHA独立记录。
新公开报告为`RPF01_guarded_performance_20261021.json`，lineage为`RPF01_guarded_performance_lineage_20261021.json`。
private原始CRLF有430处实际换行，原件与公开对象全等且字节逆变换已验证。

## 数据库迁移与回滚方式

无DB、迁移、实际apply、服务/入口注册、通知或业务删除。实验只在单个独立进程切换四别名，finally恢复。
原private raw、stdout日志和旧perf保留不删；冻结后不重写数据。

## 偏离设计的地方

无新优化或参数调整。原performance.py原句“CPU wall time”只是历史措辞；实际perf_counter观测elapsed wall time，非CPU-time采样。
公开性能JSON不修改该原句，以保持只规范换行的可逆谱系；lineage与本回执明确纠正解释。

## 未验证 / 已知风险

固定顺序、单机5样本，无置信区间/随机顺序控制，缓存与系统调度可影响结果。
tracemalloc峰是Python分配，非RSS/完整进程内存。有限22精确类型、未知/子类拒绝，未接主运行入口。
导入、fixture初读、source hashes、parity证明和证据写入不在workload计时中。
不把这次与旧工具版本直接比较成新优化收益，不宣称真实PG/用户数据/业务链或生产效果。
模型、网络、服务器、PG、通知、Git、产品/测试/fixture编辑均0；未读B或私有75正文。

## 需要用户或大脑决定的问题

无。是否未来接线由主线/大脑另决；本轮只完成被授权的冻结工具重观测。

## 建议后续

由root独立核新报告/lineage SHA后统一提交，11:45回归仍使用其冻结清单。
本任务立即冻结；不因观察到比率变化改产品、参数或原测试。
