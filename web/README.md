# 明镜台 v4 静态前端（P10 M1/M2）

本工程提供设计系统和七个合成示例页面：今日、对话、命盘、塔罗、事项、关于我、设置。数据和交互均在浏览器本地演示，不请求 API，不发送消息，不保存用户资料，不计算真实命盘或抽取真实塔罗。旧 FastAPI 页面入口保持原状。

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

`npm run dev` 启动开发预览；`npm run preview` 在本机 4173 端口预览构建。构建输出到已忽略的 `../static/dist/`。`#/__design` 展示组件及其状态。七页使用 hash 路由，旧报告、记忆、时间线等深链映射到对应静态分区。

浏览器测试在本机使用已安装的 Chrome，在 CI 使用 Playwright Chromium。CI 工作流为 `.github/workflows/frontend-v4.yml`，同时验证键盘、弹层焦点、减少动效、AA 对比度、无横向溢出和没有后端或外域请求。

## 证据与参考

`../docs/v4/evidence/P10/` 包含 24 张未经改动的参考截图、56 张实际页面截图、56 张并排比较、16 张组件/浮层截图及 56 份自动审计记录。375、390、768、1440 四个视口分别覆盖宣纸和夜墨。比较脚本 `node scripts/compare.mjs` 使用现有截图，不生成或修饰设计图。

2026-10-18按大脑14§I修正六项后重拍上述矩阵，并在`review-2026-10-18/`新增12张日历/控件特写与逐文件哈希。当前26项单测、80项浏览器检查通过；56默认首屏和对话滚动检查按已裁定口径满足内容朱砂≤3。日历/时间/选项仍为本地合成演示，不接业务保存或重新排盘。

## 本地字体与许可证

使用固定版本 `@fontsource-variable/noto-sans-sc@5.3.1` 与 `@fontsource-variable/noto-serif-sc@5.3.1` 的 WOFF2 切片，202 个文件共 10,531,532 字节，低于 15MB 限额。仅预加载常用无衬线切片；其余按字体的 unicode-range 加载。可选楷体保留系统回退，不复制系统字体。

- `public/fonts/noto-sans-sc-OFL.txt`
- `public/fonts/noto-serif-sc-OFL.txt`
- `public/fonts/manifest.json`：每文件大小与 SHA-256。

`npm run prepare:fonts` 从锁定依赖重建字体、CSS、许可证与清单，超过 15MiB 会终止。运行时不依赖字体 CDN。`fonts.css` 为第三方字体声明的生成资源，不是手写组件。

## 后续范围

M3 真实事件协议/后端接线、M4 行为端到端、M5 真机和性能验收尚未实施。静态界面不能证明 revision、owner、固定牌、撤销、来源授权等业务不变量。晨间待大脑复核的视觉差异见 `../docs/v4/evidence/P10/visual-review.md`，阶段回执见 `../docs/v4/receipts/P10_M1_M2.md`。

用户已指定本轮修正提交后由独立前端聊天接续M4，本代理停止此工作树与`web/**`修改。交接边界、静态状态限制、8002/core_test_fe与主线发布约定见`../docs/v4/daily/2026-10-18_frontend_handoff.md`。
