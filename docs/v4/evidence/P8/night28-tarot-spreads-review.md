# 塔罗78牌署名与现有三牌阵：只读资产交付

记录时间：2026-10-21T00:52:42+08:00，北京时间。v4/p8-calc；对应33号第二节第4项。

## 只读核对结论

完整重读78张牌的正位、逆位、misreading、question、统一source，七章技能、既有78牌审阅，
以及主线application/tarot.py和Core抽牌/声明/对话调用处。78条source均明确original_editorial，
版本zhiming-editorial-2026-10-10-v1；这能说明项目原创署名，不能冒充Waite逐句翻译或历史校勘。
当前文本未发现需要替换旧正文的确定错误，保留原78条和七章技能不改。

牌阵已经存在，真相源为`hermes/tarot_deck.py:SPREADS`，不是本轮首次实现抽牌：

| ID | 张数 | 实际位置 |
| --- | ---: | --- |
| focus1 | 1 | 此刻值得留意的角度 |
| reflect3 | 3 | 当前处境的反思；可能忽视的因素；可尝试的行动 |
| choice5 | 5 | 核心诉求；A 的机会提示；A 需核查的顾虑；B 的机会提示；B 需核查的顾虑 |

Core TarotService.create_draw直接读这些定义，choice5要求不同的非空A/B文本；
KnowledgeRegistry.tarot_claims核对固定spread、版本、牌数、顺序、已翻开状态与快照。
application/tarot.py负责撤销血缘和checkpoint清理，均只读。本轮没有替代或重新实现这些状态逻辑。

## 新增交付

`knowledge/p8_tarot/spreads_v1.json`把当前三种定义原样映射为只读资产，补上九位置的原创提问、
用途、限制、选项要求与流派差异。三者都不是历史权威牌阵的重新命名，不新增未接线牌阵。
资产明确readonly_handoff_not_runtime_registry；旧服务/Registry没有自动切换读取本文件。

契约`docs/v4/contracts/tarot_spreads.md`和自包含严格Schema：三ID/名字/数量/标签及顺序、
choice5选项、guidance索引、来源种类与唯一ID均受约束。另用AST逐项读现有SPREADS、MAJOR/MINOR
等字面量验证跨文件一致性，不导入服务或执行抽牌。

四个已有本地出处绑定UTF-8读取后LF规范化SHA，明确不是Windows CRLF原始字节摘要。
九位置新说明署名为本版本original_editorial，来源指向自身资产，避免自己嵌自身hash的循环。
静态数据没有实际draw、owner或claim，不生成c/r/t编号；表达示意要求主线运行时真实注册。

## 实跑与不变量

一个Core进程运行专属`test_p8_tarot_spreads_asset.py`，**127 passed，0 skipped，0.28秒**。
Junit：`private/p8-validation/tarot-spreads-final.xml`。

| 测试内容 | 参数化数 |
| --- | ---: |
| Schema与支持数量 | 1 |
| 三牌阵原样映射 | 3 |
| 九位置顺序、标签、原创限制 | 9 |
| 五来源实际路径和四份LF摘要 | 5 |
| 78牌正逆位/边界/问题与legacy文字逐项相等 | 78 |
| 唯一牌ID、分组、来源引用与无伪别名 | 1 |
| 非法牌阵/顺序/选项/源码署名/来源/额外字段拒绝 | 30 |

没有用运行时服务替身证明状态流程，也没有把Schema通过说成塔罗预测有效。
新测试188行，最长函数24行、最长行88字符；Ruff与88列format通过。

旧78牌义、legacy tarot_deck、Core application/tarot.py、adapter/tarot.py、knowledge/registry.py
和七章正文`git diff --exit-code HEAD`为零。本轮未改这些文件、当前catalog或其它工作树。

## 最终LF SHA256

| 产物 | 摘要 |
| --- | --- |
| spreads_v1.json | dad642dd2a6e0513c91b6741968d5ffa4b53356cd74057f922c41dfbff470a9f |
| tarot_spreads.schema.json | 331e3dc7dc1e3142b58a3c13c8d5af9e98a9491c81ef6a124da398641ad6b41f |
| test_p8_tarot_spreads_asset.py | 571ac8eceb64dae1c9cbef33953f053329d5fdf35b68e1ed22e101a66ead7a1e |

## 未验证与交接

主线/前端读取新资产、真实owner授权撤销、24小时防反复接线、模型读牌、历史逐牌校勘、
图像授权复核与现实预测效度未验证。来源足以说明原创文本，不代替历史逐牌出处表。
既有七章已含方法/前提/流派/误读/表达/出处/待核，本轮未重写或新增章节，也没有宣称通过官方Agent Skills验证。

不新增依赖、公开函数、数据库迁移；回滚撤回新增资产/契约/测试即可，不触碰已有抽牌记录。
模型、网络、服务器、数据库、飞书请求0，未合并、提交或推送。
本批数据/Schema/测试已冻结，交父代理聚合回归和发布；不冒领尚未运行的完整v4结果。
