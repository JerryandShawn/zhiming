# P10 · 字体首屏竞争修正小回执

- 分支：`v4/p10-frontend`；已推送运行源码：`a93541d52d1a1f608af936e58f7a6ea9431f25f2`。PR：https://github.com/JerryandShawn/zhiming/pull/6（Open Draft，未合并）。ExecPlan：`web/ExecPlan_week_2026-10-21.md`。

## 完成与评测

- [x] 保留08§3要求的常用Sans119预加载并设low提示；去独立Latin预加载。完整stylesheet、202个有序face、Unicode覆盖、10,531,532B原字体与OFL未改，display仍swap，PWA四字体保留。
- [x] 48/48相关单测（字体8/PWA22/budget18）、10/10浏览器（PWA6/今日路由4）、12图，1028项源/测试/构建及HEAD不变；类型/lint零警告/构建通过，Axe全规则0/朱砂≤3。真实SW白名单/正文无痕不入缓存、即时三查询/登录门禁保持；三GET由浏览器mock履行，无真实后端。
- [x] 干净运行头五冷4G LCP **2264/2268/2316/2248/2276ms，p75 2276，全部<2500**。原失败基线2464/2480/2492/2532/2460、p752492；本次观察p75降低216ms（8.67%）。完整原失败与新五次报告/图保留，未改阈值或内容。

本机390×844/DPR2、4G RTT150ms/down200000Bps/up93750Bps、CPU4、cache/SW关闭、五新正常动效context。源干净/源构建前后不变、三API200/内容计数匹配、静态失败0/真实模型0；18字体/1,069,544B每轮不变。Latin24,880B仅移出提前时段，不是总字节减量；low是提示，未单独采集浏览器内部priority。

对比还包括三个仅工具懒路由的M2c文件，测量今日不加载它们；今日关键源哈希同，启动改动为index字体提示，差分和CSS/API时序见font_priority_performance_comparison.json。单批本机观察不外推真机、部署或总体统计效应。

## 证据与边界

font_priority_checks.json、font_priority_performance_comparison.json、font-priority-final/12图、font-priority-performance/final/head-a93541d-1019/report.json与五冷原图；分析见web/Font_priority_notes_2026-10-21.md。CSS进一步规范化仅108B gzip收益，已丢弃，无二进制子集化或新依赖。

关键修改index.html/精确预加载断言；无迁移/资料写删/部署，回滚a935后重建。10:21查a935 Core queued/frontend pending，未称CI绿。下一一天脚本，10:30合法窗口全量及三遍稳定性待做。P10整体未Done，无需用户在线回复。
