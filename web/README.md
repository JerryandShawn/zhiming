# 明镜台 v4 前端（P10）

默认七页接入现有 v3 API，保留原设计系统和静态页面供显式预览：`/?preview=1#/today`。`#/__design` 始终是组件展示。真实页面包含命盘、塔罗、事项、记忆、资料确认、报告计划与归档，以及 v3 旧格式 SSE 对话与历史；成功状态以程序回执为准。旧 FastAPI 首页入口保持原状，本分支没有部署。

## 本地检查

要求 Node 22。依赖只安装在本目录：

```sh
npm ci
npm run typecheck
npm run lint
npm test
npm run build
npm run test:e2e
```

`npm run dev -- --port 4173` 启动开发预览，`npm run preview` 预览构建。API 和本地测试事件经同源代理连接 `127.0.0.1:8002`。构建输出到已忽略的 `../static/dist/`；默认页面需要 X-Token 网站口令。七页使用 hash 路由，旧深链继续映射对应数据页。不要直接使用带真实模型环境的 `main:app` 作为前端端到端测试服务。

浏览器测试在本机使用 Chrome，在 CI 使用 Playwright Chromium。默认 `npm run test:e2e` 是原 M1/M2 的 80 项显式静态预览检查，继续断言零 API/外域请求。真实数据与 SSE 测试单独运行，避免混淆验证范围。

## 隔离业务测试

本机 PostgreSQL 端口 55480，专用可丢弃数据库 `core_test_fe`。在仓库根目录使用已安装 Core 锁定依赖的 Python 环境启动：

```sh
python -m web.tests.fixture_server
```

共享数据库不可用时，可以在本工作树 `web/test-results/` 下初始化独立 PostgreSQL 15，监听 `127.0.0.1:55481`，创建同名 `core_test_fe`，并设置 `FRONTEND_TEST_DSN=postgresql://core_test@127.0.0.1:55481/core_test_fe`。夹具仅接受这两个本机端口和该库名，不会自动重启其他工作树数据库。2026-10-18 最终复测使用此隔离备用实例；数据库目录与日志均被 Git 忽略。

计算环境由 `CHART_PYTHON` 指向单独 Charts 解释器。测试服务只监听 `127.0.0.1:8002`，硬性限制数据库名，清除进程 API keys 后注入脚本模型；不启动报告投递器。每项契约测试创建独立合成 owner，避免修改全局 revision 时互相影响。

在 `web/` 中运行：

```sh
npx playwright test -c playwright.contracts.config.ts
npx playwright test -c playwright.live-visual.config.ts
node scripts/bundle-budget.mjs
```

契约套件默认使用 4173 开发服务；设置 `FRONTEND_TEST_PORT=4174` 可以在独立开发服务上运行 SSE v2 测试夹具，同时保留 4173 构建预览供视觉检查。后端仍为 8002。

第一组验证 P10 的 11 条行为契约和 SSE v2 本地模拟；第二组为真实 API 的四视口×双主题×七页截图。SSE v2 的 `tests/fixtures/v2.html` 仅在开发服务器测试使用，不会由产品页面导入，也不进入普通生产构建。请求 ID/冻结参数与事件投影保存在当前 tab 的 sessionStorage；存储容量不足时拒绝发送，避免丢失重试身份。大图片完整容量支持仍需后续附件存储方案。

本地测试专用端点 `__test__` 只定义于 `web/tests/fixture_app.py`；不修改或注册到生产 API。正常生产反向代理应自行管理 `/api`；Vite 的 localhost 代理只是本机开发配置。

## 功能区与整理建议模拟预览

P5b 增补 C / 22 号 §6 的界面用独立合成数据预览，**不需要后端或网站口令**，也不读取真实对话：

- `/?spaces=demo#/chat?space=career&topic=interview`：桌面区、话题、对话三栏；手机区标签横滑和话题下拉；全部时间线、回答归区及输入归属。
- `/?spaces=demo#/me`：七区记忆、重要的人与事项。
- `/?spaces=demo#/organize`：整理树，可改名、合并、拆分、移动、忽略；应用和撤销都要再次确认。

现有页面的“功能区预览”和“关于我 → 整理建议 · 合成预览”均能进入。此模式的归属修改、批次和草稿仅在内存中，刷新重置；忽略不删除原消息；应用后有新归区修改时，旧批次不能直接覆盖撤销。聊天发送和模型起名禁用。默认入口仍用真实 v3，不会混入这些合成记录。

构建并启动 `npm run preview` 后可运行（无需 PG/8002）：

```sh
npx playwright test -c playwright.spaces.config.ts
npx playwright test -c playwright.spaces-visual.config.ts
node scripts/bundle-budget.mjs evidence/2026-10-18/spaces/bundle-budget.json
```

状态/组件测试包含在 `npm test` 中（同时收集 `.test.ts` 与 `.test.tsx`）。新截图和哈希在 `evidence/2026-10-18/spaces/`，与旧 M4 证据分开。计划为 `ExecPlan_spaces.md`；API、真实历史整理与分类器未接通，仍由主线/模块线交付。

## 证据与参考

`../docs/v4/evidence/P10/` 包含 24 张未经改动的参考截图、56 张实际页面截图、56 张并排比较、16 张组件/浮层截图及 56 份自动审计记录。375、390、768、1440 四个视口分别覆盖宣纸和夜墨。比较脚本 `node scripts/compare.mjs` 使用现有截图，不生成或修饰设计图。

交接前静态快照：2026-10-18 按大脑 14§I 修正六项后重拍上述矩阵，并在 `review-2026-10-18/` 新增 12 张日历/控件特写与逐文件哈希。当时 26 项单测、80 项浏览器检查通过；56 默认首屏和对话滚动检查按已裁定口径满足内容朱砂≤3。该组证据对应显式静态预览，日历/时间/选项为本地合成演示；默认真实页面的独立证据见 `evidence/2026-10-18/`。

## 本地字体与许可证

使用固定版本 `@fontsource-variable/noto-sans-sc@5.3.1` 与 `@fontsource-variable/noto-serif-sc@5.3.1` 的 WOFF2 切片，202 个文件共 10,531,532 字节，低于 15MB 限额。仅预加载常用无衬线切片；其余按字体的 unicode-range 加载。可选楷体保留系统回退，不复制系统字体。

- `public/fonts/noto-sans-sc-OFL.txt`
- `public/fonts/noto-serif-sc-OFL.txt`
- `public/fonts/manifest.json`：每文件大小与 SHA-256。

`npm run prepare:fonts` 从锁定依赖重建字体、CSS、许可证与清单，超过 15MiB 会终止。运行时不依赖字体 CDN。`fonts.css` 为第三方字体声明的生成资源，不是手写组件。

## 后续范围

SSE v2 服务端与冻结 schema、cookie 会话、无痕语义、新版画像/proposal/主动设置/设备吊销尚未提供；相关控件禁用。v3 运行取消接口实际返回 422，不能宣称已停止。塔罗写接口不校验 expected_revision，紫微与星盘目前为实际字段列表。飞书真机、4G LCP 与生产首页切换未验证。本分支没有访问 stage/生产或发真实模型/飞书请求。

当前计划 `ExecPlan_frontend.md`；本线日报 `../docs/v4/daily/2026-10-18_frontend.md`；新证据摘要在 `evidence/2026-10-18/`，完整本机测试输出与图片在已忽略的 `test-results/`。原 `docs/v4/evidence/P10/` 是交接前静态证据，保持不变。
