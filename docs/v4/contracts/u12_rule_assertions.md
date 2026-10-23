# U12条件断言检查：独立契约 v1

版本`p8-u12-rule-assertions-preview-v1`，落实18号推理增补§A5和33号第二节第2项。
这是供主线`chart_inconsistency`审阅读取的本机纯规则候选，不是已接入Registry或P6。

## 独立接口与兼容决定

    check_u12_rule_assertions(answer_text, chart_compute, *, expected_scope=None)

入口`mingjing_core.skills.consistency_u12`。原六类断言API
`check_chart_consistency`及其v1 Schema、三份旧样例不变；主线需要显式调用两个接口。
**严格旧读者不能读取新的`u12_rule`字段**，因此没有在旧契约扩枚举或宣称旧读者完全兼容。
本接口有独立版本、Schema、样例和证据。整合后的主线审阅须区分两个工具的document_id。

复用既有受信信封校验、严格owner/subject/revision/operation预期上下文和语言守卫。
原信封只接受`p8-chart-compute-preview-v1/v1.1`；从native真太阳时primary读取实际
`p8.rule_assessments[]`，不选北京时间/诊断分支替代主盘，不根据自然语言重算规则。
`expected_scope`仍是可选比较，不是鉴权；主线须先核计算provider、当前owner和撤销账本。
内容hash不是签名，重新算出hash不赋予外部授权或使伪造的命理盘变真。

API只读本地固定U12登记表元数据，并比较传入的有限JSON，不调用模型、网络、时钟、数据库，
不保存资料、不改答案。静态读取使用`charts.rules.registry.load_registry()`，
这是现有`knowledge/p8_bazi/rules_v1.json`的只读元数据加载，**不是主线KnowledgeRegistry接入**。

## 支持语法与明确边界

| 输入例式 | 实际语义 |
| --- | --- |
| `规则[u12-combo-hurting-officer-officer]条件命中` | 声明此ID的计算条件met=true |
| `规则[u12-pattern-officer-c1]条件未命中` | 声明此ID的计算条件met=false |
| `规则[伤官见官（仅透干同见）]条件未命中` | 用当前登记表的完整名称定位，必须唯一 |
| `正印格候选/月支藏该十神条件命中` | 原生完整名称，末尾显式“条件命中/未命中” |
| `你这是伤官见官`、`你不是官杀混杂` | 仅有限同透短名的肯定/直接否定，仍只核计算条件 |

可用的五个短名只有`伤官见官/官杀混杂/枭食同透/食杀同透/伤官印绶同透`，
各自映射当前确切ID。`是/这是/出现`表示条件命中；`不是/并非/这不是/这并非/没有出现`表示未命中。
`规则[短名]条件命中/未命中`也按同一固定映射，不模糊查找相似名称，不做同义词模型扩展。
原生完整名称可能包含`流年`、斜线、分号和否定子条件：只有通过本机静态登记校验的
**完整名称内部**才当标识符遮罩，不被拆句或当作另一时间层。无效或未登记行自报的名称
不进入遮罩，也不能删掉“如果”“对方”等正文守卫词；名称外的北京时间、旧盘、他人或
假设等仍触发保守守卫。

不支持的规则、相似名、模糊提及及未知ID返回`not_checked/needs_review`，不会“最相近匹配”。
裸术语如“伤官见官”不等于声明成立；“枭神夺食/食神制杀/伤官配印”的完整效力、
`完整夺食/制杀有效/已经成格`属于未计算的更强结论，必须待复核，不能因同透met=true而放行。
多分句分别报告；一个条件已核不表示旁边的成格或现实结果也已核。

引用、转述、疑问、假设、多重否定、反讽撤回、他人/旧盘/北京时间比较等，
沿用原checker的整句/标题段内守卫。码点偏移、不回显原文、32000码点上限也相同。

## 受信计算载体与静态登记的双重核对

传入信封的规则版本须等于本机当前登记版本，ID必须属于实际38条登记；
name、condition_ref、parameters、school、source、notes等全部静态登记字段按有限JSON
规范内容hash严格匹配。只靠`u12-foo`形状合法、资料自报名字或版本号不能自注册规则。
未来登记版本或元数据变化后，本接口按当前静态源重新核对；未受支持的载体保留待复核。

`met`必须是真正布尔值，不接受0/1、字符串或null。ID/名称在一个主分支内须唯一；
多主分支相同ID有不同met时待复核，不能多数投票。

true assessment须与同一主盘、同一ID的唯一rule_hits行完整一致；false assessment不能在
rule_hits有同ID记录。比较的是原生assessment实际met，不把缺少hit猜成false。
实际evidence_paths也逐个解析，不能因载体hash合法就忽略不存在的依据Pointer。

## 输出、真实依据与两个命名空间

输出Schema：[u12_rule_assertions.schema.json](u12_rule_assertions.schema.json)。
信封仍为`version/scope/document_id/data/rule_hits/aliases/sources/effects/limits`。
`data.status`和`coverage`含义沿用原checker，仅统计被识别的断言，不是语言召回率。

每项`checks[]`保留`field=u12_rule/outcome/reason_code`和真实met的`source_refs`；
成功检查另有`assessments[]`，含确切ID/name、原生version、met、condition_ref、
condition_scope、notes及整行assessment_ref，`evidence_refs[]`列实际底层输入引用。
来源是该原生登记的school/source；不能把效力未判的notes省略后当完整格局成立。

`input_c_aliases`选取原信封中实际覆盖assessment的最具体c，可为整份assessment数组的c；
不固定c3，也不因c覆盖较大对象就改造内容。**false必须仍有真实c，input_r_aliases=[]**；
不会为了引用失败条件新造传统r。
true可复用同document/branch/规则版本/ID的原生r，其底层真实c也一并保留。
未知或不相干的答案引用待复核，不能借另一条true r给false条件背书。

`data.input_aliases/input_citations`始终是原盘命名空间；顶层tool-evidence c/r是本检查
结果自己的临时命名空间，绑定实际比较/守卫记录和`p8.u12_assertions.*`项目规则。
顶层r的met=true只表示比较或守卫命中，不把原生false规则改成true；主线须按document_id登记重映射。

## 状态与错误

单项outcome为`matched/contradiction/needs_review/not_checked`；
总体依次优先`inconsistent/needs_review/no_contradiction_found/not_checked`。
明确矛盾不自动触发重写；所有结果`policy=record_only`。

复用`consistency_answer_invalid/consistency_chart_invalid/consistency_scope_mismatch`输入错误。
不能安全读取已受信字段结构时抛`u12_assertions_chart_fields_invalid`，不含私密正文。
坏载体通常作为待复核而非抛异常：`u12_rule_unregistered/u12_registry_metadata_mismatch/`
`u12_met_not_boolean/u12_identity_ambiguous/u12_hit_assessment_mismatch/u12_false_has_hit/`
`u12_assessment_incomplete/u12_evidence_paths_invalid/u12_version_unsupported`。

合成样例`u12-assertions-ayuan.json`只含人工写的合成短答与真实当前纯函数结果；
原38条规则正反盘计算测试仍属计算层证据，本工具测试只核受信met载体与文本断言的对应。
未验证：主线Registry/P6/工具合并、真实鉴权撤销、一般自然语言语义、模型表达及现实效度。
