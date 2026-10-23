# 212术语与20课：第二轮有限只读审阅

观察时间：2026-10-21T01:03:06+08:00，北京时间，来自工具UTC读数换算，未依赖宿主时区。
范围只在v4/p8-calc本工作树；初次审阅只写报告，词典/课程/Schema/测试/样例当时保持冻结。
其后root明确批准下列直接出处与文字修正，执行情况独立追加在文末，不覆盖修前观察。

## 结论与审阅边界

复读212条术语的定义、例句和类别，20课全部正文、实际例子、40题及其解释；
另核跨文件引用、关键流派差异及精确来源支持范围。未发现新增确定的十神算式、
黄道角度、紫微宫位或当前合成盘观察值矛盾。未将“没有发现”扩写成全部古籍或流派已校勘。

旧G1–G4及十条定点修正不重做，本轮只确认读取的最终SHA没有漂移。
有四条新的直接出处链补充建议和一处课程连写歧义，均不要求更改冻结中的算法或数据。
下列出处缺口不等于正文数值算错；冻结解除后可做小型来源修订，再同步课程来源注册SHA。

## 新发现与具体修正提案

| 项目 | 原文和当前出处 | 实际本地证据 | 提案与优先度 |
| --- | --- | --- | --- |
| S1 平太阳时 | bazi-mean-solar-time：定义“按当地经度相对于标准经线的差换算”，例句“先做经度分钟修正……再加均时差”；仅引p8-time-basis，locator为resolve_birth_instants与clock_basis | time_basis.py该函数解析时区/钟表/标准时；真正公式在time_basis_solar.py:solar_time，53–56行为4*lon-offset、mean与apparent | 补已有p8-solar，明确支持经度分钟修正与apparent-minus-mean；保留p8-time-basis支持物理瞬间。这是具体公式出处补齐，不改算式。 |
| S2 北京时间 | bazi-beijing-standard-time：例句“同一实际UTC加8小时得到比较口径”；仅引同一resolve_birth_instants定位 | 该函数处理输入地点的历史标准偏移，不固定所有地点为+08；time_basis_solar.py:solar_time第59行明确beijing_standard=utc+8h | 同补p8-solar的beijing_standard实际字段，区分通用历史标准时与固定北京时间比较坐标。 |
| S3 行运正午例 | astro-transit例句“晨报用明确北京时间正午行星”；只引p8-astro-transit，其路径interactions_transits.py为连续区间求解 | daily_transit_natal.py:snapshot第22–33行显式日期12:00/+08；daily_transit_astro.py:astro_day第17–24行用该时刻求历表 | 保留原区间来源支持概念和entry/exact/exit；另补直接daily采样来源，不能以区间源码独自支持产品正午默认。 |
| S4 紫微午时例 | ziwei-ziwei-daily例句“晨报读明确日期午时采样……保留实际运限时辰索引”；只引p8-ziwei-time-editorial | 该章说明运限字段但未定义午时索引；daily_transit_ziwei.py:ziwei_day第34–45行显式horoscope(day,6)并保存snapshot_time_index=6 | 补具名实际实现来源，保留技能章作解释边界；程序采样约定不冒称古籍流派定则。 |
| E1 课程措辞 | lesson-19.json第53行：“ming_gong为亥；未来自shen_gong，不能用身宫字段替命宫。” | 当前真实主盘ming_gong=亥、shen_gong=未，正文同课也已正确区分；没有计算矛盾 | 改为“ming_gong为亥；‘未’来自shen_gong字段，不能用身宫字段替命宫。”避免“未来”连写读成另一时间层。纯编辑澄清。 |

S1/S2可复用现有source_id，不必为同一公式再造新权威。S3/S4若新增来源，应标project_implementation，
精确列snapshot/astro_day/ziwei_day与支持范围，不能只因路径存在就称每句话已有逐句支持。
以上提案本轮未执行，尚未改变任何绑定SHA。

## 已知分类与尚待决定的表达改进

真太阳时definition_kind已为astronomical_time_coordinate；平太阳时、北京时间、夏令时仍是
traditional_concept。它们的正文分别正确区分太阳坐标、固定标准时与民用历史规则，
没有假托古籍；但类别会让前端把现代时制误列作古法。这是上一轮已记录的语义分类改进，
不是本轮新增数学错误，不应以“新发现”重复计功。

后续可将平太阳时改到现有astronomical_time_coordinate；北京时间与DST更适合新增明确的
civil_time_convention类别。新增枚举需要同步Schema、消费约定、测试及课程引用SHA，
不能在01:15全量冻结中静默修改。若暂不扩契约，保留当前正文区别并在显示层说明类别粒度有限。

