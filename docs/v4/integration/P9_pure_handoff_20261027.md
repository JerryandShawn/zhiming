# P9纯模块回执与主线接线边界

分支v4/mod-p9，基点e578e2d，Draft PR27。本轮160项定向通过（1.57s），Ruff lint/format通过；真实模型/飞书/服务器请求0。只新增channels纯模块/测试/文档，不改Agent、闸门或现有路由。PR基点相对目标含已有历史差异，采用时只认本线提交与新增P9路径。

| v14指定项 | 已交付 |
| --- | --- |
| 六类卡片JSON | cards_official_v3：回答、提问、决策、记忆回执、固定塔罗、合盘确认；button.value只有t，安全预览、HTML实体转义、update_multi、元素/字节预算。塔罗仅渲染主线提供的固定draw，合盘只出授权询问，均不自行计算/发牌/批准。 |
| 验签与身份 | callback_auth：原始body的timestamp+nonce+Encrypt Key+body SHA256常量时间比较，300秒窗口，验签后AES-CBC/PKCS7解密，重复JSON键/坏密文拒绝，核schema/app/verification token/event_type；长连接入口只供主线已认证SDK使用，不能作为HTTP免签模式。 |
| 去重与幂等 | callback_commands：核当前open_id/chat/message和可信ActionTokenClaim，token消费+唯一命令在内存锁内提交，event_id重放绑定精确指纹，第二张同逻辑动作卡也只执行一次；先toast确认收到，再worker重核权限，结果不明永不自动执行第二次。 |
| 假飞书服务 | tests/v4/mod_p9/fake_feishu.py：进程内卡片保存、加密签名回调、业务副作用记录和结果不明注入；无HTTP服务或外连。 |

## 官方协议与待主线采用

依据26号2026-10-20官方转录；本轮公开站点只返回页面标题，未冒称重新逐字段核实。加密/签名另对照本地固定SDK源码；首选沿用同一个已认证长连接。回调须3秒内HTTP200，只做验签/消费能力/唯一命令；实体卡只回toast，不在callback响应放card.raw。实际业务线程消息、撤销、固定牌select/reveal、合盘用途同意必须由主线当前授权服务执行。

CardKit接线仍归主线：POST /cardkit/v1/cards创建→POST /im/v1/messages发送（receive_id_type=open_id，uuid≤50）→PUT /cardkit/v1/cards/:id/elements/:element/content全量非空文本→PUT /cardkit/v1/cards/:id最终布局→PATCH /cardkit/v1/cards/:id/settings关闭流式并更新summary；后两步各占严格递增int32 sequence。uuid派生≤50、单卡按10QPS更严上限；结果不明不换uuid重发。请求范围均在open-apis下。创建无uuid尤其不能盲重试。

主线token消费与唯一命令须同一PG事务；调用authorize不是认证证明，须从绑定解析owner并重核subject/来源/撤销/同意/固定牌/版本和租约fencing；后台副作用仍需稳定operation账本，unknown先对账。MemoryCallbackCommands只验证纯契约，不提供PG持久/进程崩溃恢复证明。

## 未验证 / 管理员待办

完整05/P9入站图片、富文本、免登、真实流式、CardKit适配器、实际PG并发、平台SDK长连接与真机截图未运行。管理员须配置机器人可用范围并发版，最小消息发送scope、cardkit:card:write、消息读取/更新权限及card.action.trigger；不用申请employee_id。Webhook需Encrypt Key。最低客户端7.20。真实stage验证每次需用户单独授权。

26号§7十项（序号能否跳号、单全量更新能否关闭、空markdown、&转义、实体card.raw、uuid窗口、openid字符集、reply实体卡、锁屏预览、流式频控冲突）仍列平台待验证；不据合成测试解禁。停用未接线模块即可回退，不丢账、不重发unknown、不改变任何真实用户数据。P9纯模块就绪后继续接口契约草稿，不暂停整队列。
