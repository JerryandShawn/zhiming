# U12独立入口：载体与语境反例复核

时间：2026-10-21 00:48（北京时间）。只读审阅独立 `check_u12_rule_assertions` 三模块、契约、
原信封验证和共享语境守卫；没有修改作者源码、旧六类v1、计算规则或旧样例。
测试仅新增 `tests/v4/test_p8_u12_independent_review.py`；没有真实模型、Charts、数据库或网络访问。

## 新增反例与结果

| 独立保护 | 例数 | 实际结果 |
| --- | ---: | --- |
| 原生true assessment与对应hit一起改school/source/已知但不相符condition/name，或改为形状合法的未知ID，并重算信封、别名内容hash及claim | 5 | 全部needs_review；静态登记字段不相符或未知ID不能自注册；没有输出原生r背书 |
| 未选中的另一行同时改未知ID及name=如果/对方/北京时间/你说，再重算hash；尝试用其名字抹除标题传递守卫 | 4 | 假设、他人、比较口径、引用分别保留，真实true规则也不绕过守卫 |
| alias.scope.revision改true/1.0/字符串1并重算claim | 3 | 固定consistency_chart_invalid；不能用相等数值替代正确类型 |
| expected_scope.revision使用上述三种类型 | 3 | 固定consistency_scope_mismatch |
| true assessment与hit一起改met=1/字符串true/null，并保留原生r条目且重算hash | 3 | 原信封检查先拒绝为consistency_chart_invalid，未进入布尔比较 |
| r的rule_id借用另一登记ID，或rules_version改外来版本，重算claim | 2 | 固定consistency_chart_invalid |
| 跨句引号、北京时间标题、另一人物标题、反讽撤回，所述规则本来确实为true | 4 | 全部needs_review；实际真值不能覆盖语言语境边界 |
| 同句“条件命中”后另加“格局已经成格” | 1 | 第一项matched，第二项needs_review；总体needs_review，不能把部分核对算作完整成格 |

所有变更均作用于合成阿远信封的深读副本，输入来自实际已发布盘面。
其中涉及载体变更的17项均重算真实的document_id/value_sha256/claim_id，未用旧hash失败替代语义或类型保护。
规则条件本身没有重新计算；这些是受信载体的一致性反例，不是38条命理规则的重新验证。

执行前清除API_KEY环境值、关闭模型追踪，仅1Core进程：

    python -m pytest -q tests/v4/test_p8_u12_independent_review.py

结果：**25 passed、0 skipped、1.02秒**。默认Ruff格式及 `E,F,I,B,UP,SIM` 静态检查均通过。
这是本次实际执行的25项，不把作者另报的764项与本次相加冒充一次789项完整运行。
作者此前269项新入口与495项旧接口回归见其独立报告，完整聚合由root按窗口另跑。

## 源码绑定与兼容边界

本次读取后按UTF-8文本/LF计算的SHA256：

| 模块 | SHA256 |
| --- | --- |
| consistency_u12.py | 7d8bf1942539f7b9b678e19f8a279ea0b8c4e46ec3b265fb6a5a48c6941fb1c3 |
| consistency_u12_input.py | d17934c721f146195b1ad84f85c3d780902370cb933398d74354f5e641bd6d64 |
| consistency_u12_eval.py | 054d1306d7a892fe9513bb96fe68dc907cbc74db3deb55e36f22ee6c5becea43 |

旧consistency四模块及旧Schema的工作树diff为空；本审阅未将新u12_rule枚举塞入旧v1接口。
顶层r是本工具的比较/守卫项目规则，原盘r保留在input_aliases命名空间；
不能把顶层met=true读成原生规则都为true，false条件仍不得借其他r背书。

## 未验证与限制

- 本次未发现需改作者源的新失败；已有有限语法、语境守卫不等于一般中文语义理解或召回率保证。
- 载体hash是内容完整性检查，不是签名。静态登记校验拦截自注册/改名/换来源，
  但不重新计算规则条件，也不能证明来自可信排盘进程；调用方仍须核provider、当前owner、修订和撤销。
- expected_scope是严格值/类型比较，不查询权限；主线Registry/P6/review接入、外部授权与实际用户内容未验证。
- 没有重新计算盘面、专业成格判断、真实模型表达或现实预测效度；全量与准确提交CI由root另记。
