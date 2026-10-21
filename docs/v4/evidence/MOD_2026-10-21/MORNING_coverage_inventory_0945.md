# 新增产品完整覆盖盘点（09:48–09:50北京）

本次分母是启动基底8c554bd之后新增的191份产品Python：mingjing_core及两个纯工具包。
不包含旧基底产品、测试或benchmark工具；所有191文件都入分母，未执行入口不剔除。
27组插桩回归12267通过125.18秒，511快照零漂移，与三轮普通回归快照完全相同。
行10093/10748=93.905843%，分支3408/4008=85.029940%，综合13501/14756=91.494985%。
另有81行按coverage默认规则排除，原JSON保留逐文件excluded_lines数量；没有为本盘点新增排除。
随后只读检查coverage配置文件列表为空，默认包括pragma/类型检查/协议ellipsis，不能将排除行称已经执行。

综合超过90%不表示每个文件达标：57文件低于90%，分支总体也不足90%。
0%的CLI入口保留在分母；Q5冻结产品即使出现在下表，也不能据B回调，B不重开、不读正文。
这不是全仓库/CI、条件覆盖、PG、平台、模型质量或产品接线证明；插桩耗时不作性能收益比较。

公开主报告SHA256：7e77d6c25625361fa37eb61cc0266d79725ff9bac4619a20994bff11ec86359a。
报告含命令、解释器/coverage版本、191产品路径、全部511源SHA、原stdout、逐文件缺行/分支。
报告开始09:48:17.992723+08:00，结束09:50:25.230457+08:00；没有复用主机Tokyo时区。

## 低于90%的文件

以下按综合覆盖从低到高排列。只选真实可达公开输入补测，不用绕过构造器的私有坏态刷分。

| 产品路径 | 综合% | 缺行 | 缺分支 |
| --- | ---: | ---: | ---: |
| tools/eval_material_v23/__main__.py | 0.0000 | 21 | 4 |
| mingjing_core/organize/supplement_v2/legacy_bridge.py | 76.1194 | 8 | 8 |
| mingjing_core/scheduling/recurrence_calendar.py | 77.9412 | 9 | 6 |
| mingjing_core/memory2/mutations.py | 79.1667 | 12 | 13 |
| mingjing_core/application/briefing_v2/calendar.py | 79.3103 | 12 | 12 |
| tools/calibration_v3/models.py | 79.3103 | 10 | 8 |
| mingjing_core/organize/supplement_v2/lifecycle.py | 80.4878 | 12 | 12 |
| tools/eval_material_v23/observe.py | 80.6061 | 16 | 16 |
| mingjing_core/organize/v2/contracts.py | 80.9524 | 8 | 8 |
| mingjing_core/application/briefing_v2/transit.py | 82.1138 | 11 | 11 |
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
| mingjing_core/application/briefing_v2/evidence.py | 84.4156 | 13 | 11 |
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
| mingjing_core/memory2/mutation_contracts.py | 87.3016 | 4 | 4 |
| tools/calibration_v3/daily.py | 87.3684 | 6 | 6 |
| mingjing_core/memory2/consent_text.py | 87.5000 | 1 | 1 |
| mingjing_core/memory2/dedup.py | 87.5000 | 2 | 2 |
| mingjing_core/memory2/plan_builder.py | 87.6106 | 7 | 7 |
| mingjing_core/scheduling/recurrence.py | 87.7551 | 3 | 3 |
| mingjing_core/memory2/contracts.py | 87.7934 | 13 | 13 |
| mingjing_core/timeparse/numerals.py | 87.8788 | 2 | 2 |
| mingjing_core/memory/retrieval_types.py | 88.2353 | 9 | 9 |
| mingjing_core/organize/supplement_v2/guards.py | 88.2353 | 4 | 4 |
| mingjing_core/timeparse/calendar_holidays.py | 88.4058 | 5 | 3 |
| mingjing_core/organize/export_dry_run_v3/preview.py | 88.8889 | 3 | 1 |
| tools/calibration_v3/import_brain.py | 88.8889 | 6 | 4 |
| mingjing_core/application/briefing_v2/items.py | 89.0411 | 4 | 4 |
| mingjing_core/application/reports_v2/contracts.py | 89.2256 | 16 | 16 |
| mingjing_core/timeparse/calendar_helpers.py | 89.2308 | 3 | 4 |
| mingjing_core/adapters/channels/cardkit_official_v3/contracts.py | 89.3023 | 11 | 12 |
| mingjing_core/memory/retrieval.py | 89.5833 | 5 | 5 |
| mingjing_core/scheduling/recurrence_contracts.py | 89.6552 | 6 | 6 |
| mingjing_core/application/reflection_v3/schedule_contracts.py | 89.6774 | 9 | 7 |
| mingjing_core/organize/v2/classifier.py | 89.7590 | 10 | 7 |
| mingjing_core/scheduling/recurrence_civil.py | 89.7959 | 1 | 4 |

## 后续与复跑

下一轮先读记忆变更、调度坏历法端口和晨报来源证据的完整产品与调用方，先冻结独立真值再写测试。
不得将本报告的历史快照误称后续修改后的现行快照。每一轮重新记录源/测试/样例身份。

在原工作目录清除provider keys、关闭追踪，仅于北京45–59分开始全量；使用新private数据/临时/报告路径。
命令从主JSON的command逐项复制，替换data-file及basetemp为新路径；测试目录正是JSON的27项suites。
完成后用同一解释器加载coverage数据，不读取业务正文：

    import coverage, json
    from pathlib import Path
    reference = json.loads(Path('docs/v4/evidence/MOD_2026-10-21/MORNING_completed_coverage_0945.json').read_text(encoding='utf-8'))
    measured = coverage.Coverage(data_file='<本次新private数据路径>')
    measured.load()
    measured.json_report(morfs=reference['product_files'], outfile='<本次新private原始JSON路径>')

对原始totals，以(covered_lines+covered_branches)/(num_statements+num_branches)计算综合；
逐文件保留summary/missing_lines/missing_branches，并将运行前后source_snapshot及实际stdout另存新报告。
路径列表只用于同一冻结分母复跑；新开发扩展分母时需重新从基底A状态产品枚举，不能默默丢未测入口。
