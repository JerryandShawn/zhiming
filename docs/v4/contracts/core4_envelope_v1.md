# core4.0 结果信封 v1

冻结来源：02蓝图§3.5和大脑28号第三节。机器契约为 `core4_envelope_v1.schema.json`，它与 `events_v1.schema.json` 中Final所引用的EnvelopeV1来自同一Core类型。所有新读取端须兼容core3.0和core4.0；本切片不声称已完成Hermes、delivery、tarot及网页历史的接线。

必需字段如下：

| 字段 | 内容 |
| --- | --- |
| schema | 固定core4.0 |
| message_id | 已提交的助手消息ID |
| text | 非空最终正文 |
| receipts | 经真实工具/事务回执核验后的公开投影列表 |
| used_fact_ids / used_claim_ids | 本轮依据别名解析出的实体ID，不接受模型自报ID |
| asked | 提问卡或null，结构同ask_user事件（不含事件公共字段） |
| options | 决策卡或null，结构同present_options事件（不含事件公共字段） |
| review | `{state,reasons[{code,severity}],revision_id?}`；状态与代号见events_v1.md |
| usage | 公开计数；不得含推理或私有协议 |

`asked`与`options`缺省时也要显式写null。决策卡包含2–4项，未知项目列入unknowns。提问卡包含稳定ask_id、带ID的快捷选项、allow_free_text、multi与why；旧内部提问参数的slot、changes_conclusion只用于工具控制，不进入公开卡片。

在读取端迁移期间，允许以下明确的兼容投影：`schema_version:"core4.0"`、`answer`（必须与text逐字相同）、`validation:{status:"validated",valid:true,schema:"core4.0"}`、白名单meta（core_run的run_id/operation_id、subject_id、case_ids、structural_warnings）。没有任意扩展对象或隐藏reasoning的通道。core3.0继续读取原answer/validation契约，不能把旧schema_version偷偷改成core4.0。

当前提交构造器 `agent/envelope.py:build_envelope` 已对齐这些字段；默认review明确为 `{state:"skipped",reasons:[]}`，因为受信评审服务尚未接入。模型或调用方不能把passed/revised直接塞进构造器。后续接入受信评审时必须保留一次修订上限与安全提交闸门。

公开receipt仅保留write_status、status、code、id/fact_id/proposal_id/draw_id、kind、revision、affected_ids。它是业务回执，不能仅凭模型说“我记下了”生成。记忆SSE的pending_confirm与内部存储pending_confirmation等状态须在可信适配器明确映射，不能把内部值原样冒充公开状态。

公开usage只含模型步骤/流/重放计数、reported_tokens中的input/output/cache计数、usage_known和offline。缺供应商usage时不捏造actual值。发送预算的estimated/upper_bound/actual会在其专用诊断与中央账本记录，不用正文长度代替token。

落库与发送顺序：实际工具回执/引用/当前租约epoch/撤销/取消检查 → 原子提交助手消息与信封 → final事件。结构正确只证明契约形状，不证明事务已完成；禁止在提交前发final。正在生成的旧稿由text_reset整段替换。
