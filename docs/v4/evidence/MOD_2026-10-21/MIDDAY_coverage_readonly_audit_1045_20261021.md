# 10:45 完成模块覆盖：独立只读审计

- 观察时刻：`2026-10-21T10:53:50.318891+08:00`（Asia/Shanghai）。
- 审计方式：只读公开报告、测量脚本、原始coverage JSON与源码字节；未运行测试、coverage、Git或产品入口。
- 本次仅新增本审计文件；未改代码、测试、fixture、原报告、旧191历史或三轮审计。
- 未读取Q5 B正文、私有75条正文；没有模型、网络、服务器、PG或通知请求。

## 结论与身份

只读核对通过。覆盖报告与10:45三轮使用相同27组、相同532份来源集合及SHA；审计时532份当前字节再次全部吻合。
这只是本地离线覆盖身份和统计核对，不能代替真实数据库、渠道、集成、CI、盲评质量或部署验收。

| 证据 | SHA-256 |
| --- | --- |
| MIDDAY_completed_coverage_1045.json | `5481293bb241147555e09eb33d4444a2b5aae0ce1c307469b58245b3b8f3d241` |
| MIDDAY_completed_regression_1045.json | `88d60d1071db7771d942a9a7602a787cd425f84133ae733c50d8c7affecad816` |
| 原始private coverage JSON | `8826b068daba455d884de7a7aa53b4628c91424b21598dc9d5d7cc3ed9cd8ca3` |
| 原始private测量脚本 | `a7ad1f3d4731cebb70274e9252d589a1b2635c6dfa0bf4987d5c79081eb950db` |
| 旧191产品覆盖报告（保持历史） | `7e77d6c25625361fa37eb61cc0266d79725ff9bac4619a20994bff11ec86359a` |
| 三轮独立只读审计 | `cda3c325352c1c66a7c5f18c5084fb2fb6fa16cc431e65ef8b3e560b1ca2ee4f` |

- 覆盖实际开始：`2026-10-21T10:48:50.345185+08:00`；实际结束：`2026-10-21T10:51:04.697033+08:00`。开始分钟48合法。
- 原始pytest结果：`12371 passed in 132.24s (0:02:12)`；exit0、stderr空、source_drift为空。
- 三轮与覆盖共享的532映射锚：`ccf00e2f74cbe837eea6c9f3ce59a0b38cea3e56a8435768f4fcf20981e91ce6`。
- 三轮非插桩结果与本次插桩结果分开，132.24秒不能与普通测试墙钟或性能报告比较收益。
- raw coverage meta为无时区本机时间`2026-10-21T11:51:04.769544`；不将它冒充+08门禁时间。门禁来自显式aware Clock转Asia/Shanghai的测量包装。

## 192产品分母

- 192个唯一文件，product_files与files集合完全相等，192份都在532来源账本中。
- 组成：175个本轮新增Core Python、12个calibration_v3纯工具Python、5个eval_material_v23纯工具Python。
- 相对旧191，唯一新增分母是`mingjing_core/application/briefing_v2/current_manifest.py`，没有移除旧文件。
- 静态核测量脚本按基底`8c554bd4af6788b3a4d98b9dd0d7618c591f7cfd`的A路径筛选上述3个前缀；本审计没有重新执行Git diff。
- 原始coverage json_report显式传全部192路径，未按是否执行过滤；两份零语句__init__仍列入文件数量，对总语句/分支权重为0。
- 基底已有产品、测试、benchmark及其余工具不在这192文件分母中；范围不是全仓库覆盖。

## 独立重算

| 口径 | 已覆盖 / 分母 | 百分比 |
| --- | --- | --- |
| 行 | 10210 / 10791 | 94.6158836067% |
| 分支 | 3478 / 4024 | 86.4314115308% |
| 综合 | (10210+3478) / (10791+4024) = 13688 / 14815 | 92.3928450894% |

- 192份summary逐项相加与totals完全一致；逐文件覆盖数+missing数等于分母，missing_lines及missing_branches数组长度与计数一致。
- 每文件percent_covered按行与分支合计重算吻合；公开文件数据与原始coverage JSON逐项相同。
- missing为581行、546分支；46文件综合低于90%。不把整体综合92.39%写成分支已达90%或所有文件均达90%。
- 旧191/57低于90文件记录保持历史，没有覆盖改写为本次192/46结果。

## 排除与范围边界

- coverage 7.11.0，branch_coverage=true；config_files_read为空，omit=None。
- 保留coverage默认exclude规则：pragma no cover、ellipsis占位体、TYPE_CHECKING；默认partial规则为pragma no branch。
- 原生统计excluded_lines=81，来自12个文件；未临时新增exclude/omit来提高分数。这81行不计入10791语句分母，不能声称已执行。
- raw/public逐文件缺失分支仍完整保留；测量不是靠删除未执行文件提高百分比。
- 固定10份材料及新增104测试的纳入证明见前一份三轮审计；本次复核覆盖source_files与其完全一致。
- 测量helper没有遍历B或私有校准材料；本审计只读哈希账本及coverage数字，没有重开其正文。
- 对A路径归属的证据是已锚定测量脚本与保持原191集合的差分；本次没有把禁止的Git操作或历史测试重跑伪装为独立复验。

- Root 2026-10-21T10:55:12.958596+08:00：只澄清前一份审计的10:49:58初查与10:51:28冻结时刻并更新其引用SHA；原引用SHA 7ef124fa29fb9b1a1b79927084f7b70989e04d0d9bb4c88602cf377ed6ee2c67 保留作修订身份。统计、原报告、原覆盖数据均未改。
