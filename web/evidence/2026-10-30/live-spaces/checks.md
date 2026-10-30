# `#/spaces` 页面验收（2026-10-30，北京时间）

- 范围：`?spaces=demo#/spaces?space=career` 的实际 `LiveSpaces` 页面与内存合成服务；不是旧 `spaces.spec.ts` 静态演示，也不是已发布后端或真实 PG 验收。
- 环境：本机 Node `v24.15.0`；CI 固定 Node 22，本机结果不替代 CI。
- `npm test -- tests/spaces-http.test.ts --maxWorkers=2`：21/21 通过。
- 首轮 `npm run test:spaces`：14/15；移动后切区找不到原话题。定位为路由 key 重建内存服务，`src/App.tsx` 对 spaces 改用稳定 key；未改原行为断言。
- 修复后 `npm run test:spaces`：15/15，通过新建、改名、归档/恢复、移动、敏感区键盘导航及旧 spaces 演示回归；API/外域请求 0。
- `npm run test:live-spaces-visual`：8/8，375/390/768/1440 × 宣纸/夜墨；全 Axe 规则、横向溢出、小字、朱砂预算、控制台/页面错误、API/外域请求均为 0。截图与逐图 SHA 见 `visual-summary.json` 和 `screenshots/`。
- `npm test -- --maxWorkers=2`：115 文件、1501/1501 通过；`npm run lint`、`npm run typecheck`、`npm run build` 通过。
- 未验证：真实接口、真实 PG、登录态、真机、服务器与部署；性能结果另存 `spaces-performance/`，不以本文件预写达标。
