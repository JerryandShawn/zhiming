# v7 委托额度首片（离线）

北京时间 2026-10-23 22:14；工作树 `v4/first-release-integration-20261023`。

- 新委托入口 `tools/member_delegate.py` 与 `DelegatedSession`；沿用中央 PG 账本，不修改历史 0008。
- PG 为每批最多 10 个物理尝试计数（包括失败和未决预留）；等价验证跨批、跨重启合计最多 20 次。
- 委托评测主模型/评审共用单个 eval 槽；全局两个槽、可信角色、账户身份及来源保护继续有效。
- 只有 PG 签发的保留授权前缀启用 v7 策略，取消旧 80 次预算及冷却；普通交互预算不混入委托用量。
- 权限、usage limit、并发、Access 停止持久化；委托路径不随机重试。仅明确的标准 `Retry-After` 可形成恢复边界；未知时间保持停止，Access 不自动恢复。
- `QuotaGuard` 默认独立 `SystemClock`，可注入实际授权时钟；不使用评测业务 `get_clock()`，HTTP 恢复时间也使用同一中央时钟。
- 真实 CLI 检查当前 HEAD、运行源码清洁、当前源码摘要；三组脚本门必须同一候选/来源、complete、零物理请求、精确场景集合：P3 48 + 日期新增 7 + 原 80 展开 81。合成门显式 `synthetic=True`，真实 CLI 拒绝。
- 脚本门内的 `equivalent=True/False` 自报位一律拒绝；本片生产 core 阶段保持关闭。测试代码显式使用私有 seal 构造 core 替身，不是生产可调用的等价结果入口。

## 验证

唯一目标链：`run_narrow_safe.py`，10 个明确文件：新增 `test_delegated_policy.py`、`test_delegated_quota_pg.py`，原有 quota guard/batches/http/legacy、error classification/member errors/actions/http boundary。

**323 passed in 40.31s**；真实本机隔离 PG 15 + MockTransport，测试时区 Asia/Tokyo，进程凭据清空、追踪关闭。原始本地记录：`private/safe-narrow-228da08708d9405f9fa38db12bc94207/metadata.json`、`pytest.xml`。没有服务器、真实模型或飞书调用。

随后收紧生产 core 门，仅新增关闭门的两条目标断言：**2 passed in 0.08s**，记录 `private/safe-narrow-af42517eb0ca487f99420107f9ee6993/metadata.json`。没有重复跑整链。

包含：81 次物理替身请求分为 10×8+1 九批，随后普通交互仍可用；等价第 21 次拒绝；伪造/重标授权拒绝；eval 单槽及全局双槽；全部停止类别与明确/未知恢复窗；冻结业务时间到过去仍按实际授权时钟运行。Ruff E/F/I/B/UP/SIM 通过（120 列）；新增文件 ≤400 行，函数 ≤60 行。

## Decision

原两条 quota_5h 测试保护“停止持久化”和“不得提前人工清除”。现在显式注入已知的五小时恢复时间，全部原断言保留；新增测试另保“未知恢复时间绝不自行猜测”。旧纯错误分类和人工授权路径保留，未伪造 TTY 或人工同意收据。

## 未完成与边界

完整首发脚本门仍未通过，旧 48/48 报告不能放行；本片没有生成任何真实调用授权。生产 core 阶段封闭；旧 probe 尚未接入新 Session。下一片需要可信真实等价结果：固定用例、两模型完整完成、物理 PG 账本最多 20 次、同候选/来源，然后才能开放 core；当前不能宣称可无人值守完成“等价→核心题”。报告门组合生成及 live/v4 runner 由主线/评测片接线。真实协议、复位头格式和模型质量未验证；停止后旧批次不自动复活，崩溃未决预留不退款、不自动接管。

## 后续离线片：可信等价证明（北京时间 22:36）

- 增加独立本机 PG15 控制 schema（必须 `probe_` 前缀，与中央 schema 分离），只由 `--mode init-control --init-control-schema` 显式初始化；正常运行缺表就关闭，不占用 0009、不修改任何 Core 迁移或 PG 角色。初始化不启动探针。
- 新 `--mode delegated` 保留原人工 `--mode live --grant`；固定现有 EQ01–EQ09：每模型十步，两模型二十步。`DelegatedSession` 按物理十次换批，账户历史所有 probe 预留跨重启、跨候选、跨控制 schema 累计计入同一二十次授权，不能用新 SHA 重置预算。
- 控制库只记录 `check_response` 的公开结果与中央实际 attempt 指纹，证明绑定 candidate/source/固定合同、中央 account/identity/location、控制库位置及 evaluation_session_id。`load_core_approval` 回查全部二十步 PG 记录后才产生 core 批准；自报布尔、mock 证明、缺题、账户/来源/账本变动均不能开启。
- 完整不等价可选 k3；额度中止保持 incomplete/equivalent=null，不能伪装成不等价。已失败一次即不足以在原二十次内补齐全部二十成功步，保持停止等待新预算裁定。恢复头只保留已知时间，不猜；Access 不恢复。跨进程遗失 EQ09 私有多轮状态时保守关闭，不重发已完成步骤。报告与控制结果没有原始 reasoning、签名、header 或密钥。
- 唯一新目标链 **17 passed in 34.38s**（新真实 PG/control proof + 旧 probe 兼容），`private/safe-narrow-3e95f6eb8651485199c2223ddd7757f2/metadata.json`；测试替换 HTTP，测试临时控制 schema 随后删除，真实模型/服务器/飞书均 0。测试 token 已释放，未重复宽验。
- 这完成离线控制机制与证明校验，尚无真实等价证据，完整脚本门未绿，不能启动真实探针或宣称模型等价。Core30 调用与 fallback 模型装配由评测片接线；生产配置仍锁 k3-256k 时，不会悄悄改为 k3。
