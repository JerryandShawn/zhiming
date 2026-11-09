# P10 新前端 `web/` 独立移植清单（准备稿，不合入 release-next）

状态：准备稿。大脑 2026-11-09 裁定本版只带 B 界面；`web/` 在 B 上线稳定后作为一次独立的"只增不改"发布，连同 Node 22 构建、`/v4/` 路由与 CI 一起移植。本清单只为那次发布做准备，**没有向 `release-next` 合入任何东西**。清单里的命令已在一次性本地工作树（`trial/web-port`，从 `release-next@e17cd336` 拉出，未推送）里真实演练过，演练结果见第 6 节。

## 1. 要移植什么（精确范围）

| 项 | 数量 | 说明 |
| --- | --- | --- |
| `web/**`，排除 `web/evidence/**` | **846 个文件** | src 333、tests 206、public 226（含 202 个字体切片，约 11MB）、scripts 35、其余是 `package.json`、锁文件、各 `vite/vitest/playwright` 配置和几份 `*.md` 说明 |
| `.github/workflows/frontend-v4.yml` | 1 个 | 现触发条件是 push `v4/p10-frontend` 和 PR→`v4/main`，移植后要由主线改成适用的分支；`.github` 不归前端线改 |
| `.gitignore` | **只加一行** `/static/dist/` | 见第 4 节"不要整文件取" |
| 文档（可选） | `docs/v4/execplans/P10_frontend.md`、`docs/v4/receipts/P10_M1_M2.md`、`docs/v4/daily/*_frontend*.md` | 不影响运行，随主线需要取 |

**不移植**：`web/evidence/**`（4254 个文件，历史截图、报告、五冷性能证据；单测和浏览器套件都不读它们，见第 6 节）、`docs/v4/evidence/P10/**`（231 个）。需要查证据时从 `v4/p10-frontend` 分支读。

除上述之外，`static/`、`mingjing_core/`、`tests/` 等 release-next 既有文件**一个都不改**（p10 相对 release-next 在 `static/app.js`、`static/index.html`、`static/paper.css` 的差异来自旧页，属于本版 B 与第三批，不在这次移植里）。

## 2. 移植步骤（已演练）

在 `release-next`（或其后继）拉出的新分支上：

```bash
git fetch origin
# 一定要用 NUL 分隔的列表：中文文件名会被 git 加引号，普通管道会漏排或报错
git -c core.quotepath=false ls-tree -r --name-only -z origin/v4/p10-frontend web \
  | tr '\0' '\n' | grep -v '^web/evidence/' > /tmp/port-list.txt
tr '\n' '\0' < /tmp/port-list.txt | xargs -0 git checkout origin/v4/p10-frontend --
git checkout origin/v4/p10-frontend -- .github/workflows/frontend-v4.yml   # 之后由主线改触发分支
sed -i 's#^node_modules/$#node_modules/\n/static/dist/#' .gitignore          # 只加这一行
```

预期 `git status` 为 848 个已暂存（846 个 `web/` 文件 + 工作流 + `.gitignore`），且 `git ls-files --others --exclude-standard` 为空。移植应是**单独一个提交**，不与别的改动混在一起，便于整体回退。

## 3. 构建与验证门（Node 22，以 CI 为准；本机 Node 24 只作补充）

```bash
cd web
npm ci
npm run typecheck
npm run lint
npm test -- --maxWorkers=2
npm run build            # 产物在 static/dist/（gitignore，不提交）
npm run test:e2e         # 串行入口，约 560 项
```

构建后核对 `static/dist/encoded-assets.json`（gzip 副本字节与 SHA）和 `static/dist/.vite/manifest.json`；每次发布都用同一精确 SHA 重新构建，不复用旧构建或旧 gzip 副本。详细的 gzip、PWA 壳、缓存、CSP 建议见 `web/B6_delivery_handoff.md` 和 `web/Static_delivery_notes.md`，这里不重复。

## 4. 演练中发现的坑

