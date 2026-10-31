# P10 静态交付准备与边界（仅供主线审查）

本线只构建、核验本机产物和编写建议，没有访问服务器、启用配置或部署。PR #6 保持草稿。课程页面是固定合成教材；真实身份、业务 API、学习进度和真实飞书验证另行验收。

## 构建与哈希

使用 Node 22、锁文件安装后的既有依赖执行 `npm run typecheck`、`npm run lint`、定向测试和 `npm run build`。构建产物在 `static/dist/`，不提交该目录。`static/dist/.vite/manifest.json` 描述模块及懒加载关系；`encoded-assets.json` 记录身份资源与 gzip 副本双方字节数、SHA。每次构建都重新核对副本，不能把旧发布的副本复制到新发布。

课程位于 `data/study/courses-v5/{course,manifest}.json`，输入固定 meta v5 `f8d9536a`。旧版七资产仍独立；不得把旧卡片 c2 与新课程 c7 按短号合并。页面只 GET 单一已固定大小/SHA 的课程，不发送身份头、不读个人档案、不持久化练习。

PWA 的 `pwa/shell-manifest.json` 只选应用壳，不包含任何 `data/study/` JSON；运行时不扩充数据缓存。注销/无痕/对话数据规则不因 gzip 或教材静态化改变。

## `/v4/` 挂载：本机已接，生产待验收

早期构建以站点根路径为基准，不能直接放到 `/v4/`。2026-10-30 已按统一基址补齐 Vite 模块、HTML 字体/PWA、manifest start_url/scope、SW scope 与公开 `/data/study/` 的相对解析，并在本机隔离 HTTP 验证；API `/api/` 仍属主线路由，共享 `/static/tarot/` 不随基址改写。

以下为经本机构建验证后的配置建议，不是已启用或已经生产验收的配置。发布目录由主线代入；不覆盖旧站和既有 API，旧站路由冲突仍需主线实机核对。

```nginx
location = /v4 { return 302 /v4/; }
location = /v4/index.html {
    alias /REVIEWED_RELEASE/static/dist/index.html;
    add_header Cache-Control "no-store" always;
}
location /v4/assets/ {
    alias /REVIEWED_RELEASE/static/dist/assets/;
    gzip_static on;
    add_header Vary "Accept-Encoding" always;
    add_header Cache-Control "public, max-age=31536000, immutable";
}
location /v4/data/study/ {
    alias /REVIEWED_RELEASE/static/dist/data/study/;
    gzip_static on;
    add_header Vary "Accept-Encoding" always;
    add_header Cache-Control "no-store" always;
}
```

主线还需补齐字体、manifest、SW 和应用壳 fallback 的精确位置；SW 与 manifest 不使用 immutable，避免旧壳滞留。仅带内容哈希的 assets 使用长期 immutable。公开教材文件名固定，浏览器仍按 no-store 读取并自行核对固定摘要。Content-Type 保留原类型；无 gzip 副本或客户端不接受 gzip 时返回原文件。

上述模板不修改 SSE。`/api/runs/*/events` 的缓冲、超时和不压缩要求遵循主线 P4 契约，由主线单独验证；本线没有操作代理或 LISTEN 连接。

## CSP 候选

先在受控环境以 Report-Only 验证，再由主线决定是否强制。基础建议为：默认拒绝；脚本、连接、字体、manifest 和 worker 仅同源；图片允许同源及确有需要的 data URL；禁止 object；base-uri/form-action 同源。当前 React/Radix/动效和视口组件使用内联样式，不能未经验证就用仅 `style-src 'self'` 宣称弹层和键盘适配可用；需报告其来源并选择 nonce/hash 或经审查的样式例外。禁止内联脚本与事件属性。

飞书容器的实际嵌入域和身份契约尚未验证。frame-ancestors 的白名单由主线按实际容器确定；本线不凭 UA 或假服务放宽来源、不加载外部 SDK。伪装容器、假 code、断网或超时都不得建立正式登录身份。

## 发布前待核

- 当前精确 SHA 的 CI 全绿；历史本机绿和取消的 CI 不替代它。
- `/v4/` 本机基址、深链与 SW scope 已测；SW 升级、生产旧站并存及精确头 CI 仍待。
- 新页面四尺寸双主题、全规则 Axe 与朱砂计数；课程本机证据见本日目录。
- 4G 性能单独记录：旧页 p75 2572ms、新课程 f374e1fc p75 5260ms 均未过2500；H5 gzip预览1816ms不能替代两者。
- 真实 HTTP+PG 的身份/归属/取消/回执投影由主线验收；本线真实模型请求0。

回退仅指恢复本线前端提交后重新构建并交主线审查，不涉及数据库迁移、数据删除、服务器动作或自行上线。

## 2026-10-30 v6 发布准备补充

### 可复现构建门

在干净工作树使用 CI 相同的 Node 22 与锁文件，依次执行；本机 Node 24 的结果只作补充，不替代精确头 CI：

```sh
cd web
npm ci
npm run typecheck
npm run lint
npm test -- --maxWorkers=2
npm run build
npm run test:e2e
```

发布时只取同一精确 SHA 新生成的 `static/dist/`，不提交或复用旧构建。`static/dist/.vite/manifest.json` 用于模块核对，`encoded-assets.json` 用于逐个 gzip 副本与原文件的字节数/SHA 核对；`pwa/shell-manifest.json` 只含应用壳，不能加入 API、对话或个人进度。压缩副本每次重建，不能用旧哈希文件的副本顶替。

