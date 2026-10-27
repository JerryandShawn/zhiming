# P10 补充回执：事件兼容、R7 与旧页性能

- 分支：v4/p10-frontend；运行源码0bc8502；PR #6保持Draft，未合并。
- 计划：web/ExecPlan_resume_2026-10-27.md。已执行指令板v3。
- [x] 52/52相关单测（新增R7 12、事件目录4）；原行为断言未改。类型、定向lint通过。
- [x] 2/2新旧HTML浏览器（390/1440），Axe全规则0，2图。提问/决策/四记忆状态不阻塞final、无额外写操作；旧页显示final提问与输入提示。新前端core4不读取旧回执别名，不把generic ack误当可撤销记忆卡。
- [ ] 旧页4G五冷门槛未过：干净运行源码基线2564–2580ms，p75 2572。预加载候选p75 2588，无收益已撤回；15原图和三个完整批次保留。首批漏登记只读archive，已纠正夹具后重测，不掩盖首批失败。
- [ ] 原core_test_fe:55481连接角色不存在，Docker占用该端口；未停止/修改Docker。日报首段请大脑确认测试库归属，转其他前端项。

关键文件：tests/core4-receipt-boundary.test.ts、legacy-event-catalog.test.ts、legacy-e2e/；scripts/measure-legacy-lcp.mjs。脚本只在临时127.0.0.1端口提供真实HTTP静态资源与合成只读API，网络节流走实际传输，不用route.fulfill；五冷390×844/DPR2、150ms、200000Bps、CPU4、禁缓存，无压缩。候选报告如实有dirty标记；尝试名不是时钟，以batch的北京时间为准。

未完成/风险：不称“旧网页流式就绪”；富决策/回执交互、真实旧页兼容投影、P4 HTTP+PG、新P10当前性能仍待。旧回执投影由主线负责，不造Schema或撤销API。上一头1221/93与历史2/3不顶替本轮或当前CI；0bc头frontend queued、Core in_progress。真实模型/服务器/飞书请求0，无新增依赖/迁移；本次运行源码无最终变化，回滚本测试/工具提交即可。

证据：legacy-catalog-browser/{related-unit.json,browser.json,catalog-*.png}；legacy-performance/*/{batch.json,report.json,cold-*.png}；compatibility-checks.json。继续P10已发布API及49队列，不等待答复。
