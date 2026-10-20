# 三复合规则：实际条件最小对照

完成时间：2026-10-21T01:44:45+08:00，北京时间，工具UTC读数换算。
基于来源提交 `3eb5b8f6c46ef23648d1040cb4ce91e1d0e75965`，本工作树 `v4/p8-calc`。
本增量仅新增 `tests/v4/test_p8_extra_condition_matrix.py` 和本文；未修改规则数学、知识表、
旧fixture、v3、共享样例、契约、课程或其它工作树。由root统一提交推送，本代理未自行提交。

## 实际实现与判据

本轮承接只读剩余清单的首项，验证以下三个实际登记ID的各三条件：

- `u12-pattern-established-lu`：建禄；
- `u12-pattern-month-robber`：月劫；
- `u12-pattern-yang-blade`：阳刃。

三条件顺序是“月令符合具名格局锚点”“透干满足一条候选取用路径”“未见本条显性败因”，
来自 `mingjing_core/adapters/charts/p8_structure.py:83–122` 的真实 `reviewed_extra`。
`rules/conditions.py:44–67` 读取实际screen_passed并保留三个条件Pointer；
`rules/engine.py` 生成全部assessment且只把true放进rule_hits。

每对仅替换四柱中的一个完整合法干支值，日主保持不变；不是任意改布尔、十神、strength或screen_passed。
每次先走 `tests/v4/p8_rules_sample_context.py:18` 的make_data，实际生成具名藏干、十神、
两法旺衰和格局，再执行当前evaluate_rules。断言原生三布尔值、screen_passed、assessment.met、
true命中存在/false不命中、三条真实Pointer、登记来源、输入完全不变，以及candidate_only边界。

## 九对实际观察

T/F是实际condition.satisfied的布尔值，不是从测试预期回填进输入。
每对原始正例都是TTT、met=true；右侧只对应一个条件改为false、met=false。
完整合成四柱在新测试内，以下列必要的单柱变化与语义，避免把测试说成出生历法案例。

| 规则 / 条件 | 单柱变化（正例→反例） | 观察向量 | 最小对照说明 |
| --- | --- | --- | --- |
| 建禄 / 1 | 月戊寅→戊辰 | TTT→FTT | 只变月支，保留年月时透干集合；甲日寅禄锚点离开 |
| 建禄 / 2 | 年辛酉→壬申 | TTT→TFT | 去正官后，财印集合没有现行三条取用路径；显性败因仍未见 |
| 建禄 / 3 | 时丙申→壬申 | TTT→TTF | 两例都保留庚杀与丙食路径；新增透印使“无财官、杀印并透”显性败因成立 |
| 月劫 / 1 | 月戊寅→戊辰 | TTT→FTT | 乙日月支本气不再是劫财；透干及败因条件不变 |
| 月劫 / 2 | 年庚申→癸亥 | TTT→TFT | 去正官后剩财印，无食伤/杀路径；显性败因仍未见 |
| 月劫 / 3 | 年庚申→辛酉 | TTT→TTF | 正例官印路径→反例杀食路径，第二条件仍true；无财官的杀印并透触发第三条件失败 |
| 阳刃 / 1 | 月己卯→己巳 | TTT→FTT | 只变月支，甲日卯刃锚点离开，官财印透干不变 |
| 阳刃 / 2 | 年辛酉→癸酉 | TTT→TFT | 去唯一官杀，财印支持仍在且没有伤官，只有取用路径失败 |
| 阳刃 / 3 | 时壬申→丁卯 | TTT→TTF | 官与财仍满足第二条件，丁伤官令第三条件失败 |

静态方案先推导这九对，再用private中的单Core实际探针核算18个成员；九对全部符合后，
才将草稿复制为新的测试文件。没有先把不成立向量写成已通过，也没有调整规则或旧fixture来凑向量。
当前九对不需要报告不可达项；这仅证明本三条件的上述单条件失效对照可达，未穷尽所有8向量/流派/日主。
其中复用正例，所以九对共18次成员观察、14个不同合成四柱对象，不能把18说成18份独立出生盘。

## 依据别名与出处边界

evaluate_rules本身不登记c/r。测试先核每条原生evidence_paths能解析到真实condition对象，
再将选中规则的实际true hit传给现有tool_evidence.evidence_result，形成**测试局部临时信封**：

- r实际指向原生命中，rule_id/source保持登记值，值SHA独立规范化重算；
- 三个c实际指向三个原生condition，r.evidence_aliases逐个绑定，使用运行时短号；
- false不创建r；这个仅收true hit的测试包装也不创建false c。false原生条件仍通过Pointer逐项可读；
- 此包装scope=null、ephemeral_only，不是chart_compute主盘信封、会话账本或用户授权的端到端验证。

没有把测试局部r1标成某份阿远主盘的r1，也没有为falseassessment补造命中。
出处直接比较当前 `mingjing_core/knowledge/p8_bazi/rules_v1.json` 的真实登记：
《子平真诠》第九章成败、第四十三至四十六章阳刃与建禄月劫；沿用现有转录定位。
本轮未外访原文、未核版次页码，不能由来源元数据相同推断古籍已逐句校勘。

## 实跑结果与文件绑定

九对探针通过后，新增9个条件对照测试及3个登记/每规则三条件覆盖检查，共12新项。
与既有 `test_p8_rule_hits.py`、`test_p8_rule_review_24.py` 的153项聚合：

    <Core Python> -m pytest tests/v4/test_p8_extra_condition_matrix.py \
      tests/v4/test_p8_rule_hits.py tests/v4/test_p8_rule_review_24.py -q

首次聚合165通过、0skip、0.62秒。自审后再给每个成员加上直接的
screen_passed/met预期true或false断言，防止只验证两字段互相一致而不验证真实决策；
没有生产失败或规则改动。最终同集合**165/165通过、0skip、0.64秒**，
Junit：`private/p8-validation/extra-condition-matrix-final.xml`。
Ruff检查及88格式通过；新文件158行，最长87字符，最长函数27行。

| 文件 | SHA256（实际LF文件字节） |
| --- | --- |
| tests/v4/test_p8_extra_condition_matrix.py | d564ad3c08e1e0272659701103f43f1bf8d558fb8e15153b53fc1cad62f9088c |
| mingjing_core/adapters/charts/p8_structure.py（只读） | 3dcc442a40d13511b2abb61f36e35be6995a898e0cfa6a61640bfe6333c36e07 |
| mingjing_core/knowledge/p8_bazi/rules_v1.json（只读） | 29df571dbe201d7ed35dec2285d36dbbdf621c568517c026944fbcf89c3093fa |

探针/测试串行，最多一个Core进程；测试前清进程API凭据并关闭LangSmith/LangChain/OTel追踪，
指定原有Charts解释器与tzdata路径但没有启动Charts。测试进程现已结束，新测试冻结，之后只写本文。

## 不能据本结果声称

这是三条复合候选最终布尔决策的九组独立条件对照，不是整个程序或内部取用OR分支的完整MC/DC。
所有四柱成员各自干支阴阳合法，但未验证它们对应真实同一出生年月日时；没有新增历法金标准。
通过候选筛选仍不证明成格、制杀力量、合化、救应、岁运应事或现实预测效果。
没有改倒推冻结政策、规则优先级、真实E2分数或主线授权/别名账本。
本次真实模型0、Charts0、网络0、DB0、服务器0；不访问其它工作树，不合并PR。
