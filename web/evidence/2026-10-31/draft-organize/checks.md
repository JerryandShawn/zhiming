# 整理审阅 draft 页面验收（2026-10-31，北京时间）

- 范围：独立 `#/organize-draft` 接入 draft HTTP 端口与内存合成服务，不是旧本地整理模拟或真实 PG 验收；原 `#/organize-review` 演示保留。
- 行为：读取提案、改名、精确计划审阅；编辑使旧审阅失效。`record_only` 下点击应用资格显示“这项整理尚未开放自动应用”，不伪造成功回执。
- 定向：`draft-organize-page` + `organize-http` 合计12/12；最新全量120文件、1534/1534。
- 浏览器：`npm run test:draft-organize` 10/10，含2项行为和四视口×双主题8组；全Axe、横向溢出、小字、朱砂预算、API/外域、控制台/页面错误均0。截图已人工复核。
- 类型检查、全量lint、生产构建通过。本机Node `v24.15.0`，CI固定Node 22。
- 完整串行浏览器入口552/552：static 143、spaces 15、components 10、components-visual 64、night 220、overnight 88、thread-chat 10、`/v4/` 2、draft-organize 10。
- 未验证：正式接口、真实PG、跨设备持久化、生产CSP/反代。性能未达标不因此改变。