1. **不要整文件取 `.gitignore`。** p10 的 `.gitignore` 缺少 release-next 里关于 `mingjing_core/models/` 和 `tests/v4/models/` 的 6 行例外规则，整文件覆盖会让模型相关文件被忽略。只加 `/static/dist/` 一行。
2. **中文文件名。** `git ls-tree` 默认给非 ASCII 路径加引号，用 `grep -v '^web/evidence/'` 会漏掉带引号的证据文件、同时让 `xargs git checkout` 报错。用 `-c core.quotepath=false … -z` 和 `xargs -0`。
3. **`node_modules` 不要提交。** 演练用目录联接复用了已安装的依赖；真实发布用 `npm ci`。
4. **`legacy-stream` 浏览器项目在 release-next 上必然失败（15 项）。** `web/playwright.config.ts` 的默认入口含 `legacy-stream` 项目（`tests/legacy-e2e/stream.spec.ts`，15 项），它们等待旧页的 `window.mingjingLegacyStream`，这个桥接来自 p10 的 `static/app.js`/`static/index.html` 改动和 `web/` 构建出的 `legacy-stream.js`，属第三批（旧网页逐字显示），release-next 的旧页没有。演练中 `test:static` 因此得到 128 过 / 15 败，15 个全是该项目，每个等满 60 秒超时（套件耗时 15.9 分钟，而主工作树 1.6 分钟）。这不是回归，也不是新前端本身的问题。移植时必须二选一并写进发布说明：（a）让 `frontend-v4` 工作流和 `test:e2e` 在没有第三批旧页桥接时排除 `legacy-stream` 项目；（b）把第三批旧页桥接一起带上。**本移植提交不改任何测试或配置**，保持与 p10 逐字节一致便于追溯。
5. **vitest 首跑偶发 `ERR_IPC_CHANNEL_CLOSED`。** 演练中和 `tsc`、`eslint` 连着跑的那一次出现过一次，单独重跑通过；CI 按顺序跑各步，不并发。

## 5. 后端与部署需要什么（前端线不改，交主线）

1. **`/v4/` 路由。** release-next 的 `web.py` 只挂 `/static`，没有 `/v4/`。构建基址是相对的（`base: './'`），所以把 `static/dist` 原样挂在 `/v4/` 下即可（FastAPI `StaticFiles(directory=…/static/dist, html=True)` 或 nginx，配置建议在 `B6_delivery_handoff.md`）。**这一步在本机演练里没有做，属未验证。** 旧根页 `/` 和 `/static/*` 不受影响。
2. **构建步骤。** `static/dist` 不在 git 里，发布流程要在目标 SHA 上执行第 3 节的构建；构建产物不能从别的发布复制。
3. **CSP / SW。** 新页面带 PWA 的 service worker（scope `/v4/`）和少量内联样式，CSP 先 Report-Only，见 B6 文档。
4. **接口对照。** 新前端调用 36 个后端路径。release-next 已有的：`/api/chat`、`/api/history`、`/api/threads/{id}/messages`、`/api/runs/{id}`（含 events/cancel/retry/resume）、`/api/cases`、`/api/memories`、`/api/chart*`、`/api/tarot/*`、`/api/subjects/self/profile*`、`/api/reports*`、`/api/state*`、`/api/health`、`/api/timeline`、`/api/graph`、`/api/dict`。**release-next 没有**（对应 mod 线的 draft 契约，主线尚未发布正式 `api_*.md`）：`/api/spaces*`、`/api/topics/*`、`/api/messages/*`（区与话题）、`/api/organize*`（整理审阅）、`/api/study/progress/*`（研习进度）。

   影响：只有 `#/spaces` 和 `#/organize-draft` 两个深链页面会直接请求这些缺失路径，导航里没有入口；研习进度只出现在 `?spaces=demo` 预览的课程面板里。这些页面在后端缺路由（404）时的表现**没有验证过**。移植时二选一，由主线/大脑定：（a）保持原样，只在发布说明里写明这两个深链暂不可用；（b）加一处路由开关，缺接口时显示"尚未开放"（需要小改动 `src/App.tsx`，发布前另测）。我的建议是 (b)，因为 (a) 会让用户手输深链时看到错误页。

## 6. 演练结果（`trial/web-port`，release-next@e17cd336 + 上述移植，Node 24）

- `tsc --noEmit`、`eslint .`：无输出（通过）。
- vitest：**122 文件、1541/1541**（不含 `web/evidence`，说明单测不依赖证据）。
- `vite build`：通过，产物目录含 `assets`、`data`、`fonts`、`encoded-assets.json`。
- 浏览器：`test:v4-base` 2/2、`test:thread-chat` 10/10、`test:spaces` 15/15、`test:draft-organize` 10/10；`test:static` 128 过、15 败（15 个全是 `legacy-stream` 项目，原因见第 4 节第 4 点）。
- 没有跑完整 `test:e2e`、没有 CI、没有 `/v4/` 实机挂载、没有真实后端联调、没有 PG。

## 7. 仍未达标的项（移植不会改变它们）

对话页页面加载 LCP p75 2548ms（差 48ms）、课程页约 5000ms 未达 2500ms；整理页 2080ms、spaces 2132ms 本机合成条件下达标。真机 4G、飞书真机、真实 API/PG 均未验证。这些在发布说明里要如实写，不写"就绪"。

## 8. 回退

移植是单个提交，回退即 `git revert` 该提交；`/v4/` 路由和构建步骤另行回退；不涉及数据库迁移或数据变更，旧根页面和旧 API 全程不受影响。
