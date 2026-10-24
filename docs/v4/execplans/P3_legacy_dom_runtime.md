# P3：旧页面真实 DOM 与本机三轮切换

本片遵循 `.agent/PLANS.md`，时间按北京时间。只新增后端验收测试，不改 static/**、web/** 或其他线工作树。

## Purpose / Big Picture

使用原 static/index.html、原 app.js、原 Markdown/清理依赖，在真实 DOM 实现中执行原 sendChat 与历史显示；通过真正的 loopback HTTP 访问当前 Core 和隔离 PG。两种模型为显式离线替身，v3 使用实际 LangGraph 和旧服务，v4 使用实际 AgentRuntime，路由通过新管理应用服务切换。避免把 API200 或手造信封当作页面验收。

## Progress

- [x] (2026-10-21 01:36 +08:00) 审查原网页 SSE、recoverTurn、历史投影及已声明的 jsdom 依赖。新命名 SSE 不被旧解析器逐字消费，但完成后原回查路径可能兼容，待实测。
- [x] (2026-10-21 01:41 +08:00) 原sendChat真实HTTP/PG三轮正文与历史通过；加入实际回执DOM断言后发现旧UI字段缺口，最终1 passed/1 strict xfailed、10.59秒，0skip/warning。不算完整旧页面验收。
- [ ] 记录真实结果、限制、提交与精确头组合回归。

## Plan of Work

创建本机临时端口的 Uvicorn 服务，按真实 owner 进行三轮对话和一次历史加载；Node 只访问显式同源127.0.0.1，测试不允许外部HTTP。DOM 使用已锁 jsdom，真实旧页面代码加载到初始化边界，跳过全站无关的开屏数据拉取，不改对话函数或渲染函数。测试清凭据且东京TZ，业务展示仍按owner时区。

## Validation and Acceptance

必须分别落 v3/core3、v4/core4、v3/core3；新事实有真实PG写入，旧页面显示答案与回执，历史呈现三条助手回答，其他owner不变。新事件靠原回查路径完成时明确记录，不宣称逐字流兼容。jsdom不提供浏览器布局/视觉截图，不宣称P10响应式或真实供应商验收。

## Surprises & Discoveries

原sendChat在未收到旧type=result事件时会recoverTurn，不可仅静态断言新SSE必然让旧页面失败；必须验证完整路径。

01:37首次真实HTTP探针已完成旧v3页面显示和两次离线模型步骤；切换时遇到尚在开发的管理服务SQL路径格式错误，整条测试失败，不计验收通过。服务负责人独立修复后才复跑。HTTP探针显式关闭未使用的WebSocket协议，避免无关WebSocket依赖导入。

## Decision Log

沿用现有npm锁jsdom和仓库vendor，不新加浏览器依赖；管理CLI在独立小片中实现，本测试消费其应用服务，不直接SQL切运行版本。

## Outcomes & Retrospective

两次v3真实旧服务共4次合成生成，v4真实AgentRuntime两次脚本生成与一次PG事实保存；三轮固定v3/core3、v4/core4、v3/core3，旧history三个助手节点。原JS不消费新命名SSE，通过完成后的原recoverTurn一次回查显示新答。没有服务器、真实供应商、飞书或部署操作。

强回执用例确认：core4持久receipts含1条真实回执，但旧当前页与历史页的.memory-notice都为0，原UI仅读memory_receipts。保留strict xfail，只允许这个已精确观察的LegacyReceiptMissing类型；其他HTTP/PG/路由/正文断言仍普通失败。未来修复后XPASS会使测试失败并要求移除标记。主线不改前端独占文件，也不向冻结core4偷偷加新字段。详见evidence/P3/2026-10-21-legacy-dom-runtime.md；缺口交前端，保持P3验收未完成。