lesson-15“当前三候选集合的consensus_stems为[庚]”与实际输出一致，但该字段包含格局候选
集合的并集，不只收筛选通过者：当前pattern内正印候选true取壬、偏印候选false仍列庚；
p8_structure.py:reviewed_useful第127–133行按所有row候选构造集合。课程没有声称这些全部成格，
因此不判为确定错误。教学上可补一句“未过筛者仍是待议候选，不把交集当成已成立用神”，
让学习者知道庚从哪来；这不授权修改计算算法或把候选升为结论。

## 跨文件与观察值独立核对

一个Core只读JSON审计过程，未运行pytest、Charts或重新排盘。独立解析原信封document/alias/Pointer，
比较JSON值与类型，核来源ID、真实引用及固定输入SHA；未复用课程测试的_binding作为判定器。

| 核对对象 | 观察结果 |
| --- | --- |
| 词条 / 体系 | 212；八字72/紫微55/西占50/塔罗35 |
| Schema对象 | 两份词典数据、一个课程目录、20课，共23对象结构通过；不是23个pytest用例 |
| 来源 | 36注册；31本地路径存在、5URL本轮未访问；术语/差异/课程无未知source_id |
| 课程 | 20个唯一顺序/前置链，40题答案与expected严格相符；概念题来源属于本课source_ids |
| 固定输入 | 三chart+三learning共6文件SHA及三个case scope逐项一致；来源注册SHA一致 |
| 观察与例子 | 20条实际观察Pointer值等于expected，20个worked_example依据不跨case；学习卡ID可解析 |
| 原生r | 三条rule_input均能解析真实met=true且c在r.evidence_aliases；false候选没有伪造r |
| 文本别名 | worked_example所写c/r均在该例声明的原始依据中，未跨operation混用 |

课程当前按source_id共享词典来源注册，但没有逐课term_id字段或已经连好的术语弹窗映射；
这不是现有数据错误，也不能据课程/词典并存就宣称前端词典到学习卡已集成。

正文额外抽核了未单列为测验expected的具体观察：四柱甲戌/丁卯/丁酉/甲辰、两分数63.0/77.5、
卯支乙/甲本余角色、三命司令甲及节后6.196日、第三步大运庚午、三候选交集庚，均与当前主盘一致。
课程用辰藏壬保留所选sanming_5520异文，明确不混现代常见癸表；不能据常见表印象将其当本课错误。

西占次限确用Ephemeris.julian的utc_to_jd得到UT1后映射365.2422，未发现“仅UTC相减却称UT1”的问题。
第20课明确旧本命沿用julday民用UTC近似UT，与新western_timing方法分开，没有把两种历表入口混称。
塔罗35词沿原创牌义与项目编辑章节，不将公版书一般引用冒充原创句子的逐句来源。

## 读取版本与限制

| 文件 | 当前SHA256 |
| --- | --- |
| p8_glossary/terms_v1.json | b9d310c560df92666b9c1f2d4bdcf6c6a821d099908d113cc4a22acfb32e14a4 |
| p8_glossary/sources_v1.json | 3e1d2035b299548b1b413a707d3bb28c0e5c8991b96ef3b0c0b723eb2c3aaf12 |
| p8_learning_lessons/curriculum_v1.json | 0348759805ad6a83288888ebbd8dceea07d772b419ef74aab990baecf34c1ec3 |

.gitattributes将正文统一eol=lf；课程测试的read_bytes摘要在当前LF工作树与目录一致，
不能把某个外部CRLF导出文件的原始字节hash说成同一值。
未认证5个URL当前内容、古籍版次页码、全部跨派原典、教学效果、模型表现或现实预测效度。
只读过程已结束；模型/网络/DB/服务器/飞书请求0，不修改其它线、不提交推送。

## root批准后的有限修订

四条术语补直接来源，212个ID、顺序、分布、正文和例句均保留；未改既有十条定点修正文。
平太阳/北京时间复用p8-solar的具体solar_time定位；行运补p8-daily-snapshot与p8-daily-astro，
紫微流日补p8-daily-ziwei。来源从36变为39，其中34本地路径、5旧URL；三项新增都明确项目实现。
分类枚举、传统流派断言、原刊页码、候选算法和七技能正文均未改。

