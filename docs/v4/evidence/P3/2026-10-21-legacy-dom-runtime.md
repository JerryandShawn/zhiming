# 原旧页面 DOM / HTTP / 运行版本切换

北京时间2026-10-21 01:41，主P3工作树。真实隔离PG15、原FastAPI/Uvicorn loopback端口、原static/index.html/app.js及vendor Markdown/清理器；DOM实现为仓库已声明锁定jsdom。没有改static/**或web/**，无服务器/供应商推理/飞书操作。

## 实测

    python -m pytest tests/v4/agent/test_legacy_dom_runtime_pg.py -q -rx

最终 **1 passed，1 strict xfailed，10.59秒，0skip、0warning**。这不是完整旧页面验收通过。测试清凭据、关闭追踪、TZ=Asia/Tokyo；Node仅允许显式同源127.0.0.1 HTTP，网页外部资源自动加载关闭。Node/jsdom来自既有锁依赖，无新增包。

普通通过项完整执行原sendChat三轮及loadHistory：

- 原v3通过实际LangGraph/ConsultationService，用FixtureModel替代模型响应，两个模型步骤完成正文。
- 可信RuntimeSettingsService切v4，实际AgentRuntime/Journal/Finalizer、两个脚本模型步骤、memory_write保存1条真实PG事实。旧JS不读取新命名SSE的final，SSE结束后原recoverTurn一次回查即显示完整正文，未触发重发。
- 切回v3后新请求沿原路径完成，旧模型总4步；三条run的runtime/schema严格为v3/core3.0、v4/core4.0、v3/core3.0。其他owner保持v3。
- 历史DOM有三个助手答案节点，旧/新正文都可见；每轮只有一次POST、send按钮恢复、无错误alert。

## 精确失败与交接

加强回执验证后，实际core4信封receipts长度为1、真实fact也存在，但原当前页与历史页的`.memory-notice`都为0；旧`static/app.js:evidenceHtml`只读取memory_receipts。正文中的“已记住”不能作为回执显示证据。

保留独立strict xfail验收：完整三轮/PG/正文基础断言完成后，只有上述精确`LegacyReceiptMissing`异常可被期望；任何其他业务错误仍使测试失败。未来前端适配后XPASS同样失败，需复核并移除标记，不能把它当作100%通过。没有修改既有回归断言或冻结契约。

交前端后续：旧页面兼容读core3.memory_receipts与core4.receipts，仍只显示真实saved回执，不从正文推导；分别验证当前回答和历史恢复。主线不向core4 EnvelopeV1添加未经版本升级的memory_receipts字段，也不写前端独占代码。不能用本证据放行P3 stage。

## 限制

jsdom证明真实DOM节点/旧JS与HTTP交互，不提供Chromium视觉布局、响应式截图或P10验收。探针仅跳过全站开屏其他面板数据拉取，使用原对话/历史函数、真实页面元素和原依赖，不替换对话API或生成手造信封。没有真实模型质量、缓存或真实渠道送达结论。
