# 整理审阅 draft 页面验收（2026-10-31，北京时间）

- 范围：独立 `#/organize-draft` 接入 draft HTTP 端口与内存合成服务，不是旧本地整理模拟或真实 PG 验收；原 `#/organize-review` 演示保留。
- 行为：读取提案、改名、精确计划审阅；编辑使旧审阅失效。`record_only` 下点击应用资格显示“这项整理尚未开放自动应用”，不伪造成功回执。
- 定向：首轮`draft-organize-page` + `organize-http`合计12/12；写重试扩展后相关单测17/17，最终全量122文件、1541/1541。模糊失败复用完全相同的request_id与载荷；409保留草稿并锁写待重读。
- 浏览器：`npm run test:draft-organize` 10/10，含2项行为和四视口×双主题8组；全Axe、横向溢出、小字、朱砂预算、API/外域、控制台/页面错误均0。截图已人工复核。
- 类型检查、全量lint、生产构建通过。本机Node `v24.15.0`，CI固定Node 22。
- 完整串行浏览器入口552/552：static 143、spaces 15、components 10、components-visual 64、night 220、overnight 88、thread-chat 10、`/v4/` 2、draft-organize 10。
- 五冷性能：`4b3382fd`干净头p75 4024ms，未达2500；证据`web/evidence/2026-10-27/organize-performance/4b3382fd-clean/`。行为回归不替代性能门。
- 瀑布定位：首轮主组件约1874ms到达，pencil/shield-check两个微型分包约3824/3901ms才到达，LCP为3960ms。字体18片约1.05MB与微型分包共享带宽；不把此观察冒称已优化。
- 合包候选：Lucide 5.92KB gzip、draft共享包4.45KB gzip；dirty五冷1932/1936/1940/1968/1984ms，p75 1968ms，见`grouped-runtime-candidate/`。包体/PWA40/40、功能/路由39/39；干净头复测另核。
- 未验证：正式接口、真实PG、跨设备持久化、生产CSP/反代。性能未达标不因此改变。
