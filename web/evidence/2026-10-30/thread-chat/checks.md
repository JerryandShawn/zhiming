# C3 对话页接线验收（2026-10-30，北京时间）

- 范围：生产默认 `#/chat` 改为 v4 线程提交 + C3 控制器；附图与旧恢复继续走原 v3。v4 pending 保存线程目标与验收回执，刷新只恢复原运行。
- `npm test -- tests/thread-chat.test.tsx --maxWorkers=2`：5/5，覆盖提交至终稿、停止、刷新恢复、附图 v3 回退和实际 `Chat transport="v4"`。
- 原 v3 定向回归：`chat-cancel-feedback`、`chat-session`、`chat-components` 合计 25/25。
- 首轮浏览器 10 项失败：合成运行未在事件后改为 succeeded，C3 正确拒绝把 running 的旧终态当完成；另停止夹具无法在响应前显示部分文本。修正合成服务状态与夹具，不放宽 C3 断言。
- 第二轮两项测试定位修正：排除 draft 键、按停止状态角色定位，并纳入终稿后的历史刷新请求。
- 最终 `npm run test:thread-chat`：10/10；生产默认发送/停止 2 项，四视口 × 双主题 8 项。全 Axe、横向溢出、小字、朱砂预算、控制台/页面错误、外域请求均为 0；见 `visual-summary.json` 与 8 张截图。
- `npm test -- --maxWorkers=2`：118 文件、1523/1523；`npm run lint`、`npm run typecheck`、`npm run build` 通过。本机 Node `v24.15.0`，CI 固定 Node 22。
- 未验证：真实 PG/生产接口、真实模型、真机与服务器。性能使用独立真实 loopback HTTP 目标，结果另存 `thread-performance/`，不预写达标。
