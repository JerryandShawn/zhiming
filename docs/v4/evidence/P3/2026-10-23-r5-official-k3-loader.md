# P3 R5：固定官方 K3 本地计量器

2026-10-23 21:33 +08:00。35 号 R5 批准的唯一依赖例外；只用于 TokenMeter，不加载模型权重，不进行推理或真实供应商调用。尚未提交，由主线统一审核。

## 实现与复现

根 `k3-tokenizer.lock.json` 固定官方 `moonshotai/Kimi-K3@f831ab66814297da540d832a5235f8e904f29d06` 的词表、两个 Python 文件、两个配置及 LICENSE，共 6 文件、2,851,284 字节，实算 SHA256 全部符合前审计。锁自身摘要也由本地校验器固定，不能用自填 manifest 换 revision。官方代码保持原样，仅保存在忽略的 `private/artifacts/`，不作为自造分词器提交。

`python -m tools.install_k3_tokenizer --destination <专用绝对目录>` 只 GET 该 revision 的固定小文件，限制 HTTPS 官方跳转，写入前核对长度与 SHA；已有错误文件拒绝覆盖。`--verify-only` 完全不下载，可用于部署检查。工具已对全新本机目录真实获取六文件并随后完成 verify-only。没有下载权重。

`load_k3_counter(Path目录)` 只读取本机文件，拒绝缺文件、错 SHA、符号链接/重解析路径和缺失/错误版本依赖。它执行已验字节并直接实例化官方 `TikTokenTokenizer`，把该实例真实的 `encode(allow_special_tokens=False)` 绑定给 `PinnedK3Counter`；不调用 Hub、AutoModel、pipeline 或在线 from_pretrained，也不接受任意注入的 encode 函数。估算仍是规范化完整请求 JSON 的真实编码数 ×1.15 向上取整 +4000；保留校准与180k守卫，不声称等于会员 XTML 或供应商 actual usage。

根 Core 锁保留既有 58 个包的版本，只追加批准闭包的 11 个新包名、12 段 pin（numpy 按 Python 条件区分），保留解析产物全部 hash。专用 `.venv-k3` 按根 Core/test hash 锁安装成功；`uv pip check` 检查 74 包兼容。没有改动现用 Core 或 P2 环境。计量器新增可选配置 model 身份；RequestLedger 校准重建保留该身份。

## 定向证据

在专用 `.venv-k3`，清凭据、关闭追踪、显式 Asia/Tokyo，并在测试内拦截 socket 连接及 DNS；实际官方加载与编码没有网络尝试。目标为 `test_k3_loader.py`、`test_k3_model_identity.py`、既有 `test_context_k3.py`。

- 初链 41 passed、1 failed/7.14s；失败为新完整工具消息夹具漏传同一 `tool_cycle`，原上下文守卫正确拒绝。只补新夹具配对标记后，该单例 1 passed/1.20s，保留原全部计量断言；未将两次运行冒充一次全绿回归。
- 新增公共入口缺依赖先拒绝及损坏下载不得落盘两例：2 passed/0.16s。
- 覆盖中文、英文、代码、Unicode、字面控制标记、210,007 字无标点文本、空串、完整 system/user/assistant/tool 循环及工具 Schema。控制标记按普通 BPE 编码；官方解码逐字往返；完整请求的 estimate/upper/actual 分离。六个文件各自同尺寸内容损坏均拒绝执行，缺配置、错锁、错依赖版本同样失败关闭。原估算公式/校准/硬门目标保持通过。
- Ruff E/F/I/B/UP/SIM 与 120 列格式检查通过；私有日志/JUnit 为 `private/k3-offline-20261023/`，依赖安装记录为 `private/k3-install-20261023.log`。

本机安装目录为 `private/artifacts/kimi-k3-installer-20261023`。真实 artifact 测试使用显式 `K3_TOKENIZER_ARTIFACT_DIR`；未安装时该组明确跳过，不自动联网或伪造 encoder。实际生产装配由主线接线，缺依赖/文件应继续拒绝启用。尚未做 Linux 安装或供应商计费等价性测试；真实模型请求、飞书发送、服务器访问均为 0。
