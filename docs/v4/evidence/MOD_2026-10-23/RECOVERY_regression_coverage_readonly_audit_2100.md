# 恢复后27组三轮及192产品覆盖：独立只读审计

- 任务标签2100；实际首次观察`2026-10-23T21:00:39.567459+08:00`，完成核对时刻`2026-10-23T21:04:35.109116+08:00`（Asia/Shanghai）。
- 只读解析两份新报告、原始coverage数字、测量脚本及来源字节；本轮没有运行测试、覆盖、性能或Git。
- 唯一新增文件为本审计；不修改代码、工具、测试、fixture、旧报告或任何既有文档，不读B/private75正文。

## 结论与原件身份

审计通过，没有发现失败、来源漂移、分母选择差异或覆盖数学不一致。
这是本地离线回归/覆盖的材料核对，不等于产品、真实PG、CI、平台、部署或模型质量验收。

| 原件 | SHA-256 |
| --- | --- |
| RECOVERY_completed_regression_2055.json | `f6dcaf3dcf8e9568ba98e41575270b676a32ccfd28ce64a17708aab9b8d47b69` |
| RECOVERY_completed_coverage_2055.json | `8c79ad570b4f49fb6a7b1bd187e8f4c5c8178bf93dc183582835a40ad936b51e` |
| 原生private coverage JSON | `c37ab6f7b0afbc852f3e4a9991cf6c07bba13fa1a7ad2e7d6f34ed13c6519c63` |
| private一次性测量脚本 | `ed2f6d8fe813effe800a286dbcf62294eba9be9f25e6ba5aef66ad5e467d1581` |

公开报告均UTF-8 LF无CR。原生coverage JSON及测量脚本当前SHA均与报告一致；逐文件summary/missing_lines/missing_branches及totals与原生JSON完全吻合。

## 三轮真实时间、结果及并发

| 轮次 | 实际+08开始 | 实际+08结束 | 原pytest摘要 |
| --- | --- | --- | --- |
| 1 | 2026-10-23T20:56:33.781792+08:00 | 2026-10-23T20:57:39.621594+08:00 | 12406 passed in 61.15s (0:01:01) |
| 2 | 2026-10-23T20:57:39.705411+08:00 | 2026-10-23T20:58:37.806279+08:00 | 12406 passed in 56.47s |
| 3 | 2026-10-23T20:58:37.867279+08:00 | 2026-10-23T20:59:33.640196+08:00 | 12406 passed in 54.22s |

- 三轮普通回归顺序无重叠，各12406通过，两个exit字段都0，stderr均空，source_drift均空。
- 三个真实启动分钟56/57/58均处45–59窗口；按显式+08时刻判断，没有沿用旧日期或系统无时区时间。
- coverage实际`2026-10-23T20:57:41.509925+08:00`至`2026-10-23T21:00:02.224316+08:00`，启动57分合法；跨整点结束不违反启动窗口。
- coverage原pytest结果`12406 passed in 138.63s (0:02:18)`，exit0、stderr空、source_drift空。
- 由这四个开始/结束区间计算，记录内测量并发峰值2：coverage与普通后两轮有重叠，普通三轮彼此顺序。
- 这是四条记录的区间核对，不声称审计了全系统所有进程；本子任务未增加测量进程。
- 普通/插桩结果分开保存，12406不能相加成不同场景数。上述耗时受并发、插桩、启动及调度影响，均不能当性能或与旧性能报告比较收益。

## 544份来源、当前身份及测试范围

