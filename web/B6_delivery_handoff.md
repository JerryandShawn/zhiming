# P10 静态交付准备与边界（仅供主线审查）

本线只构建、核验本机产物和编写建议，没有访问服务器、启用配置或部署。PR #6 保持草稿。课程页面是固定合成教材；真实身份、业务 API、学习进度和真实飞书验证另行验收。

## 构建与哈希

使用 Node 22、锁文件安装后的既有依赖执行 `npm run typecheck`、`npm run lint`、定向测试和 `npm run build`。构建产物在 `static/dist/`，不提交该目录。`static/dist/.vite/manifest.json` 描述模块及懒加载关系；`encoded-assets.json` 记录身份资源与 gzip 副本双方字节数、SHA。每次构建都重新核对副本，不能把旧发布的副本复制到新发布。

课程位于 `data/study/courses-v5/{course,manifest}.json`，输入固定 meta v5 `f8d9536a`。旧版七资产仍独立；不得把旧卡片 c2 与新课程 c7 按短号合并。页面只 GET 单一已固定大小/SHA 的课程，不发送身份头、不读个人档案、不持久化练习。

PWA 的 `pwa/shell-manifest.json` 只选应用壳，不包含任何 `data/study/` JSON；运行时不扩充数据缓存。注销/无痕/对话数据规则不因 gzip 或教材静态化改变。

## `/v4/` 挂载尚待接线

**当前构建仍以站点根路径为基准，不能直接把整个目录放到 `/v4/` 后宣称可用。** Vite 模块基址、HTML 的字体/PWA路径、manifest start_url/scope、Service Worker 注册与 scope、静态只读端口的 `/data/study/`、浏览器返回及深链接都需要一起核对。API `/api/` 属于现有主线路由，不能随静态基址盲目改写。

主线集成前选定一种统一基址方案，并先在本机隔离服务验证 `/v4/`。建议让应用壳、字体、PWA与公开教材都归 `/v4/`，集中通过构建基址解析静态 URL；这需要前端后续接线，当前不是已完成能力。若暂时保留根路径资产别名，须先审计与旧站现有路由的冲突，不能仅依赖下面的配置片段。

以下只是**未来完成统一基址后的模板**，不是可直接粘贴的现状配置。发布目录由主线代入；不覆盖旧站和既有 API。

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
- `/v4/` 统一基址、本机真实 HTTP 深链刷新、SW scope/升级及旧站并存；目前仍待。
- 新页面四尺寸双主题、全规则 Axe 与朱砂计数；课程本机证据见本日目录。
- 4G 性能单独记录：旧页 p75 2572ms、新课程 f374e1fc p75 5260ms 均未过2500；H5 gzip预览1816ms不能替代两者。
- 真实 HTTP+PG 的身份/归属/取消/回执投影由主线验收；本线真实模型请求0。

回退仅指恢复本线前端提交后重新构建并交主线审查，不涉及数据库迁移、数据删除、服务器动作或自行上线。
