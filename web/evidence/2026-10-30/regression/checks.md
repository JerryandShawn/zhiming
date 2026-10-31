# 最终前端回归汇总（2026-10-31，北京时间）

- 环境：本机 Node `v24.15.0`；CI 固定 Node 22，结论另核，不混称。
- `npm test -- --maxWorkers=2`：**119 文件、1531/1531**，失败/跳过 0。
- `npm run lint`、`npm run typecheck`、`npm run build`：通过。
- 最终完整 `npm run test:e2e`：**542/542**，全串行，失败/flaky/跳过 0：
  - static 133/133（含 legacy、H5、课程、thread-chat 与 `/v4/` 项目）
  - spaces 15/15
  - components 10/10
  - components-visual 64/64
  - night 220/220
  - overnight-visual 88/88
  - thread-chat 10/10
  - `/v4/` 2/2
- 过程保留：首轮 204 过/16 EEXIST，第二轮 night 197 过/23 EEXIST，均因 `wx` 写固定历史截图；默认输出改到带批次号的 ignored 目录。第三次 night 219/220，唯一 `ERR_NO_BUFFER_SPACE` 在并行 preview 资源竞争后出现，单独串行复验通过；最终不并行套件、不屏蔽 console、不删测试。
- `/v4/` 首轮截图误用默认 1280 宽，已显式 390×844 重拍并人工核图。
- 历史被覆盖的已跟踪证据已恢复；新未跟踪输出移到 ignored `test-results/full-e2e-generated/`，没有删除历史文件。
- `10bd5e81` 精确头 frontend/Core 四个 CI run 全部 success；监视过程一次 TLS 握手失败不是产品失败，最终 API 元数据已复核。
- 未验证：真实 API/PG、生产 CSP/反代、真实飞书和真实模型。性能旧页 2572ms、课程 5020ms、spaces 4148ms、v4 对话 5840ms 均未过 2500ms，回归与 CI 全绿不等于性能或上线就绪。
