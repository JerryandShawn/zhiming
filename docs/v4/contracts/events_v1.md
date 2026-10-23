# 公开运行事件契约 v1

冻结来源：大脑28号文件第三节，2026-10-20。分支 `v4/p3-agent-runtime`。机器契约为同目录 `events_v1.schema.json`（JSON Schema 2020-12）；Core 类型源为 `mingjing_core/agent/event_contracts.py`，序列化入口为 `agent/events.py`。前端与模块线只读使用；修改字段须另起契约版本，不能各自改名。

本切片冻结并验证公开数据形状及 SSE 编码。运行事件落库、订阅、150ms/40字合并、15秒心跳调度、Last-Event-ID补发与24小时清理仍待后续运行时及模块线接线；文件存在不代表这些路径已上线。

每个事件的内部交换对象为 `{"type": "status", "data": {...}}`，Schema 校验这个对象。SSE 发送为三行和一个空行；`data` 只包含 payload，不再套一层 `type/data`：

```text
id: 1
event: status
data: {"v":1,"run_id":"run-synthetic","seq":1,"ts":"2026-10-17T08:30:00+08:00","text":"正在整理","phase":"thinking"}

```

所有事件公共字段：`v` 固定整数1；`run_id`；`seq` 为每个run递增的正整数；`ts` 为真实有效、显式带 `+08:00` 的ISO时间。ID为1–200个ASCII字母、数字、`_ . : -`，首字符为字母或数字。生产者显式将带时区时钟转为 `Asia/Shanghai`，不读取本机默认时区。恢复时保留原seq，重复事件不生成新seq。连接/心跳/重试不占seq。

| event | 公共字段之外的data | 语义 |
| --- | --- | --- |
| started | thread_id, message_id, area_id?, topic_id?, incognito | 已入队或开始 |
| status | text, phase | phase为thinking/tool/writing/reviewing |
| tool_call | call_id, name, summary | 只发服务器生成的安全摘要 |
| tool_result | call_id, name, ok, summary, receipt? | 不发工具参数、原始结果或私人正文 |
| text_delta | text | 追加正文 |
| text_reset | text, reason, revision_id? | reason=revised/resumed；整段替换，不能追加旧稿 |
| memory_receipt | fact_id或proposal_id, write_status, summary, undo_token?, sensitive | 必须恰有一个非空实体ID；状态saved/pending_confirm/undone/rejected |
| ask_user | ask_id, question, options[{id,label}], allow_free_text, multi, why | 本轮结束；事件对象与最终asked相同 |
| present_options | options_id, prompt?, options[2..4] | 决策卡，与最终options同构 |
| review | state, reasons[{code,severity}], revision_id? | state=pending/passed/revised/skipped；severity为整数1–5 |
| final | message_id, envelope | 已安全提交；message_id须等于envelope.message_id |
| error | code, message, retryable | 固定大写code，message为中文用户提示，不输出堆栈/供应商正文 |

决策卡每个选项为 `{id,title,benefit,cost,risk,reversibility,first_step,unknowns[]}`。`reversibility` 固定 `easy/partial/hard/unknown`。不知道的内容保留空描述并列入 `unknowns`，界面显示“待确认”；不得编造。选项ID唯一。提问选项也是ID唯一，最多4项，自由输入由allow_free_text指定；不能以显示标签作为稳定ID。

评审code采用06号正式P4的15个英文代号：`off_topic`、`time_error`、`memory_error`、`false_receipt`、`unsupported_chart`、`fatalism`、`unsafe_advice`、`crisis_missed`、`over_asking`、`overpromise`、`tone`、`fabrication`、`generic_barnum`、`sycophancy`、`chart_inconsistency`。公开事件只给代号、严重度与修订标识，不含评审原话、reasoning、trace、模型私有协议。评审失败为skipped，前端不弹出评审错误；这不跳过提交安全校验。

心跳严格为 `: ping\n\n`，每15秒一次；不是 `event: ping`，不落事件seq。`encode_sse` 用紧凑JSON并转义正文换行，拒绝NaN/Infinity和额外字段。内层的usage/meta/validation也只允许公开类型规定的字段，不能藏入reasoning或工具参数。

可选字段可以省略或为null；core4的asked/options是**必需字段**，没有卡片时明确为null。JSON Schema校验器须开启`date-time`格式检查；仅做字符串正则不能识别2月30日。JSON Schema不表达跨字段相等或按ID唯一：接收端另核final标识相同、提问/决策ID唯一。Core已做这些语义校验。工具摘要必须由生产者使用固定安全文案生成，凭据正则只是额外拒绝层，不能当通用脱敏器。

Core构造：`make_event(type, run_id, seq, payload, clock=...)`；序列化：`encode_sse(event)`；校验：`validate_event(type, data)`。序号分配器属于后续持久事件接口；调用方不能把未经授权的模型字段当作run_id/seq。契约测试覆盖12类事件、core4形状、跨时区时钟、无效日期、私有字段、四种记忆状态、SSE转义和已发布Schema漂移。
