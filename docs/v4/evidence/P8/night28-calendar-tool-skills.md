# 28号四章跨体系技能增补

状态：已登记的只读产品技能草稿，不是主线 Agent 或现实预测验收。
目录版本 `p8-skills-draft-2026-10-21-v2.3`。

原四体系 bazi10、ziwei6、astro5、tarot7 全部保留；新增 `calendar-tools` 四章，合计32章。
新增主题为 daily-transit、window-search、almanac、synastry，根对象均为独立 `P8ToolEvidenceResult`。
旧28章仍保留原文和原版本说明，没有把新目录版本冒充旧章节重新审定。

## 变更理由与验证

28号主队列第6项要求四章跨体系工具解释。将其登记到独立体系，避免把紫微/西占流日、公共黄历或合盘误放为单纯八字章节。
`SkillLibrary` 原本支持已登记体系，本轮无需修改 loader。

原 `test_all_systems_have_requested_chapter_coverage_and_open_frontmatter` 的计数断言保护四个基础体系的完整性。
此次保留全部原计数，只追加 `calendar-tools:4`；原四体系章节结构、来源、字段、规则映射、预算、拒绝路径与只读保护仍然执行。
通用章节测试新增calendar-tools参数，使新章也完整接受同样检查，没有为新章减小验收范围。

    python -m pytest tests/v4/test_p8_calendar_tool_skills.py tests/v4/test_p8_product_skills.py -q

结果：**20 passed，0 skipped，0.15秒**；两测试文件 Ruff E/F/I/B/UP/SIM 与88列format通过。
专属测试使用实际计算的10-21 almanac样例核验字段和六个真实rule_id。
其它三工具的完整原生字段/Agent接线效果须随对应计算里程碑验证，不将文档登记说成计算已经通过。

## 上下文预算

| 主题 | 完整技能context UTF-8字节数 | 上限 |
| --- | ---: | ---: |
| daily-transit | 3311 | 5500 |
| window-search | 3291 | 5500 |
| almanac | 3027 | 5500 |
| synastry | 3517 | 5500 |

以上是loader实读的完整上下文，含版本包装和来源，没有截断章节。
UTF-8字节仅为既有保守代理预算，不是模型tokenizer实测。

## 语义边界

每章说明使用时机、输入前提、具名方法差异、反例、老朋友口吻、字段根与出处，末尾均保留待核。
`〔c#〕〔r#〕` 明确只是格式示意，必须根据当前结果的真实rule_id和aliases.r读取实际别名，再解析对应计算依据；
不使用数字示例别名假装当前证据。

合盘章明确consent=user_confirmed在计算之前、失败不泄露对方资料、授权不自动扩展到保存分享；
as_of_date由主线Clock明确注入。四章不恢复倒推，不替用户下关系结论，也不把黄历历史灾祸词搬进正文断言。

## 未验证 / 待核

新三工具全部原生样例字段对照、主线工具注册、真实上下文别名账本、Agent模型表达和现实效度尚不能由此次文档测试证明。
原典版次与纸页待核继续见 `night28-m1-m4-review.md`，未新增编造出处。
本轮模型调用0、无服务器/飞书、无数据库写入；发布与完整分支回归由root按里程碑统一处理。
