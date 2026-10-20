# 塔罗牌阵只读资产契约 v1

资产版本`p8-tarot-spreads-v1`，文件`mingjing_core/knowledge/p8_tarot/spreads_v1.json`。
Schema为同目录文档`tarot_spreads.schema.json`。这是对**现有三种运行时牌阵**的只读交付说明，
不是新的抽牌入口、知识注册表或已上线功能；现有TarotService不会自动加载这个新文件。

## 实际已支持的范围

运行真相源是`hermes/tarot_deck.py:SPREADS`。现有Core的`adapters/tarot.py`直接导入它，
`create_draw`按其中positions确定张数与顺序；`KnowledgeRegistry.tarot_claims`再次逐项核对
整个spread对象、牌数、顺序、label、版本、已翻开状态及牌面快照。本资产逐项映射，未修改这些路径。

| ID / 名称 | 张数 | 固定牌位，按顺序 |
| --- | ---: | --- |
| focus1 / 关注点 | 1 | 此刻值得留意的角度 |
| reflect3 / 梳理问题 | 3 | 当前处境的反思；可能忽视的因素；可尝试的行动 |
| choice5 / A/B 选择 | 5 | 核心诉求；A 的机会提示；A 需核查的顾虑；B 的机会提示；B 需核查的顾虑 |

三者现有spread.version均为`1.0`，共九个位置。本版本没有新增凯尔特十字或其它未接线牌阵。
reflect3不是“过去/现在/未来”，choice5不是输赢算法；不能按张数相似就偷换位置。

## JSON结构与消费顺序

根对象字段：`version/status/school/runtime_supported_count/supported_card_counts/meanings/`
`sources/spreads/reference_policy/pending_review`，全部必填且不接受额外字段。
`status=readonly_handoff_not_runtime_registry`说明这个新资产尚未成为运行时注册源。

`spreads[]`中`id/name/version/positions`与现有SPREADS原样一致，另有：

- `card_count/runtime_supported`：实际张数与现有支持状态，不表示新JSON已经被运行代码读取。
- `purpose/when_to_use`：本项目原创用途和选择建议，不能代替用户确认问题。
- `position_guidance[]`：1起算的position、原label、focus、question、limit、original_editorial与来源ID。
- `options`：choice5要求A/B两项，去首尾空白后须非空、各≤1200个Python字符且不同；其它两种不要求。
- `school_differences/limits/source_refs`：项目方法与边界、出处引用，不补造历史共识。

主线先确认资产版本与Schema，再核本地运行定义和来源SHA是否同版；有差异就停止自动映射，
保留原运行时固定spread快照，记录版本差异。来源hash是变更提示，不是签名或授权。
旧牌阵不可按这个资产的新说明静默改label、顺序、牌面或修订号。

本轮Schema严格约束三种ID、名称、张数、位置原文、guidance顺序及choice5选项，
也拒绝重复ID、虚构source_id、空说明或自称Waite译文的source_type。
真实路径/SHA和跨文件原文一致性由本机测试补足，Schema本身不读取文件、不验证权限或文本效度。
当前没有新增公开加载函数或错误码；主线接入时须在其边界处理版本/Schema/来源漂移错误。

## 原创署名和流派边界

78张牌义仍只在原`knowledge/tarot_meanings.json`维护，正位、逆位、误读与提问均各78条；
本资产只引用该文件的版本和来源，不复制或改写旧牌义。
`zhiming-editorial-2026-10-10-v1`逐牌source.type为`original_editorial`。
这足够说明产品文本的原创署名，不足以声称逐句对应Waite、专家认证或历史原刊校勘。

三种牌阵和新增九位置说明均为项目反思设计；不把公版书的一般引用当作这些句子的出处。
已有七章技能的Waite背景阅读与当前原创牌义署名分开，章节和catalog本轮未修改。
RWS编号、马赛编号、逆位法和时间牌阵各有差异，本版本不自动互换。

`sources[]`逐项有source_id、kind、真实path/locator与支持范围。四个已有本地源绑定
`sha_mode=utf8-lf-sha256`：UTF-8读取、换行规范到LF后再编码的SHA256，**不是磁盘CRLF原始字节SHA**。
原创guidance来源指向本资产本身，不含会造成循环的自身SHA；整份资产SHA另记交付证据。

## 运行状态、引用和表达

这是静态数据，没有owner、draw_id或实际抽到的牌，不能生成实际〔c#〕、〔r#〕、〔t#〕。
`reference_policy.expression_format_only`只是表达格式示意，不含可冒用的编号。
主线须先通过现有服务读取本人已固定、ready、已翻开的牌阵，确认未撤销和版本，再登记真实依据；
示例“这张固定牌在行动位，咱们先挑一件能核实的小事”只有在本轮牌位确实如此时才能使用。

不猜未翻牌、不补牌、不用逆位诊断、不读他人内心、不按牌选择健康/财务/法律结论。
不以“保证”“一定”描述象征结果；现实条件未知时先调查，不能把未知当零风险。
24小时防反复、明确坚持新抽、旧牌复用、更正、删除、原话血缘和授权撤销由主线工具处理。
本资产不执行这些操作，也不因通过127项数据测试就声称防反复接线已验收。

## 验证和剩余工作

专属测试`tests/v4/test_p8_tarot_spreads_asset.py`：纯AST/JSON/Schema，127/127、0skip，
含三种运行定义、九位置、五来源、78牌原文和30种非法数据。它不导入服务、不连DB或模型。
详细证据`docs/v4/evidence/P8/night28-tarot-spreads-review.md`。

未验证：新资产的主线加载与前端消费、真实授权/撤销、24小时策略执行、历史逐牌校勘、图片授权复核、
Agent读牌效果与现实预测效度。无数据库迁移；回滚只需撤回新增只读文件，不改已有抽牌或保存数据。
