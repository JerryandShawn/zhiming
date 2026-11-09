# 新前端接口总览（下一版，`v4/release-next`）

> 读者：前端线。真相源是代码；本文件写于 2026-11-09，对应 `v4/release-next@8a05c12f` 之后。字段若与代码不符，以代码为准，并回报新主线修文档。
> 分册：[对话](api_conversation.md) · [记忆与关于我](api_memory.md) · [命理档案](api_fate_archive.md)

## 1. 页面挂载与切回开关（`mingjing_core/adapters/web_ui.py`）

| 路径 | 内容 |
|---|---|
| `/` | 默认 302 跳到 `/app/`；`MINGJING_WEB_UI=legacy` 时直接返回旧页 |
| `/app/` | 新前端构建产物 `static/dist/`（`StaticFiles(html=True)`），`index.html` 与 `assets/` 等同目录 |
| `/legacy/` | 旧页 `static/index.html`，任何模式下都在（旧页资源走绝对路径 `/static/...`） |
| `/static/...` | 旧页静态资源（不变） |

- 开关 `MINGJING_WEB_UI=v4|legacy`，默认 `v4`；非法值启动即报错。切回旧页 = 在成员 env 文件写 `MINGJING_WEB_UI=legacy` 后重启 Web；不改 nginx。
- 若 `static/dist/index.html` 不存在，根路径自动回退旧页，不会出现空白根页。
- `GET /api/health` 新增 `web_ui` 字段，报告**实际**服务的页面（`v4`/`legacy`），执行单用它核验。
- 前端约束：Vite `base: './'`（已是），hash 路由，Service Worker scope = `/app/`。不要依赖站点根下的绝对资源路径。

### 构建产物与哈希（待与前端线最终商定，见文末“待定”）
- 产物目录固定 `static/dist/`，含 Vite `manifest.json`（`.vite/manifest.json`）。
- 新主线提议：发布包按 git 跟踪文件打包，所以冻结候选时把 `static/dist/` 作为构建提交纳入 git（从 `.gitignore` 去掉该行），并生成 `static/dist/SHA256SUMS`（每个文件一行，LF）。冻结门：在锁定的 Node 22 + `npm ci` 下重新构建，与提交内容逐字节比对；生产执行单在解包后用 `sha256sum -c` 核验。

## 2. 认证与通用约定
- 所有 `/api/*` 需要请求头 `X-Token`；无口令配置 503，错误口令 401（`adapters/web.py:auth`）。
- 写请求必须带稳定 `request_id`（重放安全，同一 id 换内容会报冲突），并尽量带 `expected_revision`。
- 错误体：`{"detail": "<给人看的中文>"}`；403 范围错误、404 记录不存在、409 修订/幂等冲突、422 输入或证据错误。
- 人物（subject）：本版新前端只用 `subject_id=self`。

## 3. 正式页面 → 接口对照（新前端 `web/src/live` 等）

| 页面 | 接口 | 后端状态 |
|---|---|---|
| 今日 | `/api/history?session=shared&subject_id=self&limit=4`、`/api/reports`、`/api/state` | 已有 |
| 对话 | 见 [对话](api_conversation.md) | 已有 |
| 命盘 | `/api/chart`、`/api/chart_ziwei`、`/api/chart_astro`、`/api/subjects/self/profile(/confirm)` | 已有；P8 补充见[命理档案](api_fate_archive.md) |
| 塔罗 | `/api/tarot/deck`、`/api/tarot/draws…` | 已有 |
| 事项 | `/api/cases…` | 已有 |
| 我 | `/api/memories…`、`/api/timeline`、`/api/graph`、`/api/dict`；**新增** `/api/memory2/proposals`、`/api/memory2/profile` | 见[记忆](api_memory.md) |
| 设置 | `/api/state/settings`、`/api/reports/schedules` | 已有 |

## 4. 没有后端的前端功能（本版请隐藏或保持仅预览）
以下只在前端 `fakeServer.ts` 里有实现，后端在任何分支都没有，本版不新增：
- `/api/spaces…`、`/api/topics/…`（spaces，`?spaces=demo` 预览）
- `/api/organize/…`（整理草稿）
- `/api/study/progress/…`（课程进度）
- `/api/messages/{id}`

正式导航不得出现这些入口；如前端认为本版必须带，请报大脑。

## 待定（等前端线回复）
1. `static/dist/` 是否纳入 git，以及构建是否可在 Linux CI 上逐字节复现（Windows/Linux 换行、Node 小版本）。不可复现时改为“本机构建 + SHA256SUMS + 执行单单独上传核验”。
2. 体积：公共资源约 13MB（字体切片），是否全部随包。
