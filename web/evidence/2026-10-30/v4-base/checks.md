# `/v4/` 静态基址验收（2026-10-30/31，北京时间）

- 实现：保留 Vite `base: './'`；HTML 的 favicon、manifest、字体与预加载改为相对 URL；公开 `/data/` JSON 由 `publicAssetPath` 按 `document.baseURI` 解析。`/api/` 和共享 `/static/tarot/` 不改。
- 定向单测：`public-asset`、`course-loader`、`study-loader`、`tools-loader` 合计 **46/46**，覆盖根路径、`/v4/`、`/v4/index.html` 和路径逃逸/双斜线/query 拒绝。
- 首轮独立 HTTP 导航失败来自测试服务器把 `index.html` 错拼为 `.index.html`，修正测试服务器，不改产品行为；manifest 与 shell-manifest 改为显式 GET，因为浏览器不会必然主动请求它们。
- 最终 `npm run test:v4-base`：**2/2**。实际验证 `/v4/` 应用、20 课公开 JSON、字体、manifest start_url/scope、SW `/v4/` scope、shell 资源作用域、hash 深链、`/v4` 302 和旧根路径。首轮截图误用默认1280宽，已显式设置390×844重拍并核图，文件为 `courses-light-390.png`。
- 后续最终全量单测119文件、1531/1531，完整串行浏览器542/542；lint/typecheck/build 通过。本机 Node `v24.15.0`，CI 固定 Node 22。
- 未验证：生产反代、旧站并存、真实 CSP、SW 升级、精确头 CI 和真实 API/PG。本机通过不等于部署完成。
