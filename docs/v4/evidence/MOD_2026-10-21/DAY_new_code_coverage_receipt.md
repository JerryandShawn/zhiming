# DAY 新增产品覆盖测量回执

- 北京时间：2026-10-21 01:54:12.571887 → 01:55:27.902057；开始处于 45–59 分窗口。
- 一次插桩运行：19 个明确离线套件，9085 passed in 73.45s。与三遍未插桩的 9102 项稳定性回归分别记录。
- 明确排除 `tests/v4/organize_v2/test_blind_protocol_mod.py` 的 17 项协议测试，属保守少测；不声称该文件读取真实盲评 B。
- 新增产品范围：相对 `8c554bd`、Git diff `--diff-filter=A` 筛选的 119 个 `mingjing_core/**/*.py`；报告成员完全一致。
- 源码与测试快照：运行前后均 334 文件，逐文件完全一致，无漂移。
- 快照 SHA256：`716cbd8936a845d1fe08406fc5e340219179754eda04e8ccd530c2baa4f9384a`。
- 行覆盖：6172/6708 = 92.0095%；分支覆盖：1944/2428 = 80.0659%；合并：8116/9136 = 88.8354%。
- 缺失 536 行、484 分支，51 个文件合并覆盖低于 90%；尚未达到 90% 合并覆盖。
- JSON 保留每文件 `missing_lines`、`missing_branches`、`executed_branches`，没有为提高覆盖而改产品或盲评。

## 原始命令

```text
C:\Users\Administrator\Documents\Codex\zhiming-v4-p2\.venv-core\Scripts\python.exe -m coverage run --rcfile=C:\Users\Administrator\Documents\Codex\zhiming-v4-mod\private\mod-week\coverage-20261021-015412.ini --branch --source=mingjing_core --data-file=C:\Users\Administrator\Documents\Codex\zhiming-v4-mod\private\mod-week\coverage-20261021-015412.data -m pytest tests/v4/organize tests/v4/validation tests/v4/followups_mod tests/v4/cards_mod tests/v4/mod_tools tests/v4/mod_week tests/v4/timeparse tests/v4/memory2 tests/v4/streaming tests/v4/scheduling tests/v4/organize_v2 tests/v4/p9_v2 tests/v4/timeparse_extended tests/v4/cross_modules tests/v4/briefing_v2 tests/v4/organize_supplement tests/v4/organize_supplement_v2 tests/v4/partition_context_v2 tests/v4/day_pipeline -q --ignore=tests/v4/organize_v2/test_blind_protocol_mod.py --basetemp=C:\Users\Administrator\Documents\Codex\zhiming-v4-mod\private\mod-week\tmp\coverage-20261021-015412
```

- 新增文件清单命令：`git diff --name-only --diff-filter=A 8c554bd -- mingjing_core`（仅读）。
- 环境：子进程清除 provider API Key/API Token、禁用 tracing；TEMP/TMP、coverage data、原始输出均位于 `private/mod-week`。
- 无安装/下载、无实际模型/PG/HTTP/飞书/服务器请求；未改产品/测试、未作 Git 写操作、未读取盲评 B 正文。
- 限制：纯模块覆盖和本地合成回归不证明真实 PG 接入、通知投递、授权快照来自数据库或语义完备。
- JSON SHA256：`f6aea304db0498e8d1d18116903cc4e5d14bdb486a1a5a377d29d3f3185b6703`。
- 原始输出与完整前后快照：`private/mod-week/coverage-20261021-015412-raw.json`（本机私有文件，不含密钥或盲评正文）。

## 低于 90% 的文件

