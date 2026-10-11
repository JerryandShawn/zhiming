# 明镜 Core 知识包

本包是可执行的初始知识范围，不是已经完成的四体系专家系统。2026-10-11 初始发布有五条受限规则、五个来源登记和完整 78 张原创编辑牌意。传统出处、编辑审核与科学实证分别标注；没有把机器整理写成专家认证，也没有把有古籍出处写成事件预测已经验证。

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

输入契约：`features` 的语义 key 可为 `pillars` 或 `bazi.pillars`；每项至少含 `artifact_id/path/value`。`artifacts` 保存同一个确定性产物的 `owner_user_id/subject_id/revision/branch_id/system/school_id/time_scale/data`。`context` 必须由服务端提供 `owner_user_id/subject_id/revision/branch_id/time_scale`。`school_id` 应从产物所属真实 CalculationProfile 解析，不能由模型补。引用兼容相对 `data` 的 `/pillars` 与完整产物的 `/data/pillars`，不允许用其他同值字段冒充该语义特征。

计算适配器同时保存本命和明确目标层时，产物仍标 `natal_with_explicit_separate_target_layers`。本包只在本轮为 `natal`，且每个必需特征都显式标为 `natal` 时允许读限定本命路径；不会把整个产物改名为本命，也不会把流日/流年字段当本命。每个时间分支分别生成声明，有限采样结果不能写成整个连续区间稳定。

返回值为 JSON-ready 字典：`eligible/status/issues/feature_refs/source_refs`。成功声明还包含规则版本、规则内容哈希、知识包版本、人物与输入版本、时间分支、限定、反对因素、编辑状态和实证状态；`real_world_link_status` 初始为 `not_established`。`claim_id` 由实际内容确定性生成，不接受模型自造身份。可读依据摘要只说明校验范围，不索取或记录隐藏思维链。

本版本未实现完整旺衰、格局、调候、喜用神、独立四化飞宫、多流派格局、精确应期、完整古典尊贵/接纳、推运等知识前提。需要这些能力时保留 `RULE_GAP`，不把初始结构规则宣传成完整精确预测。新版本应新增真实来源、明确流派/时间层、允许解释与程序负例，经测试和发布审核后替换静态包；模型不能在聊天中自行发布规则。

验证命令：`.venv312/Scripts/python.exe -X utf8 -m unittest discover -s tests -p test_core_knowledge.py -q`。当前 20 项测试通过，其中包含真实 `ChartAdapter → lunar-python → 知识前提 → 声明` 链路，以及 78×2 正逆位逐张编辑释义核对。实际模型、真实渠道和生产部署不属于这条命令的验证范围。
