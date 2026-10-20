# 学习要点独立审阅：内容绑定与异常边界

记录时间：2026-10-20 23:46（北京时间，UTC+08:00）。范围为本地合成阿远预览，
`learning_outline` 的输入验证、既有依据复用与输出卡片；没有模型、数据库、服务器或外部授权查询。

## 修前复现与修后验证

审阅以 `docs/v4/contracts/samples/ayuan_bazi.json` 为输入。以下五例先在独立私有脚本复现，
由实现者修复共享源后，再整理为 `tests/v4/test_p8_learning_review.py`，没有修改原有测试的断言。

| 独立案例 | 修前实际结果 | 修后实际结果 | 保护的行为 |
| --- | --- | --- | --- |
| 把首张定向卡使用的 c 别名改成外来 `branch_id` 和 `actual_UTC`，重算 claim hash | 接受，生成 11 张卡 | `ValueError: learning_alias_branch_invalid` | c 的分支与口径须来自实际引用文档，不能由别名行自行声明 |
| 把 `view.diagnostics[0]` 放入 `view.primary`，引用仍可解析 | 接受，生成 11 张卡 | `ValueError: learning_primary_view_invalid` | 标准时诊断盘不得提升为真太阳时默认解读盘 |
| 把实际命中规则的 `details` 改成 null，重算全部文档 ID、引用内容 hash、claim hash | 泄漏 `TypeError` | `ValueError: learning_input_invalid` | 内容 hash 有效也不免除结构检查；卡片渲染的坏形状使用固定错误码 |
| 删除 `request` | 泄漏 `KeyError` | `ValueError: learning_input_invalid` | 缺少请求结构时不泄漏底层异常 |
| `request = null` | 泄漏 `TypeError` | `ValueError: learning_input_invalid` | 非对象请求使用固定错误码 |

重算 hash 的测试特意不依赖“文档 hash 过期”来拒绝错误：调用者可以重算普通内容 hash，
所以验证仍要核对原生分支、真太阳时主视图与实际规则证据。修后代码还检查计算包
artifact/profile/feature 的 owner、subject、revision 值及类型；这项为代码审阅观察，
上表五例没有穷举这些对象的全部坏形状。

## 结果及重现

2026-10-20 23:45（北京时间）仅启动 1 个 Core 检查进程，无 Charts 子进程：

    python -m ruff format tests/v4/test_p8_learning_review.py
    python -m ruff check --select E,F,I,B,UP,SIM tests/v4/test_p8_learning_review.py
    python -m pytest tests/v4/test_p8_learning_review.py tests/v4/test_p8_learning_outline.py -q

结果：格式未改变；Ruff 全通过；**29 passed，0 skipped，0.77 秒**，其中独立审阅新增 5 例，
原有 24 例仍通过。运行前清空进程 API_KEY 环境值并关闭模型追踪，没有输出密钥值。
本次定向检查没有替代主线的全量回归、CLI 最终采样或生产验证。

## 依据与推理边界

审阅文件为 `mingjing_core/skills/learning.py`、`learning_input.py`、
`docs/v4/contracts/learning_outline.md` 及 schema、原有 24 例、handoff 引用生成与验证代码。
定向卡使用输入盘的实际日干、命身宫或行星位置；规则卡只接受已有 `met=true` 的命中，
保留原 c/r 别名、来源引用和规则版本，单项条件不升级为成格判断。
边界卡复用已有真实候选四柱，不启用冻结的倒推功能。

**外部来源与授权仍由调用方保证。** 内容 hash 不是签名；本函数核对输入内部一致性，
没有证明输入来自可信的计算进程，也没有查询当前用户、跨 owner 权限、修订新旧或撤销账本。
即使整份输入在内部一致且可重算 hash，也不能据此宣称其已获授权或是真实用户资料。
只有调用方已核验来源、当前 scope 与授权后，才适合把它交给这个纯规则学习模块。

未验证：任意恶意 JSON 形状的穷举、上游授权接线、真实用户数据、模型解读质量及命理预测有效性。
本审阅没有新命理规则、运行时写入、数据库迁移或外部传输。

## 最终增补复核

2026-10-20 23:55（北京时间）：实现者补充原生文档 revision 的值和类型同时校验，
并新增重算全部 hash 后把整数 revision 改成 bool 的反例，拒绝为
`learning_document_scope_invalid`。保留上述29例历史结果，不将其改写为修后的最终计数。

学习模块、独立审阅和离线重放 CLI 三组共 **39 passed、0 skipped、2.19秒**。
最终代码的1次预热+10次观测另存 `night28-learning-performance-final.json`，
该文件绑定原三份输入及最终源码 hash；八字/紫微/西占中位分别20.37615/15.609/15.57525毫秒，
不含文件读写、序列化、Schema验证，不是排盘/HTTP/模型耗时或生产SLA。

2026-10-21 00:09（北京时间）：root额外检查别名行scope，发现普通dict相等会把别名revision=true
视为原信封revision=1；即使claim可重算，别名scope仍必须值和类型均一致。
新增`_same_scope`与独立反例，不改变合法学习卡内容；审阅反例现在7/7、0skip、0.27秒。
该最终scope代码性能另存`night28-learning-performance-scope-final.json`；以前观测按各自源码hash保留，
不将23:55代码的性能报告误标为00:09代码。调用方来源授权与撤销仍未接线。
