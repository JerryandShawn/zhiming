# P9 官方协议候选（26号核实后的只新增实现）

## Purpose / Scope

按26号§8十一项实现新版卡片与CardKit纯候选，所有协议结论来自大脑2026-10-20核实文档及其具名官方链接。唯一目录zhiming-v4-mod，分支v4/mod-organize；启动基底8c554bd已有文件仍不改。新增v3入口，不连接飞书/服务器、不读凭据、不发模型或业务请求、不下载、不合并。

## Progress

- [x] (2026-10-21 01:58 +08:00) root/core/calendar完整读26全文、§8十一项与§7十个未说明项；旧cards/CardKit与Q6只读核对。
- [x] (2026-10-21 01:58 +08:00) 前一轮334源冻结及覆盖结束，119新增产品行92.01%/分支80.07%/综合88.84%，原始报告保留；允许新增独立v3文件。
- [x] (2026-10-21 07:32 +08:00恢复复核) root：共享严格ID/seq/uuid契约；七类新builder，63目标测试与1000随机Unicode，Ruff/format通过；原调用的实际结果保留，不伪造空档时间。
- [ ] core：纯wire/error/sequence、双步finalize/close、retry/unknown/restore、Q6租约/双freshness与命名空间CAS。
- [ ] calendar：先冻结独立规范矩阵，再独立目标验收；旧200卡片、Q6规则继续回归。
- [ ] root/acceptance：新builder与wire/reset/尺寸组合、接线与官方链接/未说明项、性能、合法窗口回归、分项提交推送。

## Surprises & Discoveries

02点后代理相继报告账户额度限制，至07:28用户continue恢复，未有持续开发与推送；小时logger仍写实际观察，但这些不是每小时开发完成证据。40分钟checkpoint要求在该空档未达，保留事实。大参数pytest默认ID导致Windows路径/冗长输出错误，显式短ID修复的是测试基础设施，不改变产品断言。

旧CardKit的单close与Q6 close确认即终结，不能把finalize伪装成旧close再继续settings；需新增v3编排，两步各有序号、操作与ACK。Q6当前只接受成功run/完整验证payload，v3不能据此声称真正运行中初稿已授权流式；需主线另行设计可信运行时协议，旧门禁不放松。

26允许修改模块线旧文件，但用户本次只新增约束更严格。故旧“待核实”注释不会全树消失；验收范围明确新v3，旧入口由主线后续接线/退役，不能声称全树grep清零。26的10002永久参数拒绝与泛化的close拒绝重试一次存在冲突，保留错误分类，不自动发请求；策略意图显式交host处理。

## Decision Log

空offer/reset采用noop_empty，不PUT空content；远端旧文在下一次非空更新前可能保留，不伪称已清空。新占位使用非空状态句。allow_sequence_gaps默认True但官方未证；200810/300317与close拒绝明确要求新号优先，不在unknown后复用序号/UUID。10分钟本地elapsed不能合成ACK或closed，只能建议host finalize/reopen。

工程预算内卡UTF8≤28000字节，最终序列化wire也独立检查≤30000字节，不据此宣称官方KB计数边界已实测。200组件按body组件树计数，文本属性不冒充独立组件；保留最多4按钮/1primary。大回答/依据/晨报降摘要+链接或明确截短提示，安全操作/回执不得静默丢弃。字面字段从原typed输入转义，不能全局反转旧JSON反斜杠。

## Outcomes & Retrospective

07:32恢复后首个发布checkpoint只包含已完成的builder/98旧guard/184冻结规范及此前覆盖报告；v3核心曾30项目标通过，但恢复强校验与独立验收仍在推进，不能将其宣称整体通过。主线真实接线未发生。

当前仅设计/只读准备，v3代码及官方线上接收均未验证；上一里程碑已分项推送bae5512/1b1af60/6ebab4b。本阶段每40分钟有意义checkpoint；全量只每小时45–59分启动，不为等待stage/密钥/离线用户停止。

## Interfaces / Validation

共享`card_limits_official_v3`暴露validate_element_id、validate_card_id、validate_sequence、wire_uuid、SAFE_CARD_BYTES=28000、MAX_WIRE_BYTES=30000、MAX_COMPONENTS=200。新cards_official_v3包保留原七类typed builder的调用形状；主线显式opt-in。core新增cardkit_official_v3包，不改Q6状态或metadata定义，记录自身official_v3子树并保留其他证明。

独立矩阵必须覆盖§8全项，源hash和stage未说明项保留。替身transport与纯状态机不等于真实HTTP/SDK/PG；Webhook验签/长连接身份、3秒HTTP200、平台延时token等按26要求写接线，主线真实路由未接。K3业务token、平台event.token与header.token明确分开，不互作授权。
