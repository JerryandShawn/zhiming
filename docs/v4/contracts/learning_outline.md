# learning_outline v1：纯规则学习要点

Python入口：`mingjing_core.skills.learning.learning_outline(chart_compute, limit=12)`。
它读取调用方已取得并信任的chart_compute v1或v1.1信封，生成便于研习的要点，不调用模型、不排新盘、不写资料。
`limit`为1–30整数，拒绝bool；没有实际可用依据时返回`insufficient_evidence`和空points，不补故事。

## 输入和来源边界

输入沿用[chart_compute](chart_compute.md)的documents/view/aliases/scope结构。
检查有限JSON、document内容hash、claim_id/value hash、scope、严格JSON Pointer、r命中真值、
原生规则版本/分支和evidence_paths与c引用的一致性。主盘来源引用必须可解析。
本函数没有出生资料授权、撤销、主线调用签名或独立历法复算能力；hash可由任意输入者重算，不能证明来源可信。
主线必须先验证真实工具产物、owner/subject/revision及当前权限，不能把用户自报JSON当已授权结果。
它也不替代原生计算请求绑定、主线chart_inconsistency或账本检查。

## 要点生成规则

八字先读实际日柱和日干，说明它是十神参照，不推人格；紫微先区分实际命/身宫地支与宫名；
西占先看实际位置和方法栏，不把几何位置解释为事件。随后按传入r登记顺序列出真实条件，
单项格局条件不能升级为已成格；交界提示保留真实两侧候选，不据此倒推或修改出生时辰。
每项含实际observed、具名school、source_refs、source_ref与可点击的原始c/r引用。
模板只是项目学习表达；传统来源保持原命中字段中的书名/章页或待核状态，不能把模板署名为古籍原句。

## 输出

| 字段 | 含义 |
| --- | --- |
| version / status | p8-learning-outline-v1；learning_only或insufficient_evidence |
| scope | 原信封owner/subject/revision/operation，输入不被修改 |
| points[] | point_id、kind、title、text、observed、school、source_refs、source_ref、c_aliases、r_aliases、citations；规则卡另有limits |
| aliases.c/r | **原登记行的投影**；只返回当前显示要点所用行，不重编号，不按数组序号猜别名 |
| rule_hits[] | 投影所引用的原生met=true命中，原文保留；不是新增传统规则 |
| source_document_ids[] | 原文档ID，仍需在调用方持有的原信封中解析 |
| effects | model_calls=0、writes=0、alias_registry=reuse_input_projection_no_registration |
| limits[] | 本轮引用范围、来源与纯规则表达边界 |

这不是独立的计算账本：输出没有复制全部原生documents，`source_ref`和aliases.ref仍相对**原信封**文档根。
某个c对应整个主盘，卡片从中读取一个字段时仍保留该c原宽度，不假冒新增细粒度依据。
短号仅在原operation上下文有效，主线若换上下文必须重新登记。

拒绝以固定错误标签报告，不回显出生正文：`learning_contract_unsupported`、`learning_scope_invalid`、
`learning_document_hash_invalid`、`learning_alias_content_invalid`、`learning_rule_must_be_true`、
`learning_rule_provenance_invalid`、`learning_rule_branch_invalid`及`learning_limit_invalid`。
所有c/r分支与坐标从原生文档推导；view.primary必须是实际真太阳主盘或实际astro artifact，
诊断盘不能由外层view提升为主盘。畸形request/details统一拒绝，不泄漏底层KeyError/TypeError。
依赖结构不支持时保留错误，不返回假学习卡。Schema另列结构，不代替语义检查。

## 样例与验证

样例采用原三份阿远真实计算合成信封，未另填真实人物资料。
`tests/v4/test_p8_learning_outline.py`检查三体系、真实交界、只投影实际引用、输入不变、确定性、
有限JSON、严格索引、重算hash后仍拒绝false/错分支和证据重定向。
本功能只提供学习要点数据，未接前端研习页、对话术语弹层、Agent工具或主线持久化账本。

离线重放入口（仅Core、无需Charts或模型）：

    python -m mingjing_core.adapters.charts.benchmarks.learning_preview --mode scripted

从原三份输入生成学习卡并验证Schema及确定性；每次性能报告使用新文件名，不覆盖历史观测。
脚本清理模型凭据、关闭追踪、禁止网络与子进程；业务函数本身不读环境或主动查询外部权限。
