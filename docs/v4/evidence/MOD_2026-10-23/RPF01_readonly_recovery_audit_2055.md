# RPF01 guarded 性能材料：恢复后独立只读审计

- 任务标签：2055；实际初次观察为`2026-10-23T20:56:37.102137+08:00`，本次完成复核时刻为`2026-10-23T20:59:34.525232+08:00`。
- 所有记录按Asia/Shanghai真实+08时刻；不使用旧任务日期或宿主时区推断运行时间。
- 只读核对四份10月21日材料、其private原件/日志及指定来源字节；本轮唯一新增文件即本审计。
- 没有运行性能、pytest、coverage、Git、服务器、PG、网络、模型或通知；未读取B及private75正文。

## 恢复结论与时间边界

只读复核通过，没有发现四份材料损坏、当前来源/测试漂移、换行谱系或六组统计不一致。
原性能真实发生于`2026-10-21T11:29:36.185421+08:00`至`2026-10-21T11:29:59.211580+08:00`，报告observed_at为`2026-10-21T11:29:59.116506+08:00`。
本日只做恢复审计，未产生新的性能样本，也未把旧报告时间改为今天。

root恢复核对明确说明：10月21日11:45全量没有执行，相关建议只是历史计划；不得以旧回执建议当成实际执行证据。
额度中断至10月23日之间不补写持续开发、推送或测试记录。本审计不声称跨两日持续作业。
本日新27组三轮/coverage由root另行执行与出报告，不属于本审计的通过结论。

## 四份冻结材料身份

| 当前路径 | 当前SHA-256（与10月21日冻结一致） |
| --- | --- |
| `docs/v4/execplans/MOD_RPF01_guarded_measurement_20261021.md` | `d253f04283a0f49a582f4dd792f18a1e44de03ab85c6ba736c383691cb7d9307` |
| `docs/v4/evidence/MOD_2026-10-21/RPF01_guarded_performance_20261021.json` | `dfd89ec3216ea6240fc6e46ff37ee34f3783bba115863c25e15b66256b9a9cf6` |
| `docs/v4/evidence/MOD_2026-10-21/RPF01_guarded_performance_lineage_20261021.json` | `d451be193eeea5596efefdd1db5f100945466a697a811ce3ca606ebdc0a1c090` |
| `docs/v4/evidence/MOD_2026-10-21/RPF01_guarded_measurement_receipt_20261021.md` | `5f6411c10ebdcde03404c593ce26473a13ed2a0fcf51127793dd1712a562ae95` |

四份公开文件均无CR字节，仍为LF；没有修改既有计划、回执、lineage或性能报告。

## 原件、公开副本及换行

- 原件：`private/mod-week/RPF01_guarded_20261021_1127.raw.json`；SHA`f8dddbb4c5e654f0848adf80096964e5827bd03987c2233864024b169596f2e9`，真实CRLF共430处。
- 公开副本：`docs/v4/evidence/MOD_2026-10-21/RPF01_guarded_performance_20261021.json`；SHA`dfd89ec3216ea6240fc6e46ff37ee34f3783bba115863c25e15b66256b9a9cf6`，无CR字节。
- 重新逐字节确认`raw.replace(CRLF, LF) == public`，且`public.replace(LF, CRLF) == raw`。
- 两份JSON对象重新解析后完全相等，内容/字段/数值没有因规范换行改变。
- 原stdout/stderr日志SHA`b54d3ab89f86e826258826136e29d6fb6418f94d6801cf6007dd693249c570c5`已与当前private日志核对一致。
- 更旧最终身份时区报告仍为SHA`4d2e89e15144dbe557a6eb07b06fc2d167fca5d65a10e8902ec73c77225d4011`，没有给旧数字换新工具身份。

## 当前288来源与239测试

- lineage的source_sha256_before与after相同，当前逐一重新计算288/288匹配，漂移为空。
- 288由当前284份Core Python及工具自身、benchmark_reflection_v3.py、performance.py、固定合成fixture四份构成。
- 当前Core Python路径集合恰为原284份，没有新增/缺失；未调用runner.source_snapshot或其Git清单。
- 只核Core `.py`与已固定synthetic，不遍历未知JSON、B或private校准材料。
- guarded工具当前SHA`3878721ba37c645cd48924973c756931ac65232f4036351b77b81fcb71393e2d`吻合，三直接依赖及3实验产品/18反思产品逐项吻合。
- 当前239份tests/v4 Python树SHA`08367bc592ac144992e5d76eff7b3854435df35c30f6b6f4bb364907c1ba94d8`，与lineage记录的前后两份树SHA均一致。
- 测试树口径为相对路径→原始字节SHA的映射，UTF-8 json.dumps(sort_keys=True,separators=(",", ":"))后再SHA-256；没有导入或执行这些测试。
- 环境工具completed_regression.py的当前SHA也与历史lineage一致；本次没有修改或运行它。

## 六组历史数据复核

| 冻结工作量 | 每次单位数 | 五样本中位墙钟秒 | 单独Python分配峰bytes |
| --- | --- | --- | --- |
| oracle_projection_and_digest_400 | 400 | 0.129792500 | 252736 |
| candidate_projection_and_digest_400 | 400 | 0.044431400 | 124238 |
| oracle_full_enqueue_work_aboutme_100 | 100 | 0.614113000 | 306066 |
| candidate_full_enqueue_work_aboutme_100 | 100 | 0.526049700 | 244696 |
| oracle_revoked_epoch_invalidation_1000 | 1000 | 0.386750500 | 45263 |
| candidate_revoked_epoch_invalidation_1000 | 1000 | 0.376721400 | 43419 |

六组名/顺序及单位数400/400/100/100/1000/1000保持；每组1预热、5个有限正值样本和独立tracemalloc峰。
逐组median/max重新计算吻合；候选/原版墙钟与分配峰三个比率也重新计算吻合，没有重采样。
候选/原版墙钟比为0.3423264056、0.8566008210、0.9740682947，不能据此宣称统计显著。

原语义fingerprint`dd83e380ac300e931f0a0cc3aa8ee9ff8fc78488ed42d468865f10b8bac66387`与lineage一致；最终别名恢复、来源集合/字节稳定字段均为true。
这些是原测量的历史守卫结果，当前只核其材料和源身份，不假称再次执行了assert_parity或模式探针。

## 测量解释与未验证范围

performance.py原limitations保留“CPU wall time”字样，但实现使用perf_counter，属于elapsed墙钟，非CPU-time采样。
lineage/回执对此已有明确说明，本审计不改原报告内容以粉饰措辞。
固定顺序单机5样本没有随机顺序或置信区间，缓存/调度仍可影响比率；Python tracemalloc峰不是RSS。
局部400投影计时外准备corpus，不能代表完整链时延。完整100反思链包含原fixture解码、输入构造、guard/assert；
导入、fixture初读、hash、parity证明和证据写入不在其workload计时内。

候选仅支持22种精确类型、字符串键、深度<=64，未知类/子类拒绝，未接主运行入口。
本恢复审计不证明真实用户批准、PG事务、部署、平台、模型或产品质量；历史性能仍是有限离线观测。
现有未提交/CI/HEAD状态由root另行核对；本审计没有Git权限操作，不以文件哈希代替提交或CI结果。

## 冻结交接

结论可供root纳入恢复材料。仅新增本文件，不修改四份原材料、raw原件、工具、产品、fixture或测试。
若后续root变更来源或测试，必须使用新的观测/审计身份，不能将本报告的288/239证明直接延伸为新状态。
