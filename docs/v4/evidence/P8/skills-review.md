# P8技能包审阅清单（2026-10-18，增补v2）

状态：草稿，待所有者抽查。八字10章（七基础、准确时刻核对、低优先证据工作台、民间口诀），紫微6、西占5、塔罗7，共28章。
版本p8-skills-draft-2026-10-18-v2。产品目录采用Agent Skills frontmatter，未安装个人/系统Codex技能；只读loader不调用模型、不写出生资料。
每章均有方法、字段根对象、流派分歧、前提、反例、白话别名示例、对应rule_id与出处。规则命中只表示条件成立，传统解释不混入规则函数。

新设计已替换原U9排名/前三论证：用户已有准确时刻，优先记录与time_basis换算，不启动事件倒推。新工作台只作为低优先离线预备；冻结/holdout/permutation与“分不出来”原则已写清，旧两分相加与前三字段不再作为当前接口。
民间口诀专章标“民间流传口诀，未见可靠古籍出处”，只展示不评分，不给它补造书名。

## 逐章索引

| 体系/主题 | 摘要与边界 | 出处 |
| --- | --- | --- |
| [bazi/basics](../../../../mingjing_core/skills/bazi/01_basics.md) | 基础、十神与司令；只读已登记字段 | [沈孝瞻著、徐乐吾评注《子平真诠评注》](https://www.anhappy.com/share/books/others/books/%E5%9B%BD%E5%AD%A6/%E5%AD%90%E5%B9%B3%E7%9C%9F%E8%AF%A0%E8%AF%84%E6%B3%A8.pdf)：第一章论十干十二支、第二章论阴阳生克、第三章附支藏人元司令图表；[万民英《三命通会》](https://zh.wikisource.org/wiki/三命通會/卷二)：卷二论天干阴阳生死、论人元司事；与项目所选具名表对照；[袁树珊《命理探源》](https://libokang.com/zh-hant/classics/bazi/命理探源/)：卷三强弱·天乙贵人、羊刃（引古歌、曹震圭、《渊海子平》）；只核原文表，不采用站点现代白话 |
| [bazi/strength](../../../../mingjing_core/skills/bazi/02_strength.md) | 旺衰判断：两种项目口径；只读已登记字段 | [沈孝瞻著、徐乐吾评注《子平真诠评注》](https://www.anhappy.com/share/books/others/books/%E5%9B%BD%E5%AD%A6/%E5%AD%90%E5%B9%B3%E7%9C%9F%E8%AF%A0%E8%AF%84%E6%B3%A8.pdf)：第六章论十干得时不旺失时不弱；第二章论阴阳生克；[万民英《三命通会》](https://zh.wikisource.org/wiki/三命通會/卷二)：卷二有关五行旺衰的概念；权重与45/55均非原典数字 |
| [bazi/patterns](../../../../mingjing_core/skills/bazi/03_patterns.md) | 格局候选与成立条件；只读已登记字段 | [沈孝瞻著、徐乐吾评注《子平真诠评注》](https://www.anhappy.com/share/books/others/books/%E5%9B%BD%E5%AD%A6/%E5%AD%90%E5%B9%B3%E7%9C%9F%E8%AF%A0%E8%AF%84%E6%B3%A8.pdf)：第八章论用神、第九章论用神成败救应、第十章论用神变化、第二十二章论外格用舍 |
| [bazi/climate-useful](../../../../mingjing_core/skills/bazi/04_climate-useful.md) | 调候与喜用：三条思路并列；只读已登记字段 | [沈孝瞻著、徐乐吾评注《子平真诠评注》](https://www.anhappy.com/share/books/others/books/%E5%9B%BD%E5%AD%A6/%E5%AD%90%E5%B9%B3%E7%9C%9F%E8%AF%A0%E8%AF%84%E6%B3%A8.pdf)：第十四章论用神配气候得失、第十五章论相神紧要；这里只支持方法区分；[万民英《三命通会》](https://zh.wikisource.org/wiki/三命通會/卷二)：卷二论天干阴阳生死；具体调候摘表出处以计算块 source_locator 为准，未核刊 |
| [bazi/time-layers](../../../../mingjing_core/skills/bazi/05_time-layers.md) | 大运、流年、流月与时间交互；只读已登记字段 | [沈孝瞻著、徐乐吾评注《子平真诠评注》](https://www.anhappy.com/share/books/others/books/%E5%9B%BD%E5%AD%A6/%E5%AD%90%E5%B9%B3%E7%9C%9F%E8%AF%A0%E8%AF%84%E6%B3%A8.pdf)：第七章论刑冲会合解法、第二十五章论行运、第二十六章论行运成格变格 |
| [bazi/life-topics](../../../../mingjing_core/skills/bazi/06_life-topics.md) | 六亲、事业、财运与感情；只读已登记字段 | [沈孝瞻著、徐乐吾评注《子平真诠评注》](https://www.anhappy.com/share/books/others/books/%E5%9B%BD%E5%AD%A6/%E5%AD%90%E5%B9%B3%E7%9C%9F%E8%AF%A0%E8%AF%84%E6%B3%A8.pdf)：第二十三章论宫分用神配六亲、第二十四章论妻子；不沿用原书性别与阶层断语 |
| [bazi/misreadings](../../../../mingjing_core/skills/bazi/07_misreadings.md) | 常见误读、边界与档案一致性；只读已登记字段 | [沈孝瞻著、徐乐吾评注《子平真诠评注》](https://www.anhappy.com/share/books/others/books/%E5%9B%BD%E5%AD%A6/%E5%AD%90%E5%B9%B3%E7%9C%9F%E8%AF%A0%E8%AF%84%E6%B3%A8.pdf)：第二十一章论星辰无关格局、第二十九章论时说拘泥格局、第三十章论时说以讹传讹 |
| [bazi/rectification](../../../../mingjing_core/skills/bazi/08_rectification.md) | 准确时刻优先：文档与时间口径核对；含待接入项 | [IANA时区规则](https://github.com/eggert/tz/blob/main/asia)：asia: PRC与历史规则；[NOAA太阳计算说明](https://gml.noaa.gov/grad/solcalc/calcdetails.html)：均时差方法 |
| [bazi/rectification-rules](../../../../mingjing_core/skills/bazi/09_rectification-rules.md) | 证据工作台：冻结、留出与置换；含待接入项 | [Stellium计算式校正研究](https://stellium.readthedocs.io/en/stable/development/specs/rectification/RECTIFICATION_REPORT.html)：预注册/零假设检验背景；项目检验门槛以设计文件为准；[Gelman与Loken：分岔小径](https://stat.columbia.edu/~gelman/research/unpublished/p_hacking.pdf)：原始论文 |
| [bazi/traditional-hour-methods](../../../../mingjing_core/skills/bazi/10_traditional-hour-methods.md) | 定时辰的传统方法：只展示，不计分；含待接入项 | [民间定时辰资料（非可靠古籍）](https://k.sina.cn/article_6431044916_17f51f534001003vbp.html)：17号§10所列转帖，仅作传统说法与互相矛盾的语料出处；[民间定时辰资料（非可靠古籍）](https://tianyugong.com/dcssc/)：17号§10所列转帖，仅作传统说法与互相矛盾的语料出处；[民间定时辰资料（非可靠古籍）](https://www.sina.cn/news/detail/5109461637141808.html)：17号§10所列转帖，仅作传统说法与互相矛盾的语料出处 |
| [ziwei/palaces](../../../../mingjing_core/skills/ziwei/01_palaces.md) | 命身宫与主星：先定位再解释；只读已登记字段 | [《紫微斗数全书》](https://zh.wikisource.org/wiki/紫微斗數全書/卷二)：卷二安命身宫诀；[《紫微斗数全书》](https://zh.wikisource.org/zh-hant/紫微斗數全書/卷三)：卷三谈星要论 |
| [ziwei/major-stars](../../../../mingjing_core/skills/ziwei/02_major-stars.md) | 十四主星：性质、组合与条件；只读已登记字段 | [《紫微斗数全书》](https://zh.wikisource.org/zh-hant/紫微斗數全書/卷一)：卷一诸星问答论：十四主星各问答；仅抽取结构方法，不复述祸福断语 |
| [ziwei/mutagens](../../../../mingjing_core/skills/ziwei/03_mutagens.md) | 四化与飞星：起点、落点和时间层；含待接入项 | [《紫微斗数全书》](https://zh.wikisource.org/wiki/紫微斗數全書/卷二)：卷二安禄权科忌四星变化诀（论生年干） |
| [ziwei/combinations](../../../../mingjing_core/skills/ziwei/04_combinations.md) | 宫位组合与三方四正；只读已登记字段 | [《紫微斗数全书》](https://zh.wikisource.org/zh-hant/紫微斗數全書/卷三)：卷三谈星要论；[《紫微斗数全书》](https://zh.wikisource.org/zh-hant/紫微斗數全書/卷一)：卷一斗数发微论、斗数准绳 |
| [ziwei/time-layers](../../../../mingjing_core/skills/ziwei/05_time-layers.md) | 大限、流年与流月；只读已登记字段 | [《紫微斗数全书》](https://zh.wikisource.org/zh-hant/紫微斗數全書/卷三)：卷三论大限十年祸福何如、论二限太岁吉凶、论流年太岁吉凶星杀；禁用危险事件断语 |
| [ziwei/misreadings](../../../../mingjing_core/skills/ziwei/06_misreadings.md) | 紫微常见误读与未知时辰；只读已登记字段 | [《紫微斗数全书》](https://zh.wikisource.org/zh-hant/紫微斗數全書/卷三)：卷三论人生时要审的确；定小儿生时诀只作为不能沿用的历史反例；[《紫微斗数全书》](https://zh.wikisource.org/zh-hant/紫微斗數全書/卷一)：卷一斗数准绳关于不能一概论议的讨论 |
| [astro/natal](../../../../mingjing_core/skills/astro/01_natal.md) | 行星、星座与宫位；只读已登记字段 | [Ptolemy, Tetrabiblos (Robbins 译本)](https://penelope.uchicago.edu/Thayer/E/Roman/Texts/Ptolemy/Tetrabiblos/1B*.html)：Book I §§4、10–11、17：行星性质、季节与星座守护；不提供Placidus或外行星依据 |
| [astro/aspects](../../../../mingjing_core/skills/astro/02_aspects.md) | 相位、容许度与条件；只读已登记字段 | [Ptolemy, Tetrabiblos (Robbins 译本)](https://penelope.uchicago.edu/Thayer/E/Roman/Texts/Ptolemy/Tetrabiblos/1B*.html)：Book I §13 Of the Aspects of the Signs、§24 Of Applications and Separations |
| [astro/transits-progressions](../../../../mingjing_core/skills/astro/03_transits-progressions.md) | 行运与次限推运：区间和技术分开；含待接入项 | [Ptolemy, Tetrabiblos (Robbins 译本)](https://penelope.uchicago.edu/Thayer/E/Roman/Texts/Ptolemy/Tetrabiblos/1B*.html)：Book I §24：入离相概念，仅支持概念区分；不支持本项目次限算法；[Alan Leo, The Progressed Horoscope](https://www.astro.nu/wp-content/uploads/The-Progressed-Horoscope-Alan-Leo.pdf)：附录IV Summary of Measures of Time：One day measures a year；区分平均日/真太阳日变体，不继承宿命断语 |
| [astro/returns](../../../../mingjing_core/skills/astro/04_returns.md) | 太阳回归盘：时刻、地点与比较；含待接入项 | [Ptolemy, Tetrabiblos (Robbins 译本)](https://penelope.uchicago.edu/Thayer/E/Roman/Texts/Ptolemy/Tetrabiblos/1A*.html)：Book I §§1–3：计算与解释边界背景；不作为回归求解或地点选择的出处；[William Lilly, Christian Astrology (1647)](https://www.worldastrology.net/wp-content/uploads/2008/12/CA-III.pdf)：Book III, Chapter CLXXII Of Revolutions，原书pp.734–737：太阳回到本命黄经与本命盘比较；不沿用疾病灾祸断语 |
| [astro/misreadings](../../../../mingjing_core/skills/astro/05_misreadings.md) | 西占常见误读与证据边界；只读已登记字段 | [Ptolemy, Tetrabiblos (Robbins 译本)](https://penelope.uchicago.edu/Thayer/E/Roman/Texts/Ptolemy/Tetrabiblos/1A*.html)：Book I §§1–3：认识范围的历史讨论；现代实证边界是项目要求 |
| [tarot/major](../../../../mingjing_core/skills/tarot/01_major.md) | 大阿卡纳：象征主题与牌面版本；只读已登记字段 | [A. E. Waite, The Pictorial Key to the Tarot](https://www.sacred-texts.com/tarot/pkt/pkt0303.htm)：Part III §3：大阿卡纳牌义；只作传统来源，不继承灾祸断语 |
| [tarot/minor](../../../../mingjing_core/skills/tarot/02_minor.md) | 小阿卡纳：四花色、元素与数字；只读已登记字段 | [A. E. Waite, The Pictorial Key to the Tarot](https://www.sacred-texts.com/tarot/pkt/pkt0302.htm)：Part III §2 The Lesser Arcana；[A. E. Waite, The Pictorial Key to the Tarot](https://www.sacred-texts.com/tarot/pkt/pkt0304.htm)：Part III §4：追加牌义；元素数字词为项目编辑概括 |
| [tarot/court](../../../../mingjing_core/skills/tarot/03_court.md) | 宫廷牌：角色方式而非固定人物；只读已登记字段 | [A. E. Waite, The Pictorial Key to the Tarot](https://www.sacred-texts.com/tarot/pkt/pkt0302.htm)：Part III §2：四花色宫廷牌；不采用历史外貌/性别判断 |
| [tarot/spread](../../../../mingjing_core/skills/tarot/04_spread.md) | 牌阵与位置：问题、上下文和固定牌；只读已登记字段 | [A. E. Waite, The Pictorial Key to the Tarot](https://www.sacred-texts.com/tarot/pkt/pkt0307.htm)：Part III §7 An Ancient Celtic Method of Divination；产品reflect3等不是该原牌阵；[A. E. Waite, The Pictorial Key to the Tarot](https://www.sacred-texts.com/tarot/pkt/pkt0306.htm)：Part III §6：读牌方法背景；24小时守卫是项目规则 |
| [tarot/relations](../../../../mingjing_core/skills/tarot/05_relations.md) | 牌间关系：支持、张力与反例；只读已登记字段 | [A. E. Waite, The Pictorial Key to the Tarot](https://www.sacred-texts.com/tarot/pkt/pkt0305.htm)：Part III §5 The Recurrence of Cards in Dealing；不沿用必然事件列表；[A. E. Waite, The Pictorial Key to the Tarot](https://www.sacred-texts.com/tarot/pkt/pkt0306.htm)：Part III §6：读牌方法 |
| [tarot/reversals](../../../../mingjing_core/skills/tarot/06_reversals.md) | 逆位的几种读法；只读已登记字段 | [A. E. Waite, The Pictorial Key to the Tarot](https://www.sacred-texts.com/tarot/pkt/pkt0303.htm)：Part III §3：含各牌Reversed条目；[A. E. Waite, The Pictorial Key to the Tarot](https://www.sacred-texts.com/tarot/pkt/pkt0304.htm)：Part III §4：追加意义；过程性四类为项目编辑读法 |
| [tarot/misreadings](../../../../mingjing_core/skills/tarot/07_misreadings.md) | 常见误读与自主决策；只读已登记字段 | [A. E. Waite, The Pictorial Key to the Tarot](https://www.sacred-texts.com/tarot/pkt/pkt0306.htm)：Part III §6：历史读牌背景；自主决策、危机边界与防依赖均为项目规则 |

## 接口边界

- U12 35条均映射到八字章节；其余体系暂无本批rule_id。r#由主线分配，示范别名不能当实际依据。
- U2八字/data/p8/time_interactions、紫微/data/p8_time_interactions已核验；宫干飞化未接入。priority/domains/palace为项目检索排序标签，传统宫位含义原刊出处存疑。
- 连续行运显式transit_period时挂/data/p8_transit_windows；conditional_fields不强求默认artifact。次限与太阳回归只给历史方法出处，计算尚未接入。
- U3 profile_proposal真实生成多分支版本化只读提案，status=calculation_proposal_not_persisted、writes=0；k=3模型自一致投票、数据库档案与资料确认接线归主线。
- 新时间入口P8ChartAdapter.time_basis只核对reported准确时刻，profile_update_allowed/life_event_scoring_performed均false；workbench新字段仅列pending，不测试已撤下的旧.rectify。
- 单次完整context最多5,500 UTF-8字节，作为6k tokens保守代理，非实际模型tokenizer实测或任意tokenizer上界；主线必须再按实际模型预算验证。

## 验证

与rules-review.md相同定向命令：**131 passed，5.23s**；Ruff E/F/I/B/UP/SIM与格式检查通过。
含真实Charts三体系/连续行运、U3提案、time_basis Pointer核验、目录穿越/超预算/元数据只读与全部rule_id章节覆盖。
单个time_basis测试显式用Core锁定tzdata作为PYTHONTZPATH测试桥，未修改共享环境；模型key空，未发真实请求。
未验证Agent工具、主线r#注入、实际模型tokenizer、PG档案持久化、前端/飞书流程、传统方法外部效度。来源仍需用户抽查，公开转录不等于原刊校勘。