| 文件 | 行 % | 分支 % | 合并 % | 缺失行 / 分支 |
| --- | ---: | ---: | ---: | ---: |
| `mingjing_core/timeparse/profile_calendar_v2.py` | 67.42 | 50.00 | 61.65 | 29 / 22 |
| `mingjing_core/adapters/channels/stream_outbox_v2/codec.py` | 73.68 | 60.00 | 68.97 | 15 / 12 |
| `mingjing_core/adapters/channels/stream_outbox_v2/intents.py` | 77.05 | 60.00 | 71.43 | 14 / 12 |
| `mingjing_core/timeparse/profile_contracts_v2.py` | 82.26 | 57.69 | 75.00 | 11 / 11 |
| `mingjing_core/organize/supplement_v2/legacy_bridge.py` | 81.40 | 66.67 | 76.12 | 8 / 8 |
| `mingjing_core/scheduling/recurrence_calendar.py` | 80.43 | 72.73 | 77.94 | 9 / 6 |
| `mingjing_core/adapters/channels/stream_outbox_v2/contracts.py` | 83.97 | 67.95 | 78.63 | 25 / 25 |
| `mingjing_core/memory2/mutations.py` | 84.21 | 70.45 | 79.17 | 12 / 13 |
| `mingjing_core/application/briefing_v2/calendar.py` | 84.62 | 68.42 | 79.31 | 12 / 12 |
| `mingjing_core/streaming/envelope_reader.py` | 84.21 | 66.67 | 80.00 | 6 / 4 |
| `mingjing_core/organize/supplement_v2/lifecycle.py` | 86.52 | 64.71 | 80.49 | 12 / 12 |
| `mingjing_core/organize/v2/contracts.py` | 87.10 | 63.64 | 80.95 | 8 / 8 |
| `mingjing_core/streaming/codec.py` | 82.89 | 77.50 | 81.03 | 13 / 9 |
| `mingjing_core/adapters/channels/stream_outbox_v2/transitions.py` | 87.50 | 61.54 | 81.13 | 10 / 10 |
| `mingjing_core/application/briefing_v2/transit.py` | 87.06 | 71.05 | 82.11 | 11 / 11 |
| `mingjing_core/adapters/channels/action_token_refresh_v2.py` | 87.32 | 65.00 | 82.42 | 9 / 7 |
| `mingjing_core/organize/supplement_v2/projection.py` | 86.67 | 76.67 | 83.03 | 14 / 14 |
| `mingjing_core/adapters/channels/stream_outbox_v2/guards.py` | 86.49 | 79.17 | 83.61 | 5 / 5 |
| `mingjing_core/organize/supplement_v2/contracts.py` | 89.86 | 58.82 | 83.72 | 14 / 14 |
| `mingjing_core/scheduling/brief_schedule.py` | 86.67 | 75.00 | 84.21 | 4 / 2 |
| `mingjing_core/application/briefing_v2/evidence.py` | 87.50 | 78.00 | 84.42 | 13 / 11 |
| `mingjing_core/streaming/cleanup.py` | 89.71 | 68.18 | 84.44 | 7 / 7 |
| `mingjing_core/streaming/coalescer.py` | 90.14 | 69.23 | 84.54 | 7 / 8 |
| `mingjing_core/organize/v2/scoped.py` | 88.89 | 75.00 | 84.62 | 4 / 4 |
| `mingjing_core/application/briefing_v2/contracts.py` | 90.73 | 63.16 | 85.19 | 14 / 14 |
| `mingjing_core/memory2/conflicts.py` | 90.62 | 70.00 | 85.71 | 3 / 3 |
| `mingjing_core/memory2/plan_builder.py` | 90.12 | 75.00 | 85.84 | 8 / 8 |
| `mingjing_core/timeparse/recurrence.py` | 91.30 | 72.22 | 85.94 | 4 / 5 |
| `mingjing_core/streaming/text_projection.py` | 89.58 | 80.77 | 86.49 | 5 / 5 |
| `mingjing_core/timeparse/calendar_terms.py` | 87.50 | 83.33 | 86.67 | 3 / 1 |
| `mingjing_core/memory2/contracts.py` | 92.00 | 63.16 | 86.85 | 14 / 14 |
| `mingjing_core/adapters/channels/stream_outbox_v2/freshness.py` | 89.92 | 80.00 | 86.98 | 12 / 10 |
| `mingjing_core/memory/retrieval_rounds.py` | 92.42 | 70.00 | 87.21 | 5 / 6 |
| `mingjing_core/memory2/mutation_contracts.py` | 92.45 | 60.00 | 87.30 | 4 / 4 |
| `mingjing_core/memory2/consent_text.py` | 92.86 | 50.00 | 87.50 | 1 / 1 |
| `mingjing_core/memory2/dedup.py` | 90.91 | 80.00 | 87.50 | 2 / 2 |
| `mingjing_core/streaming/stream_clock.py` | 91.67 | 75.00 | 87.50 | 1 / 1 |
| `mingjing_core/streaming/store_serialization.py` | 91.30 | 78.57 | 87.63 | 6 / 6 |
| `mingjing_core/scheduling/recurrence.py` | 91.43 | 78.57 | 87.76 | 3 / 3 |
| `mingjing_core/timeparse/numerals.py` | 90.48 | 83.33 | 87.88 | 2 / 2 |
| `mingjing_core/timeparse/profile_dates_v2.py` | 88.64 | 85.71 | 87.93 | 10 / 4 |
| `mingjing_core/application/briefing_v2/authorization.py` | 88.64 | 87.50 | 88.24 | 5 / 3 |
| `mingjing_core/memory/retrieval_types.py` | 91.89 | 78.57 | 88.24 | 9 / 9 |
| `mingjing_core/organize/supplement_v2/guards.py` | 92.59 | 71.43 | 88.24 | 4 / 4 |
| `mingjing_core/timeparse/calendar_holidays.py` | 90.20 | 83.33 | 88.41 | 5 / 3 |
| `mingjing_core/application/briefing_v2/items.py` | 92.16 | 81.82 | 89.04 | 4 / 4 |
| `mingjing_core/timeparse/calendar_helpers.py` | 93.33 | 80.00 | 89.23 | 3 / 4 |
| `mingjing_core/memory/retrieval.py` | 92.42 | 83.33 | 89.58 | 5 / 5 |
| `mingjing_core/scheduling/recurrence_contracts.py` | 92.50 | 83.33 | 89.66 | 6 / 6 |
| `mingjing_core/organize/v2/classifier.py` | 91.67 | 84.78 | 89.76 | 10 / 7 |
| `mingjing_core/scheduling/recurrence_civil.py` | 97.14 | 71.43 | 89.80 | 1 / 4 |