### 统一基址已在本机验证，生产仍是硬前置

2026-10-30 已保留 `base: './'`，将 HTML 字体/图标/manifest 改为相对 URL，并让公开 `/data/` JSON 通过 `document.baseURI` 解析；`/api/` 与共享 `/static/tarot/` 不变。`manifest.webmanifest` 的 `start_url`/`scope` 继续按 manifest URL 解析，SW 按构建基址注册。

`npm run test:v4-base` 使用独立真实 loopback HTTP 验证 `/v4/` 首屏、20 课公开 JSON、字体、manifest start_url/scope、SW `/v4/` scope、shell 资源、hash 深链、`/v4` 302 和旧根路径，2/2 通过；截图见 `evidence/2026-10-30/v4-base/`。这不是生产反代、旧站并存或 CI 验收，主线仍需在精确发布目录复核。

以下配置适用于上述统一基址产物。`REVIEWED_RELEASE` 由主线替换为只读发布目录；不得覆盖旧站或既有 `/api`：

```nginx
location = /v4 { return 302 /v4/; }
location = /v4/ {
    alias /REVIEWED_RELEASE/static/dist/index.html;
    add_header Cache-Control "no-store" always;
}
location = /v4/index.html {
    alias /REVIEWED_RELEASE/static/dist/index.html;
    add_header Cache-Control "no-store" always;
}
location /v4/assets/ {
    alias /REVIEWED_RELEASE/static/dist/assets/;
    gzip_static on;
    add_header Vary "Accept-Encoding" always;
    add_header Cache-Control "public, max-age=31536000, immutable" always;
}
location /v4/fonts/ {
    alias /REVIEWED_RELEASE/static/dist/fonts/;
    add_header Cache-Control "public, max-age=31536000, immutable" always;
}
location = /v4/shell-sw.js {
    alias /REVIEWED_RELEASE/static/dist/shell-sw.js;
    gzip_static on;
    add_header Vary "Accept-Encoding" always;
    add_header Cache-Control "no-store" always;
}
location /v4/pwa/ {
    alias /REVIEWED_RELEASE/static/dist/pwa/;
    add_header Cache-Control "no-store" always;
}
location /v4/data/study/ {
    alias /REVIEWED_RELEASE/static/dist/data/study/;
    gzip_static on;
    add_header Vary "Accept-Encoding" always;
    add_header Cache-Control "no-store" always;
}
```

hash 路由不需要把任意 `/v4/...` 路径重写为应用；只需保证 `/v4/` 与 `/v4/index.html` 一致。只有带内容哈希的 assets 使用 immutable；字体可按内容寻址策略另审，SW、manifest、HTML 和固定文件名教材保持 no-store。gzip 只用于静态副本，保留原 Content-Type 和 `Vary: Accept-Encoding`，无副本时返回身份字节。

`/api` 继续走主线现有反向代理，不挂到 `/v4/api`。SSE 路由建议沿用以下约束并由主线实测，不能套用静态缓存或 gzip：

```nginx
proxy_buffering off;
proxy_read_timeout 60s;
gzip off;
```

响应仍须保留 `X-Accel-Buffering: no`；首字节、15 秒心跳、Last-Event-ID 续传与 LISTEN 连接数由主线验收，本线未操作代理。

### CSP Report-Only 候选

先在本机隔离服务和 stage 的授权窗口用 `Content-Security-Policy-Report-Only` 收集报告，再由主线决定强制策略。当前 React/Radix/Motion/视口组件存在样式属性，`style-src` 暂时需要经审查的 `'unsafe-inline'`；nonce 不能覆盖样式属性。不能一边保留该例外一边宣称已经达到仅 `style-src 'self'`：

```text
default-src 'self';
script-src 'self';
style-src 'self' 'unsafe-inline';
font-src 'self';
img-src 'self' data: blob:;
connect-src 'self';
worker-src 'self';
manifest-src 'self';
object-src 'none';
base-uri 'self';
form-action 'self';
frame-ancestors 'self' https://REVIEWED_FEISHU_CONTAINER;
```

`REVIEWED_FEISHU_CONTAINER` 只是占位，必须由真实飞书容器来源替换；未验证前不要加入通配符或外部 SDK。禁止内联脚本和事件属性；不得为图方便放宽 script-src、connect-src 或 object-src。飞书 SDK 若将来确需加载，只在实际飞书页面按官方域名单独放行，不能全站放开。强制前逐条审阅报告并复测弹层、Markdown、图片草稿、键盘视口、PWA 与 SSE。

### 当前不得写“上线就绪”的缺口

- `/v4/` 仅完成本机基址验收；真实 CSP 报告、真实飞书 frame 来源、生产反代、旧站并存和精确头 CI 均未验收。
- 本机 Node 24 下，`#/spaces` 干净头五冷 gzip p75 LCP 为 **4148ms**，v4 对话为 **5840ms**，都未过 2500ms；旧页 2572ms、课程 5020ms 的历史缺口也保留。任何 H5 或包体成绩都不能替代这些页面。
- v4 对话和 spaces 目前用合成 API 完成行为/视觉验收；整理与研习 draft 端口尚未接真实 UI/PG。真实身份、来源授权、持久化和服务器验收仍属主线。
