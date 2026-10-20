# U41：无法通过模型输入守卫时仍有程序兜底

记录：2026-10-21 00:36 +08:00。

真实模型尚未配置可核验输入计量时，危机轮原先可能在构建快照、或在Loop发送守卫抛InputMeterUnverified，导致既没有发模型，也没有给兜底模板。本片在两个边界都处理ContextInputError。只有已识别危机才转固定程序模板；普通对话继续拒绝未核验的模型输入，不用替身计量放行真实请求。

模板路径重新核当前租约、owner/subject/thread、取消、有效当前用户原话与撤销账本；只登记模板实际需要的原话版本，经同一AgentFinalizer提交core4与最终事件。没有供应商请求或临时拼造工具回执。source/lease错误仍停止，不能被“失败开放”覆盖。

7项目标真实PG测试通过/3.68s，含measure抛错、meter=None、返回有效TokenReading但live_admissible=False、普通对话仍拒绝、构建过程中取消与原话撤销都不得发布。独立审计发现原首版只捕快照边界的缺口，已加入Loop边界反例。Ruff/format/函数上限通过。此前私密/长期Runtime与该路径21项目标通过/7.51s；计数重叠不相加。

同时在Runtime受信claim后、快照前接已有apply_clarification_answer，跨轮回答/拒答可更新filled/declined；独立Q类真实两轮扩充由M8线复验，不冒称全部Q场景已完成。

真实供应商请求、飞书发送、服务器操作均0；模板可用不证明真实模型质量，也不解除实际K3 tokenizer与上线阻塞。