lesson-19只将quiz[0].explanation的“未来自shen_gong”澄清为“‘未’来自shen_gong字段”。
课程目录仅source_registry.sha256同步新来源摘要，cases字段未动；随后已交回root重绑样例，
本代理不再写curriculum，避免并写和引用漂移。S1–S4/E1因此已落实，不再是待执行提案。

修后词典原测试未改，单Core实跑**268/268，0skip，0.31秒**；
Junit `private/p8-validation/glossary-second-review-final.xml`。
比旧265多三项来源路径参数化，不把它说成新增三项专业效度或自然语言正确率。
课程定向验证待root完成三chart/三learning及cases重绑后再跑，不预填已通过。

| 首次修订写入文件（CRLF原始字节，非最终LF） | SHA256 |
| --- | --- |
| terms_v1.json | 19926b1685ba6659ea13be1ffdf005fd7f594680c968b48b0c69e79f0ed85f75 |
| sources_v1.json | 6972500f0d5d7dd89cc74d35961bb25538effc0792fa105b813d95c8cd531705 |
| lesson-19.json | a7304571a2095b066fcd95a68cb06370d2be4f61542623213bd95b41c41de834 |

上述数据及测试已冻结，读写占用已释放；完整v4结果由root在合规窗口另行记录。

### 换行绑定纠正

提交前git检查发现Windows默认文本写入把上述三JSON写为CRLF，首次课程来源绑定因此用了CRLF
原始字节SHA。若不纠正，Git按eol=lf归一后会使绑定漂移。已显式newline=LF重写三文件，
逐个比较解析对象完全相等，没有改语义、类型、顺序、来源或题目；立即将最终来源摘要交root。
本代理没有在root重绑时并写curriculum，root以实际LF文件字节重新取得来源SHA。

| 最终LF文件 | SHA256 |
| --- | --- |
| terms_v1.json | b1005b6e1748c7cb0dc680ff0b43ea93c4e54819b3a23da49f8e5b3a0cd197b3 |
| sources_v1.json | a781219cbf9f364ca6fbe89e82ce5e4640a99851a29bc65988b7ddcfcf67f1f1 |
| lesson-19.json | 4798ae772770eefd860012d43516e0475ea06d4e91e73b18f4b63edffdf5dcdd |

前表仅留首次写入检查历史，不拿其中的CRLF值称最终交付SHA。

### 最终样例重绑回归：先保留失败事实

root完成输入预检修正后的三chart/三learning重建与目录hash重绑，通知冻结后，
本代理在1个Core进程聚合原词典和课程测试。首跑**348通过、2失败、0skip，0.66秒**，
Junit `private/p8-validation/study-second-review-final.xml`。
两项都定位第20课：astro_sun_sign沿用旧c1，而新信封实际view.primary为c2；
_binding按course_primary_required正确拒绝，不能为让测试绿而接受诊断或另一层对象。

新c2指向原生实际主盘`/artifacts/chart-3686c55a4452d118711b00b7/data`，c1则是另一document的/data。
已将最小修正提交root：只将目录该依据的c_alias和第20课两处显示引用换为真实c2，
relative_path、expected、答案与测试保护均不改。curriculum由root独占，本代理没有并写数据。
最终修后结果待root明确通知样例稳定后另记，不预填通过。

root随后只将该目录evidence的c_alias改为真实c2，并将第20课worked_example及第1题解释的两处
〔c1〕改为〔c2〕；没有修改实际数值、答案、测试或primary门槛。收到数据稳定通知后复跑同一集合，
**350/350通过、0skip、0.53秒**（词典268+课程82），Junit `private/p8-validation/study-second-review-rebound.xml`。
2026-10-21T01:09:58+08:00检查进程已结束，之后仅写本报告，继续冻结数据到root全量结束。

| 最终重绑产物 | SHA256 |
| --- | --- |
| curriculum_v1.json | 172e78899d753d27dcf5a95620a99d5961d5a20c0d09b891956912e13ac32a60 |
| lesson-20.json | f17322f51718fde5a29830726559f847d1392c2f346b1e448f9837f476764308 |
| ayuan_bazi.json | fe11a98184a296417f927d16cc57ee3ba664d77865393b9f20b2f867b0ea313b |
| ayuan_ziwei.json | 306b1f368a310b6963187b983245e7c2d492b1ef59fbf99f8c5f28c3cd19571e |
| ayuan_astro.json | 35a0bb10dce92aac401a49905b6c0d08fb127179de92418c79166c5ad8ea7f7c |

首轮348/2的失败记录保留，不能把它改写成重绑一直成功；再次说明同短号并不跨计算指纹稳定。