- 三轮及coverage四份source_files集合和每个SHA完全一致；当前逐路径重新读取544/544原始字节均匹配。
- 三轮各自与跨轮漂移为空，coverage同源；所有Core与27组现行非__pycache__ Python均已绑定，未发现漏入的现行Python路径。
- 共享映射锚为`225eeca625a51bc95f81b0ceae804b3032a0344ae2a2649485e881e0be6ebe36`，算法是UTF-8 json.dumps(source_files,sort_keys=True,separators=(",", ":"))后SHA-256。
- 27组名单与10月21日10:45历史报告一致；本次12406相对历史12371增加35，不回写旧报告冒充已包含后补。
- 新增六份明确材料（旧桥15矩阵/5矩阵及各synthetic，K3矩阵及synthetic）均在544账本中；旧10固定契约材料保留。
- 这些名字来自明确固定清单，不扫描B或private75/未知JSON；本审计没有运行带Git的source_snapshot。
- 10月21日11:45未执行，不能把本日真实运行补作其当时已执行；缺失期间不补写持续开发或成功记录。
- root尚待解冻的下一批测试不据本报告提前宣布通过；后续改动需要新的身份/验证证据。

## 192个产品分母与统计重算

192个唯一路径由175个本轮新增Core Python、12个calibration_v3纯工具及5个eval_material_v23纯工具组成。
product_files与files集合完全相等，192份均绑定当前544来源；分母路径集合与10月21日MIDDAY192完全相同，无删文件抬分。
测量脚本静态按基底`8c554bd4af6788b3a4d98b9dd0d7618c591f7cfd`的新增A路径及3个固定前缀筛选；本审计未重新执行Git diff。
基底已有产品、测试、benchmark和其余工具不在这192路径分母中；不是全仓库覆盖。
两个零语句__init__保留为文件数量，语句与分支权重均为0。

| 口径 | 已覆盖 / 分母 | 独立重算百分比 |
| --- | --- | --- |
| 行 | 10224 / 10794 | 94.7192884936% |
| 分支 | 3489 / 4026 | 86.6616989568% |
| 综合 | (10224+3489)/(10794+4026) = 13713/14820 | 92.5303643725% |

- 192份summary相加逐字段吻合totals；每份covered+missing等于对应分母，缺行/缺分支数组长度与计数一致，所有文件percent_covered重算正确。
- 缺失570行、537分支；525为partial branches原生计数，不能误作全部missing分支。
- 不足90%的文件数：行23（语句分母非零）、分支76（分支分母非零）、综合45。
- 总综合超过90不等于分支达到90或每个文件达标；旧191/57、MIDDAY192/46均保持历史，不覆盖改写成本次192/45。
- coverage7.11.0 branch=true；config_files_read空、omit=None，保留默认pragma no cover/ellipsis/TYPE_CHECKING及pragma no branch规则。
- excluded_lines=81为原生排除行，未临时增加exclude/omit；这些行不计10794分母，不声称执行过。

## 综合不足90%的45份文件

完整192份逐文件缺失行号/分支端点保留在原coverage JSON；下表列出本次不足文件及真实缺失数量，便于后续择有意义的公开边界。

