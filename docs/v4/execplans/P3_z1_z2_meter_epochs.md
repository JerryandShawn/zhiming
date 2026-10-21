# P3 Z1 / Z2：估算发送闸门与 L5 压缩周期

本子计划承接 `P3_agent_runtime.md`。时间全部为北京时间（+08:00）。依据交付 28 号第二节 Z1、Z2；本片不接触 events、envelope、工具可见性或 `loop_cycle.py`。

## Progress

- [x] 2026-10-20 23:13：完整读裁定、四个上下文模块、来源/依赖读取、Loop 消费端和既有测试；未找到已安装的可信 K3 编码依赖。仓库旧文档只保留了“曾核公开词表 / XTML”的研究结论，未给出可直接启用的本机 artifact 路径与锁定依赖。
- [x] 2026-10-20 23:17：Z1 受信计数 seam、两个 artifact 的版本/hash 核验、`ceil(count × factor)+4000`、独立 estimate / upper / actual、实际超估算告警及持久因子完成；86 项目标测试通过。
- [x] 2026-10-20 23:22：Z2 元数据周期准备与发送预留事务完成；126 项目标测试通过，包含真实 PG 并发、撤销、41/50/51 轮窗口换代。
- [x] 2026-10-20 23:26：新增“重复构建相同压缩结果不换 epoch”与估算标签反例后，128 项目标测试通过（14.77 秒）；真实 PG R07 / 万消息压力 2 项通过（55.60 秒）。R07 300 scripted calls、600 原消息；万消息原话 hash 不变、读取候选 ≤81，全部仍为 policy_units / 合成调用，provider calls 0。
- [ ] root 接入 Loop 每次物理发送前的准备 / 预留与完成后 usage 记录；真实 K3 encoder 需从既有锁依赖 / 经审本机 artifact 接入，默认仍拒绝未配置。

## Context and Orientation

`agent/context_k3.py` 只定义计量适配器，不下载、不重写 tokenizer。`PinnedK3Counter` 校验本机词表与 encoder artifact 的 SHA-256 / 版本，由可信应用接线绑定实际 `encode(text)->token IDs`。脚本计数器的 `live_admissible` 默认为 false；未配置抛 `InputMeterUnverified`。

`application/context_usage.py` 从持久已完成模型步骤读取供应商 usage，按步骤防重放记录。因子按线程及 provider/model/tokenizer/encoder 身份隔离；相同身份跨重启保存，新身份回到 1.15。`ContextUsageService.factor` 给下一次预算读取因子。实际超过估算上界，receipt 写告警并将 factor 提升到 `actual/estimate × 1.1`，不改写估计、原上界或实际值。

`ContextEngine.build` 只读生成 `ContextBuild.cache_epoch`。`agent/context_epochs.py` 对 canonical message fragments 计 hash：缓存前缀为 L0、L2、L3_STABLE、L5；L1 / L4 / L3_VOLATILE / L6 / CYCLE 不纳入稳定缓存前缀。L5 在同 epoch 已发出的 message-fragment 字节只能追加；压缩改变窗口或撤销 / 有效源 revision 改变，才开启新周期。这里的 canonical hash 是应用审计标识，不声称等于供应商私有 framing 或缓存命中计量。

`application/context_epochs.py` 的 `mark_sent` 是**发送前预留**：在 run 租约 / retry_epoch 校验及线程 advisory lock 的同一事务内，核真实步骤 input_fp、当前来源、撤销账本、预算实际 prefix 与缓存代次，重新计算计划，再持久化 metadata-only 周期与 run usage 发送标记。并发同一旧代次只能一个提交。它不证明请求已被远端接受，也不跨 HTTP 持有数据库事务。

## Decision Log

- 2026-10-20 / Z1 取代旧“必须证明会员 framing 等价”约束：估算上界按裁定放行，保留人工批次授权和独立物理 HTTP 守卫。公开计数未配置仍拒绝；不能拿 `strlen`、FTS tokenizer 或 UTF-8 字节冒充公开 K3 token。
- 2026-10-20 / 修改既有测试理由：旧 `TokenReading(2,4,5)` 测试将 actual 超 upper 视为计量损坏；Z1 明确要求保留这种观测并告警 / 校准，因此改成独立保留测试。负数、布尔、未知上界、估算大于上界仍拒绝，原安全契约未删。
- 2026-10-20 / 不改冻结 b9 包或旧迁移；epoch 与校准使用 v4 现有 thread / run usage 元数据，不新增迁移号。
- 2026-10-20 / 相同压缩结果重复构建不反复换周期；只有改动已发 L5 / 窗口的压缩触发新 epoch，避免每次读快照都导致缓存抖动。撤销 / 旧依赖 revision 改变仍强制新周期。
- 2026-10-20 / Loop 文件归 root 接线：本片给出完整可测服务和接口，不能把未接 Loop 的服务算物理 HTTP 全入口已受保护。

## Surprises & Discoveries

- 现有 history grouping 会在原 user ContextItem 后追加 assistant message。若比较整个 item JSON 会误判已有内容被改写；按每条规范化 message 的字节 fragment 比较，能保留真实 append 行为。
- 撤销 source span 时，原 message 的 revision 不一定单独表达投影改变；发送前同时检查较 snapshot 新的相关撤销账本，不能只看 message revision。
- usage 与 epoch 都更新 thread 元数据，统一使用相同线程 advisory lock，避免一方覆盖另一方持久状态。

## Validation Strategy

只用本机隔离 PG、FrozenClock、httpx 禁网替身 / 受控计数 seam；清凭据、关闭追踪。新 Python 文件 ≤400 行、函数 ≤60 行。先跑新增 pure / PG 与既有上下文目标，再重跑真实 PG 的 R07（300 轮）和万消息压力；压力 token 数仍标 synthetic / policy_units。

## Outcomes & Retrospective

当前服务级 Z1/Z2 已有真实 PG 定向证据。真实 K3 tokenizer、Loop 物理发送接线、端点 actual 校准、供应商缓存命中和人工真实批次均未验证；本夜实际模型请求数为 0。最终测试与接线说明见 `docs/v4/evidence/P3/2026-10-21-z1-z2.md`。
