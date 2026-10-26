# 四只读工具：第二轮独立边界审阅

北京时间2026-10-21 01:04初记。范围为daily_transit/window_search/almanac/synastry及已发布合成样例。
本子任务只新增专属测试和报告，不修改实现。原36项API、分页5项、四工具已有测试先行读取，
新增15项避开重复日期格式、普通分页31/1/0和已有consent空值组合。

## 修前真实观察

| 位置 | 最小复现 | 实际结果与边界 |
| --- | --- | --- |
| window内部daily聚合 | 真实10-21daily的scope.revision从整数1改True，重算document_id；以原int scope调用_score_results | 被接受，复制40命中、score=-7；dict相等未区分布尔与整数。默认原生daily产出类型正确，未声称公网用户可注入这个内部helper |
| 合盘双输入预检 | 第二人tz改为Mars/Olympus，其余真实合成输入和已确认consent不变；以只抛异常的prepare_natal守卫记录是否进入 | 首先进入synthetic-ayuan左盘准备，才可能在右侧识别未知IANA；未实际执行Charts。守卫不是假盘面替身，仅证明是否进入计算 |
| window不完整关系权重 | 真实首条三合facts.complete仍false，仅context.complete改为0或字符串false，重算document_id | 两种均从零权重变成+4，总分-7变-3；正常原生context未被指为错误。此处缺的是聚合载体类型门禁，不要求改现有合法权重 |

上述源缺口先报告root，由root独立修共享实现；本审阅不私改源码。
普通内容hash可以重算，所以不能用过期hash拒绝冒充类型/语义修复。
主线来源授权仍是外部责任，有限边界保护不构成任意伪造载体的完整命理复算。

## 新增15项保护

- 重算scope后True及1.0不能冒充整数revision：2项。
- 第二人未知IANA、出生晚于目标日都须在准备任何一人前拒绝；分别保留固定错误码：2项。
- 不完整关系complete=0/字符串false/缺失、context从False改True但底层事实仍False、事实complete改0而contextFalse，都须固定拒绝：5项。
- Core适配器在未确认consent时，应先于NaN资料检查和worker分派拒绝：1项。
- 四份实际成功样例先通过各自Schema，再分别破坏正午UTC+8、页内rule_hit_index类型、农历月零、双人revision类型，须拒绝：4项。
- 第二页114条observations的daily_hit与facts逐项回对当日已发布真实daily；只为文档ID重建窗口scope，不能借单独daily的operation：1项。

最后一项与原分页测试不同：原测试核本页r/c摘要、分页位置和加减分，本项回到完整外部daily源核实际命中及复制值。
重建scope只用于验证内容ID的实际归属，不改事实、不新造盘、不把单独日工具的原document_id冒称窗口同源ID。

## 验证状态

新增文件：`tests/v4/test_p8_tools_independent_boundaries.py`，默认Ruff格式及E/F/I/B/UP/SIM通过。
root修改三个共享实现文件后，新15项+既有36/API+原window55项共106项首跑：
**105通过、1失败、6.15秒**。仅1Core+最多1Charts，与root最多2进程重绑样例错开/合计不超4；
显式使用锁定Core的tzdata，清除模型凭据、关闭追踪，没有数据库或真实模型请求。

唯一失败是第二人出生晚于目标日仍被归一为daily_transit_natal_invalid；要求的daily_transit_before_birth
在validate_request的早期出生先后检查之后，尾部snapshot不可达。两人准备调用数仍为0，没有先算后拒绝。
该项原样报告root修复，没有放宽错误码断言。
其余14个新增保护及全部既有91项均通过；源码指纹/样例重绑由root集中处理。

## 最终复跑

北京时间2026-10-21 01:07，root将已验证DOB后的snapshot放在validate_request之前且置于归一try之外，
三个实现文件冻结后，仅复跑同一组，没有删改失败断言：

    python -m pytest -q tests/v4/test_p8_tools_independent_boundaries.py tests/v4/test_p8_night28_api_review.py tests/v4/test_p8_window_search.py

结果：**106 passed、0 skipped、6.26秒**，其中新15、既有36/API、原window55。
最多1Core+1Charts，完成后两者均退出；没有另起全量。新增测试167行、单函数≤60、单行≤120，
最终Ruff格式与E/F/I/B/UP/SIM检查全部通过。

root的修复不改变合法盘面算法或权重：scope逐键核值及类型；用既有load_zone预检IANA；
不完整关系的context.complete须真bool，首条真实关系fact的kind/complete还须与context一致。
实际fact没有complete时仍沿用已有True约定；不是把已明确false改为True。
未来出生原来已经在validate_request被拒绝，本轮只修稳定错误码与顺序，不能称它此前会排盘。

最终复跑时三个实现的UTF-8文本/LF SHA256：

| 模块 | SHA256 |
| --- | --- |
| window_search.py | cdc1db7638183e8f61afdd1fd71cca90273ef925c48690c26819a7b4c75ae526 |
| window_search_scoring.py | f7e327774724502489466f9dafb5bc3b8176f18dd7055d88038faff942f285a5 |
| daily_transit_natal.py | 2c393b996f4050d2df2367d9890280a093b5efeed2a877237a8d57f16558a1a6 |

## 仍未证明的范围

这是内部载体与公开预检的有限保护，不能凭Schema通过或普通内容hash认定数据来自可信provider。
没有对任意伪造context、所有来源字段或全部中文解释做完整命理复算。
四份成功Schema的四个坏形状已实际拒绝，不代表每个嵌套字段都具备完备语义限制。
出生夏令时fold/gap和全年属性已有独立证据，本组没有重复启动大批日期研究。

样例、主线授权/撤销账本、准确提交CI和完整回归由root集中更新；本组的旧7日raw数值仍用于来源对读，
不把旧样例中历史方法指纹自动称为本次最终源码执行。技能原生样例若需绑定这三个新文件，
须通过已有生成器重建，已向root提示，未由本子任务擅自改样例。
没有服务器、模型、飞书、数据库、其他工作树或Git合并操作。
