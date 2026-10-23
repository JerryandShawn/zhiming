# 10月23日恢复后的完整离线覆盖盘点

实际复核：2026-10-23T21:01:54+08:00（Asia/Shanghai）。

覆盖启动 2026-10-23T20:57:41.509925+08:00；结束 2026-10-23T21:00:02.224316+08:00，12406通过138.63秒。
与普通三轮（61.15/56.47/54.22秒）在20:57后重叠，最多2个pytest；不比较插桩/普通耗时为性能。
544来源各轮/跨轮/覆盖及本次当前字节完全相同。

192新增产品全部保留分母（175 Core+12校准工具+5素材工具）；未删未执行入口或低分文件。
行10224/10794=94.719288%；分支3489/4026=86.661699%；综合13713/14820=92.530364%。
45文件综合不足90%。81默认排除行、config_files_read=[]、omit=null；总体综合达90不代表每份或分支达标。

覆盖JSON SHA256：`8c79ad570b4f49fb6a7b1bd187e8f4c5c8178bf93dc183582835a40ad936b51e`。
10-21旧12371/532与46不足是历史范围；当时11:45未执行，今天报告不回填过去。

| 新增产品文件 | 行通过/总数 | 分支通过/总数 | 综合% |
| --- | --- | --- | --- |
| mingjing_core/adapters/channels/action_token_refresh_v2.py | 65/71 | 14/20 | 86.813187 |
| mingjing_core/adapters/channels/cardkit_official_v3/contracts.py | 160/171 | 32/44 | 89.302326 |
| mingjing_core/adapters/channels/cardkit_official_v3/transitions.py | 62/69 | 14/22 | 83.516484 |
| mingjing_core/adapters/channels/cardkit_official_v3/validation.py | 95/110 | 73/88 | 84.848485 |
| mingjing_core/adapters/channels/cards_official_v3/answers.py | 42/47 | 17/22 | 85.507246 |
| mingjing_core/adapters/channels/cards_official_v3/budget.py | 21/24 | 9/12 | 83.333333 |
| mingjing_core/adapters/channels/cards_official_v3/elements.py | 25/28 | 7/10 | 84.210526 |
| mingjing_core/adapters/channels/cards_official_v3/notices.py | 31/35 | 6/10 | 82.222222 |
| mingjing_core/adapters/channels/cards_official_v3/validation.py | 77/86 | 35/44 | 86.153846 |
| mingjing_core/adapters/channels/stream_outbox_v2/codec.py | 51/57 | 24/30 | 86.206897 |
| mingjing_core/adapters/channels/stream_outbox_v2/contracts.py | 146/168 | 64/86 | 82.677165 |
| mingjing_core/application/briefing_v2/contracts.py | 137/151 | 24/38 | 85.185185 |
| mingjing_core/application/briefing_v2/items.py | 47/51 | 18/22 | 89.041096 |
| mingjing_core/application/reflection_v3/profile_contracts.py | 96/105 | 21/30 | 86.666667 |
| mingjing_core/application/reflection_v3/schedule_contracts.py | 114/123 | 25/32 | 89.677419 |
| mingjing_core/application/reflection_v3/work_contracts.py | 204/229 | 32/58 | 82.229965 |
| mingjing_core/application/reports_v2/contracts.py | 201/217 | 64/80 | 89.225589 |
| mingjing_core/memory2/consent_text.py | 13/14 | 1/2 | 87.500000 |
| mingjing_core/memory2/contracts.py | 163/175 | 26/38 | 88.732394 |
| mingjing_core/memory2/dedup.py | 20/22 | 8/10 | 87.500000 |
| mingjing_core/memory/retrieval.py | 61/66 | 25/30 | 89.583333 |
| mingjing_core/memory/retrieval_rounds.py | 61/66 | 14/20 | 87.209302 |
| mingjing_core/memory/retrieval_types.py | 102/111 | 33/42 | 88.235294 |
| mingjing_core/organize/export_dry_run_v3/preview.py | 25/28 | 7/8 | 88.888889 |
| mingjing_core/organize/supplement_v2/contracts.py | 124/138 | 20/34 | 83.720930 |
| mingjing_core/organize/supplement_v2/guards.py | 50/54 | 10/14 | 88.235294 |
| mingjing_core/organize/supplement_v2/lifecycle.py | 77/89 | 22/34 | 80.487805 |
| mingjing_core/organize/supplement_v2/projection.py | 91/105 | 46/60 | 83.030303 |
| mingjing_core/organize/v2/classifier.py | 110/120 | 39/46 | 89.759036 |
| mingjing_core/organize/v2/contracts.py | 54/62 | 14/22 | 80.952381 |
| mingjing_core/organize/v2/scoped.py | 32/36 | 12/16 | 84.615385 |
| mingjing_core/scheduling/brief_schedule.py | 26/30 | 6/8 | 84.210526 |
| mingjing_core/timeparse/calendar_helpers.py | 42/45 | 16/20 | 89.230769 |
| mingjing_core/timeparse/calendar_holidays.py | 46/51 | 15/18 | 88.405797 |
| mingjing_core/timeparse/calendar_terms.py | 21/24 | 5/6 | 86.666667 |
| mingjing_core/timeparse/numerals.py | 19/21 | 10/12 | 87.878788 |
| mingjing_core/timeparse/recurrence.py | 42/46 | 13/18 | 85.937500 |
| tools/calibration_v3/batches.py | 80/90 | 20/30 | 83.333333 |
| tools/calibration_v3/blind_payload_contract.py | 24/28 | 18/22 | 84.000000 |
| tools/calibration_v3/critic_records.py | 42/46 | 10/14 | 86.666667 |
| tools/calibration_v3/daily.py | 63/69 | 20/26 | 87.368421 |
| tools/calibration_v3/import_brain.py | 58/64 | 22/26 | 88.888889 |
| tools/calibration_v3/models.py | 55/65 | 14/22 | 79.310345 |
| tools/eval_material_v23/loader.py | 98/115 | 60/72 | 84.491979 |
| tools/eval_material_v23/observe.py | 91/107 | 42/58 | 80.606061 |

## 来源与复跑

实际启动命令、27套件、每文件缺行/缺分支、默认排除与测量脚本SHA均在原JSON。原生coverage meta的无时区诊断时间不作为北京时间门禁，包装器aware时刻为准。
复跑使用原completed_regression.py并指定全新输出；仅北京45–59分启动各轮。覆盖helper为private/mod-week/measure_completed_coverage_recovery_20261023.py，SHA绑定在JSON。
普通三轮JSON SHA256：`f6dcaf3dcf8e9568ba98e41575270b676a32ccfd28ce64a17708aab9b8d47b69`。
当前392新增Python逐项SHA与10-21静态报告一致；这只是字节复核，不称10-23又运行Ruff。

范围仅27个明确离线模块目录，不是全仓库/PG/HTTP/浏览器/平台或真实模型质量验收；B不重开，人工0/critic0/record_only保持。
