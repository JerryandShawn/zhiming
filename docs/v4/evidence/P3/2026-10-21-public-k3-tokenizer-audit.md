# 公开 K3 tokenizer / encoder 只读审计

截至：2026-10-21 01:46，北京时间（UTC+08）。结论：**已找到可固定身份的官方 K3 词表与代码；当前真实发送仍未就绪，阻塞是锁定环境没有受信 encoder / artifact 接线。** Z1 已允许估算，不再把会员 framing 等价证明列为本片解除阻塞的必要条件。

本次只读主仓文档、源码、锁文件与两个 Core 环境的安装元数据，并 GET 官方公开资料。未安装依赖、未改锁、未加载或执行远程代码、未下载词表或权重、未跑测试、未连接数据库/服务器、未调用模型或发送飞书。下面的安装/加载步骤都是后续方案，没有执行。

## 1. 仓库约束与现状

28 号第二节 Z1 要求公开 K3 计数 ×1.15+4000 的**估算上界**，记录版本和 hash；actual 超过原上界时告警并提高系数。180k 硬门、完整请求计数和人工批次门仍独立存在，不可用字符串长度、K2 分词器或合成计量替代 K3。

33 号公共规则第 4 项原文：**“不新增依赖：需要新依赖就记进待决，先用已锁定的依赖做。”** 因此本报告只提出依赖候选交大脑裁定，不能自行安装或更新锁。

`mingjing_core/agent/context_k3.py` 已有 `PublicK3Counter`、`PinnedK3Counter` 与 `K3EstimatedMeter`：可信应用必须同时固定本机词表和 encoder artifact 的身份，再注入实际编码函数。`PinnedK3Counter` 自身只检查给定路径/hash，并不能证明任意传入 callable 来自该文件；真实 loader 仍需验证函数与已审代码的绑定。默认 `live_admissible=False`。现计量器把完整 messages/tools/tool_choice 规范化 JSON 交计数器，不能假称它就是供应商 XTML 或 HTTP framing。

对 `requirements-core.lock`、`requirements-test.lock`、`requirements-charts.lock` 的包名检查，均未包含下列候选依赖；对主仓 `.venv-core` 和本轮真实 PG 使用的 `zhiming-v4-p2/.venv-core` 进行 `importlib.metadata` 只读查询，也均显示未安装：tiktoken、transformers、tokenizers、huggingface-hub、regex、blobfile、torch、numpy、safetensors。没有扫描私人缓存或声称整台电脑都不存在这些包。已有 Z1/Z2 脚本证据继续有效，但不代替真实编码器的加载证据。

## 2. 官方身份链：确实是 K3

