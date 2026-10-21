# 新增产品完整覆盖盘点（10:48–10:51北京）

本次分母为启动基底8c554bd之后新增的192份产品Python：mingjing_core及两个纯工具包。
比09:48历史盘点增加briefing_v2/current_manifest.py一份，没有移除旧分母；测试和benchmark工具不在产品分母。
27组插桩回归12371通过132.24秒；532份来源快照无漂移，与10:45开始的三轮普通回归完全相同。
行10210/10791=94.615884%，分支3478/4024=86.431412%，综合13688/14815=92.392845%。
81行按coverage默认规则排除；实际config_files_read=[]、omit=null，默认排除规则原文在JSON中，没有新增加排除。

仍有46文件综合不足90%，分支总体不足90%；不把整体高于90%当逐文件达标。
缺失行/分支用于寻找可达公开边界，禁止绕过合法构造器制造私有坏态，也不允许重开Q5的B集。
这是本轮新增产品和27组离线测试的覆盖，不能证明全仓库、实际接线、PG、平台、模型质量或部署。
插桩耗时不是性能收益；CLI干净子进程的main guard真分支不并入parent覆盖，不人为补成100%。

公开主报告SHA256：5481293bb241147555e09eb33d4444a2b5aae0ce1c307469b58245b3b8f3d241。
实际开始2026-10-21T10:48:50.345185+08:00，结束2026-10-21T10:51:04.697033+08:00；明确Asia/Shanghai，不复用主机Tokyo时区。

## 低于90%的文件

| 产品路径 | 综合% | 缺行 | 缺分支 |
| --- | ---: | ---: | ---: |
| mingjing_core/organize/supplement_v2/legacy_bridge.py | 76.1194 | 8 | 8 |
| tools/calibration_v3/models.py | 79.3103 | 10 | 8 |
| mingjing_core/organize/supplement_v2/lifecycle.py | 80.4878 | 12 | 12 |
| tools/eval_material_v23/observe.py | 80.6061 | 16 | 16 |
| mingjing_core/organize/v2/contracts.py | 80.9524 | 8 | 8 |
| mingjing_core/adapters/channels/cards_official_v3/notices.py | 82.2222 | 4 | 4 |
| mingjing_core/application/reflection_v3/work_contracts.py | 82.2300 | 25 | 26 |
| mingjing_core/adapters/channels/action_token_refresh_v2.py | 82.4176 | 9 | 7 |
| mingjing_core/adapters/channels/stream_outbox_v2/contracts.py | 82.6772 | 22 | 22 |
| mingjing_core/organize/supplement_v2/projection.py | 83.0303 | 14 | 14 |
| mingjing_core/adapters/channels/cards_official_v3/budget.py | 83.3333 | 3 | 3 |
| tools/calibration_v3/batches.py | 83.3333 | 10 | 10 |
| mingjing_core/adapters/channels/cardkit_official_v3/transitions.py | 83.5165 | 7 | 8 |
| mingjing_core/organize/supplement_v2/contracts.py | 83.7209 | 14 | 14 |
| tools/calibration_v3/blind_payload_contract.py | 84.0000 | 4 | 4 |
| mingjing_core/adapters/channels/cards_official_v3/elements.py | 84.2105 | 3 | 3 |
| mingjing_core/scheduling/brief_schedule.py | 84.2105 | 4 | 2 |
| tools/eval_material_v23/loader.py | 84.4920 | 17 | 12 |
| mingjing_core/organize/v2/scoped.py | 84.6154 | 4 | 4 |
| mingjing_core/adapters/channels/cardkit_official_v3/validation.py | 84.8485 | 15 | 15 |
| mingjing_core/application/briefing_v2/contracts.py | 85.1852 | 14 | 14 |
| mingjing_core/adapters/channels/cards_official_v3/answers.py | 85.5072 | 5 | 5 |
| mingjing_core/timeparse/recurrence.py | 85.9375 | 4 | 5 |
| mingjing_core/adapters/channels/cards_official_v3/validation.py | 86.1538 | 9 | 9 |
| mingjing_core/adapters/channels/stream_outbox_v2/codec.py | 86.2069 | 6 | 6 |
| mingjing_core/application/reflection_v3/profile_contracts.py | 86.6667 | 9 | 9 |
| mingjing_core/timeparse/calendar_terms.py | 86.6667 | 3 | 1 |
| tools/calibration_v3/critic_records.py | 86.6667 | 4 | 4 |
| mingjing_core/memory/retrieval_rounds.py | 87.2093 | 5 | 6 |
| tools/calibration_v3/daily.py | 87.3684 | 6 | 6 |
| mingjing_core/memory2/consent_text.py | 87.5000 | 1 | 1 |
| mingjing_core/memory2/dedup.py | 87.5000 | 2 | 2 |
| mingjing_core/timeparse/numerals.py | 87.8788 | 2 | 2 |
| mingjing_core/memory/retrieval_types.py | 88.2353 | 9 | 9 |
| mingjing_core/organize/supplement_v2/guards.py | 88.2353 | 4 | 4 |
| mingjing_core/timeparse/calendar_holidays.py | 88.4058 | 5 | 3 |
| mingjing_core/memory2/contracts.py | 88.7324 | 12 | 12 |
| mingjing_core/organize/export_dry_run_v3/preview.py | 88.8889 | 3 | 1 |
| tools/calibration_v3/import_brain.py | 88.8889 | 6 | 4 |
| mingjing_core/application/briefing_v2/items.py | 89.0411 | 4 | 4 |
| mingjing_core/application/reports_v2/contracts.py | 89.2256 | 16 | 16 |
| mingjing_core/timeparse/calendar_helpers.py | 89.2308 | 3 | 4 |
| mingjing_core/adapters/channels/cardkit_official_v3/contracts.py | 89.3023 | 11 | 12 |
| mingjing_core/memory/retrieval.py | 89.5833 | 5 | 5 |
| mingjing_core/application/reflection_v3/schedule_contracts.py | 89.6774 | 9 | 7 |
| mingjing_core/organize/v2/classifier.py | 89.7590 | 10 | 7 |

## 复跑方法

使用锁定Core Python3.11和coverage7.11；清provider key、关闭tracing，临时数据和原始coverage数据放本树private。
全部产品/测试/合成输入冻结；仅在北京时间45–59分启动完整回归，使用新路径，不覆盖原证据。

    python tools/mod_week/completed_regression.py --output <新的本树报告路径> --rounds 3
    python -m coverage run --branch --data-file=<private下新路径> --source=mingjing_core,tools/calibration_v3,tools/eval_material_v23 -m pytest <报告suites所列27个目录> -q --basetemp=<private下新目录>

产品列表来自git diff --name-status 8c554bd，只选A且为mingjing_core或两个纯工具包的.py；
加载coverage数据后json_report(morfs=上述产品列表)，保留未执行文件。主报告包含精确命令、全部产品列表、
532份source_files、逐文件缺行/缺分支、解释器与coverage版本以及实际配置，重复后须重新核来源漂移。

旧MORNING_completed_coverage_0945.json与57不足列表原样保留，只代表当时191产品和12267测试。
旧消息桥的15项新预期现在只冻结为文档，没有执行，也不进入本次12371；下一续作另行实施。
