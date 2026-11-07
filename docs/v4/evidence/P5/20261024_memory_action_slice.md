# P5 记忆确认动作 · 真实服务 WIP

2026-10-24 02:21 +08:00。M08 已能执行：从原始合成来源，通过真实 leased v4 memory_write 生成同一 P3 pending proposal，再由当前 web-action 的原文“以后这类都记”确认。服务严格绑定 owner、人物、提案修订、原话和实际确认原文；没有改写成另一个确认句，没有模型授权旗标。短句只用于 remember_category=true 的明确类别确认。

M08 第一轮类别设置和事件观察断言通过，第二轮保存回执/健康事实计数失败，最终 0/1。未改原评分哈希；范围日期导致的未保存仍需核对，不能把 event 改成 background 或写入预设日期来凑绿。2 次脚本 setup 调用另行披露，2 次后续脚本对话调用，真实供应商 0。第一次驱动读取错字段产生 target_exception，改为真实 approval_consent_id 后消除该异常，失败仍保留。

20 项提案/撤销检查通过；4 项动作驱动检查覆盖真实来源、原文确认、无写重放、错误类别/提案/措辞拒绝；11 项现有 runtime/禁止注入/语料契约补证通过，未跑重复全量。新驱动测试曾将 consent id 误当实体传给 consent_live，纠正新测试 API 用法后 4 passed，没有改变授权规则。

累计分批证据 30/37 通过、M08/KU01/KU02 三项失败、F01–F04 四项未执行，不是一次冻结版本完整验收。仍未记忆2.0就绪。

评测的 owner_settings 只读别名来自真实 owner settings；consent.category_updated 只在真实服务确认和持久化检查后生成 evaluator-only 观察，不冒充已实现公开 SSE/认证路由。尚未接真实产品按钮。
