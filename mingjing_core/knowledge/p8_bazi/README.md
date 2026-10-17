# P8 显式八字计算资料 v1

本目录只供 `P8ChartAdapter` 使用，未加入 v3 `KnowledgeRegistry`，没有发布新的解释规则。全部表与项目权重均是可复查的计算口径；不是专家认证或人生预测的实证模型。

| 资料 | 版本与来源 | 核对粒度及限制 |
| --- | --- | --- |
| `month_command.json` | `sanming-renyuan-wikisource-2026-10-17-v1`；[《三命通会》卷二·论人元司事](https://zh.wikisource.org/wiki/三命通會/卷二#论人元司事) | 逐月分日段对照公开转录；寅为戊5/丙5/甲20。原文辰壬、未甲、戌丙、丑庚保留，与常见现代藏干表不同。未校勘原刊影印本；不覆盖 v3 本气字段。 |
| `climate.json` | `p8-qiong-tong-opening-candidates-2026-10-17-v1`；[《穷通宝鉴》公开转录](https://zh.wikisource.org/zh/穷通宝鉴) | 120 键：96 为月段开篇，23 为合月/季节段，1 为乙丑借冬月通则。逐行保存 `extraction_status`、`basis_scope`、段落位置与完整段落文本 SHA。候选由项目编辑摘取；全部 `full_original_collation=false`、`full_chapter_conditions_implemented=false`。没有宣称原书全文条件或原刊已逐项校勘。 |
| `auxiliary_stars.json` | `p8-auxiliary-explicit-day-anchor-v1`；《三命通会》卷二/三及[《命理探源》卷三原文](https://libokang.com/zh-hant/classics/bazi/命理探源/) | 八类标记，仅给查法与位置；天乙合双贵不分昼夜、羊刃只定义五阳干，年支/日支锚分列。文昌按所载歌诀；丙丁食神土的寄生/长生位是例外，不能全部套食神禄位。公开转录含现代译文，本表仅取明确标出的古歌/原文，不采用现代译者断语。 |

调候表的 `p22` 等定位是本次页面所有 `<p>` 元素从零计数的序号；页面结构可能变化，因此同时记录 UTF-8 原段落 SHA256。`source_excerpt` 是审核用的开篇片段，不作为运行时解释输出。运行时只暴露候选与来源/核对范围。数据库、模型及网络均不参与查表。

旺衰参数位于 `calculations/bazi/strength.py`，具名版本 `p8-month-root-exposed-v1` 和 `p8-order-ground-momentum-v1`。第一法：印比月支本气40分、四支同五行根每支最多10分（藏干分配 1；0.7/0.3；0.6/0.3/0.1）、年月时印比透干每干20/3分；45与55为中间区间边界。第二法：项目定义的“得令”即月支本气为印比40分，“得地”按四支本气印比每支7.5分，“得势”按年月时印比每干10分，同样45/55分界。**所有数值、角色比重与阈值均为项目原创未审核参数，古籍只作季节生扶概念来源，不能称原典打分法。** 两法不相加、不投票、不输出唯一旺衰真理。

格局条件筛选 `p8-pattern-condition-screen-v1` 引[《子平真诠·论用神》原文](https://www.donglishuzhai.net/chapter/3721.html)的月令、透出与顺逆用概念，但具体八正格/从格筛选条件及数量阈值为项目编辑，不是全书规则的等价实现。结果仅标“候选/条件满足”，明确列合化、救应、特殊外格等未评估项。喜用三思路分别保留扶抑两法、调候摘表与格局候选；交集为空就是空，不强选一个结论。

所有来源差异与待决事项见 `docs/v4/evidence/P8/calc-crosscheck.md`。日后要升级为正式流派规则，需大脑选定版本、校核全部条件并新增版本；不能在原 v1 上无记录覆盖。
