# 命盘文本一致性检查器：独立误报边界复核

记录时间：2026-10-21 00:10（北京时间，UTC+08:00）。
范围：`skills/consistency.py`、`consistency_text.py`、`consistency_facts.py`、
`consistency_eval.py`，复用的 `learning_input`，以及
[chart_consistency契约](../../contracts/chart_consistency.md)和Schema。
只新增 `tests/v4/test_p8_consistency_review.py` 与本报告；实现源和契约由原作者维护。

目标为33号命理线第3项的纯函数候选，不是主线review #15已完成接线或真实文本质量验收。

## 独立发现与修后观察

先完整阅读六个断言领域的现有测试及守卫/别名边界，再找未覆盖的误报。
跨句上下文和原生类型两组在初版源中发现可达路径，作者在独立运行前完成收紧；
**本报告不把它们伪称为已保存的修前失败运行。**

| 复核点 | 观察与处理 | 独立修后结果 |
| --- | --- | --- |
| 整句撤回/否定后缀 | 初版先按逗号取出“日主是甲”，可能丢掉后半句“这个说法不成立”。作者加入整句保守守卫 | 4例通过；撤回甲、否定“不是丁”、反讽“才怪”、撤回正确丁都不被当作肯定事实比较 |
| 反讽的实际失败 | 首次独立19例中，“日主是甲，才怪。”实际返回 `inconsistent`，18绿1失败；向root及作者提交最小复现。原断言保留，作者增补明确反讽撤回守卫 | 同19例重新运行全部通过；没有删掉反例或把inconsistent放进允许集合 |
| 他人/口径/引用标题跨句 | 单句守卫不能说明下一句的日主属于谁。测试含小禾、朋友、北京时间、钟表时、引用、旧盘六个上下文块 | 6例通过，后续无主语断言没有被当成当前真太阳时主盘矛盾 |
| 不靠全部跳过获得绿色 | 无其它上下文的“你的日主是甲。”应与合成阿远的实际丁日干矛盾 | 1例保持 `inconsistent`，返回实际expected丁；低召回不等于忽略所有明确错误 |
| 原生bool/int混淆 | 修改西占原生house=true、retrograde=0、longitude=true，重算全部文档ID、值hash与claim，排除仅靠旧hash失效拒绝 | 3例通过；坏类型不成为matched事实，安全拒绝或保持未检查 |
| expected_scope严格上下文 | revision=1.0或字符串"1"不能因值相近等同整数1；额外session键不能当合法四键scope | 3例按固定 `consistency_scope_mismatch` 拒绝；既有作者测试另保护revision=true |
| 内容hash与来源信任 | 把source_sha256改成明确合成的未知provider并重算全部内容hash，保留内部一致的原盘事实 | 仍可完成事实比较；结果limits明确hash不是签名、provider/owner/修订/撤销由主线先核。本例不宣称未知provider已被授权 |
| 两套依据命名空间 | 原盘input_aliases仍是原信封中的实际行；检查结果顶层c/r指向本结果真实checks，逐项重算值hash | 1例通过；文本比较/守卫r含 `p8.consistency.*` 与非命理成立的说明，不混成原盘r |

跨句守卫的收紧属于精度优先的保守策略，可能减少被检查的句子。
代码按明确标题保留上下文，在空行或显式回到本盘真太阳时主盘后清除；
这不是通用中文篇章、他人指代或时间口径理解的证明。已建议作者在契约写明传递/清除边界。

## 验证命令与结果

先清空进程API Key、关闭追踪，只启动1个Core进程，无Charts、数据库或网络。

    python -m pytest tests/v4/test_p8_consistency_review.py -q
    python -m ruff check --select E,F,I,B,UP,SIM tests/v4/test_p8_consistency_review.py
    python -m ruff format --check tests/v4/test_p8_consistency_review.py

首次实际：18 passed、1 failed，0.71秒，失败为上述“才怪”误报。
作者修正后于2026-10-21 00:10（北京时间）复跑：**19 passed，0 skipped，0.61秒**；
Ruff和默认88列格式全通过。没有启动全量回归，也不把作者其它417项或旧全量数字算作本次独立19项。

## 未验证与主线接入边界

- 仅核白名单事实、保守上下文与程序不变量；没有自然语言标注集的precision/recall指标，
  19例通过不能宣称任意否定、讽刺、引用嵌套或指代都能正确理解。
- 成格、唯一用神不由候选筛选授权，既有代码继续待复核；没有添加新的传统命理断言。
- `no_contradiction_found`只表示已识别的断言未发现冲突，不是全文已核、正确或有现实预测效度。
- input hash仅核内部一致；expected_scope仅比较调用方提供的上下文，不能证明provider可信、
  当前已登录owner、subject归属、修订新旧或撤销状态。主线仍必须在调用前完成这些检查。
- 顶层c/r只在检查结果文档有效；原盘c/r须按其document_id另解析。主线应重新登记，不能按短名碰撞拼接。
- 没有真实用户回答、模型请求、HTTP/流式接线、自动阻断/改写、持久写入、外部传输或部署验证。

本次保持 `record_only`；未改旧v3、未启用倒推、未提交/推送/合并。发布与主线集成由root统一处理。