| 文件 | missing行 | missing分支 | 综合覆盖 |
| --- | --- | --- | --- |
| `mingjing_core/adapters/channels/action_token_refresh_v2.py` | 6 | 6 | 86.81319% |
| `mingjing_core/adapters/channels/cardkit_official_v3/contracts.py` | 11 | 12 | 89.30233% |
| `mingjing_core/adapters/channels/cardkit_official_v3/transitions.py` | 7 | 8 | 83.51648% |
| `mingjing_core/adapters/channels/cardkit_official_v3/validation.py` | 15 | 15 | 84.84848% |
| `mingjing_core/adapters/channels/cards_official_v3/answers.py` | 5 | 5 | 85.50725% |
| `mingjing_core/adapters/channels/cards_official_v3/budget.py` | 3 | 3 | 83.33333% |
| `mingjing_core/adapters/channels/cards_official_v3/elements.py` | 3 | 3 | 84.21053% |
| `mingjing_core/adapters/channels/cards_official_v3/notices.py` | 4 | 4 | 82.22222% |
| `mingjing_core/adapters/channels/cards_official_v3/validation.py` | 9 | 9 | 86.15385% |
| `mingjing_core/adapters/channels/stream_outbox_v2/codec.py` | 6 | 6 | 86.20690% |
| `mingjing_core/adapters/channels/stream_outbox_v2/contracts.py` | 22 | 22 | 82.67717% |
| `mingjing_core/application/briefing_v2/contracts.py` | 14 | 14 | 85.18519% |
| `mingjing_core/application/briefing_v2/items.py` | 4 | 4 | 89.04110% |
| `mingjing_core/application/reflection_v3/profile_contracts.py` | 9 | 9 | 86.66667% |
| `mingjing_core/application/reflection_v3/schedule_contracts.py` | 9 | 7 | 89.67742% |
| `mingjing_core/application/reflection_v3/work_contracts.py` | 25 | 26 | 82.22997% |
| `mingjing_core/application/reports_v2/contracts.py` | 16 | 16 | 89.22559% |
| `mingjing_core/memory2/consent_text.py` | 1 | 1 | 87.50000% |
| `mingjing_core/memory2/contracts.py` | 12 | 12 | 88.73239% |
| `mingjing_core/memory2/dedup.py` | 2 | 2 | 87.50000% |
| `mingjing_core/memory/retrieval.py` | 5 | 5 | 89.58333% |
| `mingjing_core/memory/retrieval_rounds.py` | 5 | 6 | 87.20930% |
| `mingjing_core/memory/retrieval_types.py` | 9 | 9 | 88.23529% |
| `mingjing_core/organize/export_dry_run_v3/preview.py` | 3 | 1 | 88.88889% |
| `mingjing_core/organize/supplement_v2/contracts.py` | 14 | 14 | 83.72093% |
| `mingjing_core/organize/supplement_v2/guards.py` | 4 | 4 | 88.23529% |
| `mingjing_core/organize/supplement_v2/lifecycle.py` | 12 | 12 | 80.48780% |
| `mingjing_core/organize/supplement_v2/projection.py` | 14 | 14 | 83.03030% |
| `mingjing_core/organize/v2/classifier.py` | 10 | 7 | 89.75904% |
| `mingjing_core/organize/v2/contracts.py` | 8 | 8 | 80.95238% |
| `mingjing_core/organize/v2/scoped.py` | 4 | 4 | 84.61538% |
| `mingjing_core/scheduling/brief_schedule.py` | 4 | 2 | 84.21053% |
| `mingjing_core/timeparse/calendar_helpers.py` | 3 | 4 | 89.23077% |
| `mingjing_core/timeparse/calendar_holidays.py` | 5 | 3 | 88.40580% |
| `mingjing_core/timeparse/calendar_terms.py` | 3 | 1 | 86.66667% |
| `mingjing_core/timeparse/numerals.py` | 2 | 2 | 87.87879% |
| `mingjing_core/timeparse/recurrence.py` | 4 | 5 | 85.93750% |
| `tools/calibration_v3/batches.py` | 10 | 10 | 83.33333% |
| `tools/calibration_v3/blind_payload_contract.py` | 4 | 4 | 84.00000% |
| `tools/calibration_v3/critic_records.py` | 4 | 4 | 86.66667% |
| `tools/calibration_v3/daily.py` | 6 | 6 | 87.36842% |
| `tools/calibration_v3/import_brain.py` | 6 | 4 | 88.88889% |
| `tools/calibration_v3/models.py` | 10 | 8 | 79.31034% |
| `tools/eval_material_v23/loader.py` | 17 | 12 | 84.49198% |
| `tools/eval_material_v23/observe.py` | 16 | 16 | 80.60606% |

## 范围与交接限制

来源相同与覆盖数据一致不能认证真实业务/PG当前授权或模型结论；本审计不触碰真实数据、服务、渠道或平台。
只读核对在本时刻有效；后续解冻测试/产品后需由root按新的source map验证，不将本账本延伸到未验证状态。
本审计不报告Git提交、CI或远端状态，相关发布由root独立处理。