[MoonshotAI 官方 K3 仓库](https://github.com/MoonshotAI/Kimi-K3) 与 [moonshotai 官方 HF 模型仓](https://huggingface.co/moonshotai/Kimi-K3) 公布 K3。官方 [Kimi Code 模型配置](https://www.kimi.com/code/docs/en/kimi-code/models.html) 将 `k3` 与 `k3-256k` 都列为 K3，后者上下文为 262144；同时明确 `kimi-for-coding` 是 K2.8 Preview，不能据名称把它当 K3。此处不采用第三方转换仓、HF PR 分支或 K2 词表。

本次无凭据 GET 的 [HF 官方仓元数据](https://huggingface.co/api/models/moonshotai/Kimi-K3/revision/f831ab66814297da540d832a5235f8e904f29d06?blobs=true) 返回：

| 项目 | 实际值 |
| --- | --- |
| repo id | `moonshotai/Kimi-K3` |
| 固定完整 revision | `f831ab66814297da540d832a5235f8e904f29d06` |
| main 最近修改时间（服务端元数据） | `2026-09-02T02:22:41.000Z` |
| gated | `false` |
| config model_type | `kimi_k3` |
| text_config.vocab_size | `163840` |
| text_config.transformers_version | `4.56.2`，配置声明而非本机兼容测试 |

**官方同代模型身份已证；会员服务使用的具体 tokenizer revision/hash、计费 framing 和实际 usage 等价没有证明。** 不能把公开仓 revision 冒充会员服务部署版本。按 Z1，它可成为本地估算计数来源；实际误差需以后在独立授权的真实调用中观测，本次不发探针。

## 3. 可固定的最小公开文件

以下均来自同一个完整 revision。词表 SHA 是官方 LFS 元数据，**本次没有读取词表字节，尚未做下载后 SHA 复核**。其余列出的 JSON/Python/LICENSE 仅在内存读取原始字节、计算 SHA256 后作静态阅读，未保存、导入或执行。

| 文件（不可变官方 URL） | 字节 | SHA256 | 证据类型 |
| --- | ---: | --- | --- |
| [tiktoken.model](https://huggingface.co/moonshotai/Kimi-K3/resolve/f831ab66814297da540d832a5235f8e904f29d06/tiktoken.model) | 2795286 | `b6c497a7469b33ced9c38afb1ad6e47f03f5e5dc05f15930799210ec050c5103` | LFS 声明；未下载复核 |
| [tokenization_kimi.py](https://huggingface.co/moonshotai/Kimi-K3/resolve/f831ab66814297da540d832a5235f8e904f29d06/tokenization_kimi.py) | 16145 | `f28ea66e2d862a2a5814970b2ce40c2f7d8296ff09aed90a7e7def689b906944` | 本次原字节计算 |
| [encoding_k3.py](https://huggingface.co/moonshotai/Kimi-K3/resolve/f831ab66814297da540d832a5235f8e904f29d06/encoding_k3.py) | 26304 | `49ff03305fdc4be26867972788d36150b67f8a9e852e62bb7959d87482223676` | 本次原字节计算 |
| [tokenizer_config.json](https://huggingface.co/moonshotai/Kimi-K3/resolve/f831ab66814297da540d832a5235f8e904f29d06/tokenizer_config.json) | 3478 | `5d0803c94db9cd78763499e0956c95fd5a225c14a727e5a6cf5db3f96f010a6e` | 本次原字节计算 |
| [config.json](https://huggingface.co/moonshotai/Kimi-K3/resolve/f831ab66814297da540d832a5235f8e904f29d06/config.json) | 7006 | `9710e121a58d03ac92c8d6da287a19541994319afbbe6d6202af001ffd379213` | 本次原字节计算 |
| [LICENSE](https://huggingface.co/moonshotai/Kimi-K3/resolve/f831ab66814297da540d832a5235f8e904f29d06/LICENSE) | 3065 | `20c797ce19af0c17de52c6afb144644768a591c521655f5ebf5712c9850f2887` | 本次原字节计算；分发时保留 |

不能只固定词表而忽略 encoder。官方 [tokenization_kimi.py](https://huggingface.co/moonshotai/Kimi-K3/resolve/f831ab66814297da540d832a5235f8e904f29d06/tokenization_kimi.py) 包含 K3 的切分 pattern、特殊 token 配置和分块逻辑；其依赖包括 tiktoken、tokenizers、transformers。`tokenizer_config.json` 的 `AutoTokenizer` 映射到 `tokenization_kimi.TikTokenTokenizer`，并提供特殊 token ID。仅文件名相同不能保证另一模型或另一 revision 等价。

官方 [encoding_k3.py](https://huggingface.co/moonshotai/Kimi-K3/resolve/f831ab66814297da540d832a5235f8e904f29d06/encoding_k3.py) 负责 XTML、工具参数/工具结果排序和 thinking 等聊天渲染。这是 renderer，不是可单独代替 BPE 的词表。Z1 的规范化 JSON 估算不需要声称重建该服务端渲染器，但加载官方 tokenizer 会导入它，仍须固定并审阅。

## 4. 本机加载方式：可实施候选，未执行

最小路径是保留官方代码，不自写分词器。将上表少量文件放入专用、非 symlink、不可随意改写的本机目录，逐文件验 hash；后续 loader 只接收固定目录。调用 `AutoTokenizer.from_pretrained` 时限定该本机目录、`local_files_only=True`、`trust_remote_code=True`、`use_fast=False`，不传模型仓在线名字，也不调用 AutoModel、pipeline、processor 或推理服务。设 `HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1`、`HF_HUB_DISABLE_TELEMETRY=1`，测试层拒绝任何外部 HTTP。这里的 trust_remote_code 会执行本机自定义 Python，必须先完成代码审阅/逐文件固定；本次没有执行。

计数 seam 接收的是普通用户/工具字符串，须使用官方 `encode` 的 `allow_special_tokens=False` 路径，避免正文里的 K3 控制标记被折叠为控制 ID。不要只传默认 encode，也不要混入额外 kwargs 后误走父类路径。计数只取真实整数 token IDs 的数量，沿用 Z1 的 1.15+4000、actual 告警与自动调系数，不回填成供应商精确 token。

官方 [tiktoken 0.13.0 的读取实现](https://github.com/openai/tiktoken/blob/0.13.0/tiktoken/load.py) 支持本机文件直接读取；本机读取词表本身不要求 blobfile。不能误用在线内建 encoding 自动拉取词表。官方 tokenizer 的其余依赖及传递依赖仍要统一解析和锁定。

以下为 PyPI 发布者的版本元数据候选，**没有下载 wheel、安装或做兼容实测，也不是推荐直接放宽现锁**：

| 候选版本与官方元数据 | Windows Python 3.11 可选 wheel | 发布元数据 SHA256 |
| --- | --- | --- |
| [transformers 4.56.2](https://pypi.org/pypi/transformers/4.56.2/json) | `transformers-4.56.2-py3-none-any.whl` | `79c03d0e85b26cb573c109ff9eafa96f3c8d4febfd8a0774e8bba32702dd6dde` |
| [tiktoken 0.13.0](https://pypi.org/pypi/tiktoken/0.13.0/json) | `tiktoken-0.13.0-cp311-cp311-win_amd64.whl` | `fc1c44cd37b43fc46bae593129164f4f281e82ea116b57a85aa81bda57eafc94` |
| [tokenizers 0.22.2](https://pypi.org/pypi/tokenizers/0.22.2/json) | `tokenizers-0.22.2-cp39-abi3-win_amd64.whl` | `c9ea31edff2968b44a88f97d784c2f16dc0729b8b143ed004699ebca91f05c48` |

发布元数据声明：这三个版本都接受 Python ≥3.9；transformers 4.56.2 需要 tokenizers >=0.22.0,<=0.23.0，候选 0.22.2 在此范围内。transformers 还需要 numpy、huggingface-hub、regex、safetensors 等基础依赖；不能只锁表中三个 wheel 就宣称依赖闭包完整。这些候选的本机运行、Linux wheel、传递依赖与现有 Core 锁冲突均尚未验证。

## 5. 待大脑决定与最小下一步

待决只有：33 号“禁止新依赖”下，是否批准单独增加**本地 tokenizer 所需的受限依赖闭包**。建议由大脑批准后再新增专用、hash 完整的 tokenizer 锁或审查后并入 Core 锁，保留其他线锁不变；本报告不执行此建议。

获准后最小实现为：仅下载约 2.8MB 词表及上表必要小文件，固定完整 revision 并实算 SHA；在隔离环境按 hash 锁安装批准依赖；加载本地官方类并证明零网络；用中文/英文/代码/Unicode/空白/字面控制标记/长无标点和完整工具循环 JSON 做离线 ID/计数与确定性验证；错 hash、错 revision、非 K3、漏依赖、无 artifact 或计数异常必须失败关闭。

可信加载器还须逐项验证代码/配置/依赖身份，再将**实际被调用的编码函数**绑定到 `PinnedK3Counter`；现有两路径 hash 检查不能由一份自填 manifest 或 `live_admissible=True` 替代这种绑定证明。全部离线证据完成后才讨论真实装配；物理 HTTP 中央守卫、人工批次开始、额度规则和 D2 等价性条件仍独立成立。

公开资料/源码/词表的 GET 是 artifact 获取，不是 Kimi 会员推理请求；安装依赖、执行 tokenizer、调用模型也是三个不同步骤。本次仅完成公开元数据与少量源码静态审计，后面各步骤均未做。**真实发送维持失败关闭；原因是未获批准的新依赖和未实现受信本机 encoder，不是重新要求 Z1 已豁免的 framing 等价证明。**
