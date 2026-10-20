# U12规则条件断言检查：本机定向交付

记录时间：2026-10-21T00:45:49+08:00，北京时间。工作分支v4/p8-calc。
对应18号P8推理增补§A5及33号第二节第2项；主线Registry/review接入未实现。

## 接口和兼容决定

新增独立公开接口`check_u12_rule_assertions(answer_text, chart_compute, *, expected_scope=None)`，
版本`p8-u12-rule-assertions-preview-v1`，模块位于skills，未修改charts或排盘方法指纹。
原六类`check_chart_consistency`、四个实现文件、v1 Schema、三份旧样例保持不变。
新字段`u12_rule`不属于严格旧Schema；选择独立API、版本、Schema与样例，主线需要分别调用。
没有一边增加旧枚举一边声称严格旧读者完全兼容。

支持完整ID/完整原生名称的“条件命中/未命中”，以及五个有限同透短名的明确肯定和直接否定。
从当前真太阳时primary原生`rule_assessments[].met`取事实，不由文本重新排盘或推断命理效力。
完整夺食、枭神夺食、有效制杀、已成格和伤官配印等强结论留待复核；met只授权本条计算条件。
没有扩展通用语义召回，也没有以同透条件替代格局成败。

## 静态登记、原生载体与依据

只读现有`charts.rules.registry.load_registry()`加载的实际38条本地登记。
输入版本须等于当前登记版本，ID须确实登记，name、condition_ref、parameters、school、source、
notes等全部静态元数据按有限JSON内容hash严格一致；合法ID形状或资料自报名称不能注册新规则。
这不是主线KnowledgeRegistry接入，不改变原生计算规则。

met须为真正bool，不能用0/1代替；主分支内ID和名称须唯一。true assessment必须与同盘同ID
唯一hit整行相等，false不能带同ID hit。实际evidence_paths逐个解析，坏载体或多分支意见冲突
留needs_review。只有成功校验的完整名称允许暂时遮罩，保护其分号/流年等标识符不被误拆。

每次成功核对附实际assessment、met与底层路径，保留原生school/source、condition_scope和notes。
false仍须有真实c，并保持`input_r_aliases=[]`；true只用同document/branch/version/ID的真实r。
c可覆盖assessment数组等实际祖先对象，不写死c3。顶层c/r绑定本次比较或守卫的项目规则，
`data.input_aliases/input_citations`保留原盘命名空间；主线不能混用短别名。
内容hash不是签名或鉴权；预期scope只严格比较上下文，provider、owner、撤销账本仍由主线负责。

## 实跑过程与测试决定

首轮251项新增测试248通过、3失败，三处是新夹具假设，不是据失败放宽保护：

1. “true缺hit”夹具删除hit后仍留悬空view/c引用，导致重算夹具本身失败。修复夹具时一并移除
   已被删hit的引用，再由被测API验证原生hit/assessment不一致；不绕过输入完整性。
2. false依据错误地预设固定c3，实际合法最具体c13覆盖assessment数组。改为核对真实祖先引用。
3. “无c”只删除c3，仍留合法覆盖c13。改为删除全部覆盖本断言的c，继续要求缺证据不能核对。

原495项测试没有改写。上述更正经root确认，记录为夹具事实修正，未修改旧行为契约。
随后补入未知ID、同ID错误condition_ref、改名/参数/流派/来源等重算hash边界，共267新例与
495旧例，762/762通过。

root静态指出未选无效行name可能污染遮罩，这一提示本身不算历史实测。
本子代理随后新增两项重算合法hash反例：把未选行改名“如果”或“对方”，后半句有真实规则ID。
修前实跑两项均失败，误报inconsistent；证据`private/p8-validation/u12-guard-before.xml`。
实现改为只遮静态登记和原生载体校验均通过的完整label，无效行不参与label探测和遮罩，保留正文守卫。
原新增断言不变，修后并入全套回归。

最终1个Core进程：**764 passed，0 skipped，18.44秒**。
Junit：`private/p8-validation/u12-final.xml`。没有跑Charts或声称本次已经完成全量v4。

| 测试文件 | 参数化案例数 |
| --- | ---: |
| test_p8_u12_rule_assertions | 207 |
| test_p8_u12_assertion_boundaries | 52 |
| test_p8_u12_assertion_contract | 10 |
| 原五个consistency文件 | 495 |

新269项含38条ID各true/false断言、38条完整名称两种写法、5个短名与8种肯定/否定运算，
另有保守守卫、未知/相似名、别名串用、缺c/r、坏载体、重算hash、静态登记、scope与新旧Schema边界。
这是受信met与有限文本的一致性测试数，不是独立专业题库分数、自然语言召回率或传统命理效度。

## 格式、契约、样例与性能

7个新Python文件Ruff与88列format全部通过；硬预算逐文件AST核对如下：

| 文件 | 行数 | 最长函数 | 最长行 |
| --- | ---: | ---: | ---: |
| consistency_u12.py | 111 | 38 | 84 |
| consistency_u12_eval.py | 169 | 54 | 88 |
| consistency_u12_input.py | 208 | 45 | 87 |
| p8_u12_assertions_context.py | 70 | 21 | 88 |
| test_p8_u12_assertion_boundaries.py | 286 | 35 | 88 |
| test_p8_u12_assertion_contract.py | 139 | 23 | 98 |
| test_p8_u12_rule_assertions.py | 145 | 16 | 92 |

独立契约`u12_rule_assertions.md`、自包含Schema及`u12-assertions-ayuan.json`。
阿远原盘未重算，合成短答有错误条件、正确true条件、正确false条件及未评估强结论各一项。
最终公开API结果与样例对象完全一致；旧四模块/旧Schema/旧三样例`git diff --exit-code HEAD`为零。

最终性能文件`night28-u12-assertions-performance.json`以同一个Core公开API预热1次、观测10次，
含verified_input与本地静态登记核对；中位**22.798ms**，最小22.501ms，最大24.697ms。
绑定当前三模块、复用四模块/learning_input/tool_evidence、本地registry loader及规则JSON的LF SHA。
输入LF SHA：`8f8e8dafb6ee9ad4cfd9fc6042b10def0f1ed660a7c91f6b440964c020bbb28a`。
最终consistency_u12_input.py LF SHA：`d17934c721f146195b1ad84f85c3d780902370cb933398d74354f5e641bd6d64`。
性能是热进程局部观测，不含原生Charts、解释器启动、主线鉴权/撤销和模型，不作生产SLA。

## 未验证与交接

主线Registry/review#15/P6/两个checker合并、真实鉴权撤销、一般自然语言、真实模型表现和现实效度
未验证。低召回保守待复核；no_contradiction_found不等于全文验收通过。
真实模型、网络、数据库、服务器、飞书请求均为0；未改v3、web或其它工作树，未提交/推送。
父代理安排独立审阅、全量回归及发布；独立审阅未完成前不冒称已通过。

## 独立审阅补充

独立代理在作者定向回归后新增`test_p8_u12_independent_review.py`，25/25通过、0skip、1.02秒，
没有修改作者源码。其中17项载体变更均重算内容hash，覆盖未选坏行name对标题守卫、
共同篡改true assessment/hit登记、r版本/ID/met类型、scope类型、跨句引用/比较/他人/反讽
以及条件语句旁边另写成格结论；未发现需要再改源码的新反例。
作者269、原495、独立25分别是测试集合，后者不混称已经并入此前764项的同一实跑。
独立证据由该代理另交父代理；本报告只登记其已收到的25项结果。
