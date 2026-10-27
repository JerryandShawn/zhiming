# 命盘文本一致性检查：本机定向交付

记录时间：2026-10-21T00:14:51+08:00，北京时间。分支v4/p8-calc；主线review #15接入尚未实现。

## 行为与范围

公开API `check_chart_consistency(answer_text, chart_compute, *, expected_scope=None)`。四个skills模块复用现有learning_input内容/别名/原生primary校验，不改charts、v3、web或Agent，不改变排盘源码指纹。

核对明确日主、八正格候选筛选、分方法用神候选、第N步/明确ISO整日名义大运、紫微实际宫位主星、本命行星星座/宫位/精度感知度数与顺逆行。候选筛选不能支持已成格/用神已定；方法/主分支歧义保留needs_review，缺字段/证据不猜测。日期不依赖宿主时区或now；交运当日不强行选边。

引用、转述、假设、疑问、多重否定、句尾撤回/反讽、他人/旧盘/北京时间比较和其它运限层有保守守卫；明确标题在段内传递，到空行/显式当前真太阳主盘重置。不号称通用语义理解。

day_master计算出处现为time_basis_candidates._candidate声明坐标sect1/getDay，保留输入实际lunar-python版本、pillar_method真实method_ref；概念来源另列elements。其它格局/取用/大运逐层读取原生school/source，缺失显式source_unavailable。没有以人元司令章节替代真实日柱计算来源。

## 两个证据命名空间

顶层tool-evidence c/r绑定这次比较/守卫实际输出与具名项目规则，r不是命理成立断言。data.input_aliases与每项input_citations原样保留原盘依据和document/path；两种c1不能混用。内容hash不是签名；主线必须先检provider、owner、当前revision/撤销，再用expected_scope严格四键类型和值比较。结果record_only，不自动阻断或改写正文。

## 实跑证据

首轮事实/语言417例及词典微修265例合计682 passed；新增边界/Schema/独立review后，最终五文件 **495 passed，0 skipped，10.93秒**。

| 定向文件 | pytest案例数 |
| --- | ---: |
| `tests.v4.test_p8_consistency` | 294 |
| `tests.v4.test_p8_consistency_context` | 123 |
| `tests.v4.test_p8_consistency_boundaries` | 44 |
| `tests.v4.test_p8_consistency_contract` | 15 |
| `tests.v4.test_p8_consistency_review` | 19 |

12宫×14主星是168个不同的实际宫星归属断言，不把同一语句机械重复充数。还含十干的正/反直接否定、八正格真/假筛选、三候选方法、十步大运、十本命天体、书写精度、日期交界、输入内容/alias/branch/primary篡改、owner/subject/revision/operation及bool-int边界、未知与不相干引用、缺依据/字段、多方法/主分支、Schema和真实指针/claim哈希。495是参数化测试数，不是盲测题数或自然语言覆盖率。

独立代理首轮19例18绿/1失败，发现“日主是甲，才怪”误报。按保守反讽撤回守卫修复，原断言不改，独立19/19及最终全套495绿；其余两组先前静态发现不能冒称历史实际失败。最终Junit保存在private/p8-validation/consistency-final.xml，本报告仅摘要，不写私人正文。

Ruff E/F/I/B/UP/SIM与88列format --check全绿；文件/函数行数实测：

| 文件 | 行数 | 最长函数 |
| --- | ---: | ---: |
| `consistency.py` | 151 | 37 |
| `consistency_eval.py` | 155 | 48 |
| `consistency_facts.py` | 220 | 60 |
| `consistency_text.py` | 314 | 48 |
| `test_p8_consistency.py` | 254 | 15 |
| `test_p8_consistency_boundaries.py` | 241 | 23 |
| `test_p8_consistency_context.py` | 234 | 17 |
| `test_p8_consistency_contract.py` | 129 | 35 |
| `test_p8_consistency_review.py` | 161 | 21 |

## 样例、Schema与性能

契约chart_consistency.md和自包含chart_consistency.schema.json；三份consistency-ayuan-{bazi,ziwei,astro}.json是本轮真实纯函数输出，合成短答各含正确/错误/待复核断言。Schema通过不代表语义理解或命理预测已验证。

性能报告night28-consistency-performance.json：公开API每体系1次预热+10次连续观测，包含原信封verified_input全部内容核验，只用Core热进程。

| 体系 | 中位ms | 最小ms | 最大ms |
| --- | ---: | ---: | ---: |
| bazi | 20.042 | 19.798 | 21.137 |
| ziwei | 15.449 | 15.294 | 15.769 |
| astro | 15.531 | 15.217 | 16.400 |

输入样例与4模块、learning_input/tool_evidence来源SHA均绑定报告；生成性能后最终静态核对未漂移。热进程性能不包含解释器启动、网络、鉴权/撤销DB与主线review，不作生产SLA。

## 未验证与交接

主线review #15/流式策略/真实鉴权撤销/任意自然语言召回/产品行为和现实效度均未验证。明确低召回，不用no_contradiction_found替代全文验收；未知归属/复杂语法留not_checked或needs_review。未发模型、服务器、飞书、数据库请求；未写用户资料；本子代理未提交/推送，发布由root测试后统一处理。源/测试/Schema/样例/性能已按root要求冻结到全量回归完成，冻结期间仅写此证据报告。

## 全量后格式修正与最终定向复核

记录时间：2026-10-21T00:20:15+08:00，北京时间。

root于00:15合规窗口开始完整v4回归，报告2143/2143通过、0跳过、148.46秒。该全量对应拆行前源码；随后root只将consistency_text.py三条超过120列的相邻字符串字面量拆行，并记录`ast.dump(include_attributes=False)`完全一致。不能把格式后源码冒称再次跑过该全量。

拆行后的最终五文件定向复跑 **495 passed，0 skipped，10.92秒**，Junit保存在private/p8-validation/consistency-final-formatted.xml；三份已提交候选样例逐字等于当前公开API结果，无需重写样例。

旧性能文件night28-consistency-performance.json保留历史观测。新文件night28-consistency-performance-final.json重新以公开API各体系1预热+10观测，绑定格式后四模块及learning_input/tool_evidence实际SHA与原输入样例SHA；独立保存旧性能文件摘要及更正原因。

| 体系 | 最终中位ms | 最小ms | 最大ms |
| --- | ---: | ---: | ---: |
| bazi | 20.054 | 19.853 | 20.714 |
| ziwei | 15.757 | 15.583 | 15.874 |
| astro | 15.679 | 15.361 | 16.069 |

最终consistency_text.py LF SHA256：`83363f47dc7bf9fe1187f4b72362a11b140d495f3928863c7182574ea961b984`。其余源/测试/Schema/样例保持冻结到root提交完成；本轮仅按root授权运行Core定向与新增性能证据，未改源。
