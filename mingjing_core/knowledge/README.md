# 明镜 Core 知识包

本包提供可执行的结构解释范围。2026-10-11 v2 发布有16条受限规则、6个来源登记和完整78张原创编辑牌意：14条排盘结构规则及2条塔罗规则。传统出处、编辑审核与科学实证分别标注；机器整理不等于专家认证，古籍出处不等于事件预测已经验证。

`KnowledgeRegistry.load_builtin()` 只读取版本化本地 JSON，日常问事不联网修改规则。`select(system, topic='general', time_scale='natal', school_id=None)` 按体系、话题、时间层和流派精确筛选。塔罗需显式选择 `time_scale='question'`；现代编辑默认 `school_id='zhiming-editorial-v1'`。选择不到规则意味着不支持，不补一条通用断语。

`evaluate(rule_id, features, context, artifacts)` 先核对服务端范围，再解析真实产物字段，最后执行规则前提。`declare(..., interpretation_id)` 只生成已发布的允许解释；同一个正确字段不能授权“明年必发财”等任意文本。`validate_claim()` 重算声明并拒绝模型改写规则文字、引用或人物范围。现实应用和用户行为须另走核心的事实/事项服务，不能把此处声明写成现实事实。

| 规则 | 原始来源与范围 | 必需计算字段 | 允许解释 | 实际负例 |
| --- | --- | --- | --- | --- |
| `bazi.natal.seasonal-structure.v1` | [《滴天髓辑要·通天论》](https://zh.wikisource.org/zh/滴天髓)：日干与节令结构 | `pillars/day_master/method` | 日主、月柱与完整四柱的分析起点；不靠五行计数断旺衰 | 缺时柱返回 `RULE_GAP`；日主与日干不同返回 `REFERENCE_ERROR`；请求财富保证返回 `UNSUPPORTED_INFERENCE` |
| `ziwei.natal.linked-palaces.v1` | [《紫微斗数全书·卷三·谈星要论》](https://zh.wikisource.org/wiki/紫微斗數全書/卷三)：命宫及迁移、财帛、官禄联读 | `topic_palace/method`，含真实本宫与三联动宫的主辅星 | 同时列出四宫结构并保留化忌等牵制 | 单星无联动返回 `RULE_GAP`；伪造对宫索引返回 `REFERENCE_ERROR`；流年套本命返回 `SCOPE_MISMATCH` |
| `astro.natal.major-configurations.v1` | [Ptolemy《Tetrabiblos》Book I Chapter XVI](https://www.gutenberg.org/files/70850/70850-h/70850-h.htm)：60/90/120/180度配置及传统术语 | `aspects/aspect_orb/method` | 实际相位与限定协调/张力术语；项目容许度明确为现代编辑口径 | 超容许度返回 `REFERENCE_ERROR`；名字与角度不符返回 `RULE_GAP`；只提供合相需独立规则 |
| `tarot.rws.temperance-upright.v1` | [Waite《The Pictorial Key to the Tarot》Part III §3](https://sacred-texts.com/tarot/pkt/pkt0303.htm)：节制正位 | `cards/spread_id/deck_version/status` | 节度、管理、调适的原典概念；不要求牺牲现实底线 | 逆位、其他牌或其他牌系不能套用，返回 `RULE_GAP` |
| `tarot.editorial.complete-deck.v1` | 项目原创编辑资产 `tarot_meanings.json`，保留原 `hermes/tarot_deck.py` SHA256 | 同上 | 实际每张牌与方向对应的原创反思角度；逐张保留常见误读 | 未完成抽牌、重复牌、牌名与ID不符、牌阵数量错误返回 `DRAW_MISMATCH` |

古籍只支持上表所列传统概念，不迁移书中的疾病、寿命、灾祸、阶层价值或性别贬损断语。西洋规则明确把原典的符号几何与项目使用的黄经容许度分开；计算库接口、许可证文档与运行成功都不作为人生断语来源。Waite 原典与本项目现代释义也分别登记，不声称每张编辑牌意都是原典译文。

v2另登记项目原创结构定义 `editorial_definitions.json`，对应下列11条新增规则；明确标为 `original_editorial_unreviewed` 和 `reflection_not_prediction`，不冒充古籍断语或人工专家评审：

| 新增范围 | 实际字段与前提 | 解释边界 |
| --- | --- | --- |
| 八字藏干十神、原始关系（2条） | 完整四柱、藏干表、日主生克阴阳关系；独立重算透藏十神及六冲/六合/天干五合 | 列出实际结构，不用五行数量决定旺衰，不把五合写成合化成立 |
| 八字目标日/节月/节年（3条） | 同一目标日期的正午快照；实际交节区间、立春区间 | daily/monthly/yearly独立声明；公历年初可能仍属于前一个节年 |
| 紫微大限/流年/流月/流日（4条） | 对应 `horoscope` 层的实际宫位索引、干支、四化、12宫名和星曜位置关联 | 本命宫位与该层宫位分别列出；不补飞宫、自化或精确应期 |
| 西占本命位置、目标行运快照（2条） | 完整12宫与有限黄经；行运对实际本命参照的相位几何、日期、时区、容许度 | 本命位置与指定日UTC+8正午快照；月/年连续行运、次限、太阳弧没有规则则明确RULE_GAP |

规则覆盖general、career、study、relationships、decision、terminology、finance、family、home、health、personal_growth的结构视角；`education`显式兼容为`study`。话题可选择结构视角，不能把它当作该人生领域全部技术已经实现。

输入契约：`features` 的语义 key 可为 `pillars` 或 `bazi.pillars`；每项至少含 `artifact_id/path/value`。`artifacts` 保存同一个确定性产物的 `owner_user_id/subject_id/revision/branch_id/system/school_id/time_scale/data`。`context` 必须由服务端提供 `owner_user_id/subject_id/revision/branch_id/time_scale`。`school_id` 应从产物所属真实 CalculationProfile 解析，不能由模型补。引用兼容相对 `data` 的 `/pillars` 与完整产物的 `/data/pillars`，不允许用其他同值字段冒充该语义特征。

计算适配器同时保存本命和明确目标层时，产物标 `natal_with_explicit_separate_target_layers`。每个必需特征都须显式标为当前规则时间层；目标层还须绑定相同目标日期。不会把整个产物改名为本命，也不会挪用流日快照回答整年。每个时间分支分别生成声明，有限采样结果不能写成整个连续区间稳定。

业务服务使用以下稳定接口，owner、subject、revision必须来自服务端授权上下文：

```python
registry = KnowledgeRegistry.load_builtin()
declared = registry.claims_for(calculation_result, owner, subject, revision,
                              topic="study", time_scale="yearly", target_date="2026-10-11")
# {"claims": [...], "gaps": [...], "scopes": {...}, "pack_version": ..., "pack_hash": ...}
tarot = registry.tarot_claims(tarot_adapter.get_for_reading(owner, draw_id), owner, subject, revision)
# 另返回 frozen artifacts/features/context，可供 validate_claim 重验。
```

`claims_for`将计划层natal/daily/monthly/yearly对应实际特征层；`all`供专业附录核查全部已发布结构，`decadal`对应大限。缺少真实profile、版本/分支不符、目标日期不同均拒绝。没有对应解释规则的体系与时间层明确返回RULE_GAP。`tarot_claims`只接受已完成翻牌的ready视图，核对牌阵、标签、位置、稳定牌ID、方向、冻结牌意、版本和上下文撤销状态；资料revision与draw_revision分别保存。它不复制问题文本、私有全牌序或人物档案。

返回值为 JSON-ready 字典：`eligible/status/issues/feature_refs/source_refs`。成功声明还包含规则版本、规则内容哈希、知识包版本、人物与输入版本、时间分支、限定、反对因素、编辑状态和实证状态；`real_world_link_status` 初始为 `not_established`。`claim_id` 由实际内容确定性生成，不接受模型自造身份。可读依据摘要只说明校验范围，不索取或记录隐藏思维链。

本版本未实现完整旺衰、格局、调候、喜用神、独立四化飞宫、多流派格局、精确应期、完整古典尊贵/接纳、推运等知识前提。需要这些能力时保留 `RULE_GAP`，不把初始结构规则宣传成完整精确预测。新版本应新增真实来源、明确流派/时间层、允许解释与程序负例，经测试和发布审核后替换静态包；模型不能在聊天中自行发布规则。

验证命令：在包含`requirements-charts.lock`的隔离解释器中运行 `python -X utf8 tools/verify_core_calculators.py --output core-calculation-validation.json`。2026-10-11共59项通过、零跳过，含全部14条真实排盘规则自动声明及规范声明重验、78×2冻结牌意、时层隔离和篡改负例。测试数是unittest方法数，循环中的牌意逐张核对不虚增为独立测试方法。真实模型、数据库、渠道与生产部署不属于这条验证范围。
