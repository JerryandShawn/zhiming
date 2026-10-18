# P1b M2a：离线请求预检子范围（2026-10-18，阶段未完成）

最新状态（2026-10-18 18:29 +08:00）：root已采纳独立复核，默认1.8MB现仅用于K3；非K3只有显式max_request_bytes才检查。最新复验为新增138/0.31s、相关既有244/0.96s，最新六文件hash见文末“兼容性收窄复验”。下方18:22首轮命令/结果/hash及当时待核事项保留为历史；当前状态以文末追加记录为准。

记录时刻：2026-10-18 18:22 +08:00。本次只实现和验证现代模型端口的请求预检；U38 与完整 U39、真实探针、实际模型切换均未完成。

## 源码身份与文件边界

工作树为 `C:/Users/Administrator/Documents/Codex/zhiming-v4-p1b`，分支 `v4/p1b-k3-hardening`，基底及测试期间 HEAD 均为 `a0788aaf86fb278e95cd9a9c174b8fa877862dde`。本次六个源码/测试文件尚未提交；证据绑定下列完整 SHA256，不虚构本次 commit 或 tree。提交、发布、精确头 CI 由 root 统一完成，P1b 不因本子项通过而合并。

只新增 `models/request_policy.py` 与两个 `test_request_policy*.py`，窄改 Anthropic/OpenAI 两协议适配器与 transport。未改 errors、YAML、Registry、quota_guard、迁移0008、旧 ConfiguredModel、冻结 E1 来源、daily、前端或命理代码。新文件首次 exclusive 创建，后续每次源码改写均先比较预期 SHA256；未检测到未知同文件写入。六个源码/测试文件完成验证后冻结，本次收尾仅新增本文并追加 ExecPlan 四节。

| 文件（仓库相对路径） | SHA256 |
| --- | --- |
| `mingjing_core/models/request_policy.py` | `93db8f5b7cff9c5c5706637299651d3768910a996c901286027f49622c74dde4` |
| `mingjing_core/models/anthropic_messages.py` | `18f23496526f6188a1d613c59c99924f529857ddf5115721f519782b10ba8148` |
| `mingjing_core/models/openai_compat.py` | `3f14a3d884ffe7029f6ca6c7d734aa8a8297c6a82ced675a20aa9a01220aac53` |
| `mingjing_core/models/transport.py` | `635882bad695cc3edbaf3a70ab9dab28dfd1f23d92ecee443a845bb887b3e5fd` |
| `tests/v4/models/test_request_policy_wire.py` | `c0d61cff8b231c75db16c4a4d644e29352b48b48bd8818d94bfa34653b20399c` |
| `tests/v4/models/test_request_policy_size.py` | `884fdc6fcefa90c7238176b970964acc0e284c8f07ec10754cdd89d91092c71c` |

## 实际命令、环境与结果

所有命令的 cwd 均为上述 P1b 工作树。测试解释器固定为 P2 Core：
`C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe`。

两次测试启动前，均由这个解释器的 Python 父进程复制环境、删除变量名中含 KEY/TOKEN/SECRET/PASSWORD/PASSWD 的全部项，并设置 LANGSMITH_TRACING、LANGCHAIN_TRACING_V2、LANGCHAIN_TRACING、LANGCHAIN_CALLBACKS_BACKGROUND 为 false，OTEL_SDK_DISABLED 为 true；不打印任何变量值。每次先核对六文件及未改 errors.py 的预期 SHA256，再以 `subprocess.run(..., env=clean)` 启动以下实际子进程命令。外部 HTTP 全部由 MockTransport 替代，不连接真实供应商。

新增两模块的实际子进程命令：

    C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe -X utf8 -m pytest tests/v4/models/test_request_policy_wire.py tests/v4/models/test_request_policy_size.py -q

实际输出：`122 passed in 0.30s`，退出0。

八个相关既有模型模块的实际子进程命令：

    C:/Users/Administrator/Documents/Codex/zhiming-v4-p2/.venv-core/Scripts/python.exe -X utf8 -m pytest tests/v4/models/test_protocols.py tests/v4/models/test_stream_safety.py tests/v4/models/test_schema_registry.py tests/v4/models/test_error_actions_transport.py tests/v4/models/test_registry_retry_ownership.py tests/v4/models/test_k3_config_policy.py tests/v4/models/test_k3_config_integration.py tests/v4/models/test_probe_guard.py -q

实际输出：`244 passed in 1.22s`，退出0。以上合计366项为本次限定范围检查，不是全 models、全部v4、旧Core或完整CI。

静态检查使用现有 Ruff 可执行文件；没有安装或升级依赖：

    C:/Users/Administrator/Documents/Codex/zhiming-v4/.venv-core/Scripts/ruff.exe check --no-cache --select E,F,I,B,UP,SIM --line-length 120 mingjing_core/models/request_policy.py mingjing_core/models/anthropic_messages.py mingjing_core/models/openai_compat.py mingjing_core/models/transport.py tests/v4/models/test_request_policy_wire.py tests/v4/models/test_request_policy_size.py
    C:/Users/Administrator/Documents/Codex/zhiming-v4/.venv-core/Scripts/ruff.exe format --no-cache --check --line-length 120 mingjing_core/models/request_policy.py mingjing_core/models/anthropic_messages.py mingjing_core/models/openai_compat.py mingjing_core/models/transport.py tests/v4/models/test_request_policy_wire.py tests/v4/models/test_request_policy_size.py
    git diff --check

实际输出：Ruff `All checks passed!`、formatter `6 files already formatted`、diff检查退出0。另用同一 P2 Core 解释器经 stdin 运行 ast.parse/函数长度与注解检查；六文件均为 UTF-8 LF，完整注解，最大256行/文件、52行/函数、120字符/行。本次没有执行 coverage run，不给出新增代码或当前整包覆盖率；此前U37首切片的903/944、95.6568%不能自动当作本次M2a的覆盖率。

测试结果取本轮实际终端输出，未另建或改写旧测试日志。先行静态检查发现一个未使用 import 及两个新测试文件的格式问题，已在 SHA256 写保护下修正，再完成上述最终检查；没有改旧测试来迁就实现。

## 已验证行为覆盖

| 行为 | 本次可观察断言 |
| --- | --- |
| K3安全工具选择 | 两协议的 k3/k3-256k/kimi-k3 对 none、指定工具名与 named 拒绝；tools 为 None、空列表或非空时均为零HTTP、零meter、零request_count |
| 单工具与多工具 | 仅暴露一个K3工具时强制required（Anthropic的any）；仍要求caps支持required。多工具保留安全auto/required；没有静默修改caps |
| 纯文字 | K3无工具时请求不含tools和tool_choice字段；非K3原有none/named及无工具省略行为保持 |
| 固定采样能力 | sampling_fixed=true时从最终请求剔除temperature/top_p，即使调用参数或settings提供值；输入body不被修改，非固定采样的显式temperature保留 |
| 实际请求字节 | 先由client.build_request按httpx生成完整JSON请求，再检查request.content，最后client.send发送同一个Request；检查覆盖中文UTF-8、转义、图片与工具schema，不是只算消息正文 |
| 体积边界与计数 | 默认十进制1,800,000字节，settings.max_request_bytes可配置为正整数；等于上限可发送，比实际字节数少1的限制拒绝；1.9MB大请求在before_provider_request和request_count之前抛ModelPayloadTooLarge，且不重试 |
| 本地失败边界 | 无效体积限制、序列化失败、预先取消均不发HTTP、不增加物理计数；meter拒绝可触发一次回调但仍不发HTTP、不增加request_count；诊断不回显合成正文 |
| 相关契约回归 | 既有协议解析、可见输出不重播、取消/deadline、schema/Registry、单层重试、禁关思考与probe额度停止检查通过；未扩大为真实供应商证明 |

## 未验证、未闭环与下一步

体积守卫范围需由root核对：当前默认1.8MB检查无条件施加在共用StreamingHTTP，包含非K3；因此非K3先前可发送的大于1.8MB包体现会被拒绝。现有非K3回归仅证明工具选择/采样字段契约，未加入非K3大包兼容负对照。实现采用了增补D的共用请求保护解释；若主线“非K3旧契约保持”也要求保留旧大体积行为，则应由root决定收窄为K3或显式配置该限制。此处如实记录边界，不宣称已满足所有非K3兼容性；六源码/测试保持冻结。

U38中央PG账本、跨进程槽位、持久全停、所有入口接线与0008迁移未在本子项实现或验证。这里的meter与request_count断言是现有请求边界检查，不等于PG账号级计费或持久守卫已完成。

U39仅完成上述请求预检：完整推理/签名回传、缺签名按设计回传与计数、effort锁定及真实供应商兼容仍未完成。缺签名原行为未改；没有通过翻YAML开关掩盖缺口。sampling_fixed过滤实现已有替身证据，但本次没有修改config/models.yaml的caps或移除其中历史采样配置，因此不能声称当前默认配置已启用完整固定采样策略。

人工批次启动门、新256k候选配置/兼容E1来源、等价性子集、真实探针和实际模型切换均未完成。测试里使用合成k3-256k标识不构成真实模型切换或能力证据。D1继续会员端点、明确逐批开始、每批不超过10、批间20分钟、滚动5小时80次共享实际POST以及夜间零请求等决定不变。

本次未跑全models覆盖率、旧Core、全v4、脚本评测、真实PG集成或CI，也没有服务器、stage/生产、真实飞书或真实模型请求；不借用此前全量日志作为这六个改动的重新验证。P1b阶段保持未完成，由root继续做U38/U39其余部分与精确头验证后再决定验收。

## M2a兼容性收窄复验（最新，2026-10-18 18:29 +08:00）

root采纳独立只读复核后的明确决定：P1b是K3专项，须保留非K3原有协议契约，不能无声给全供应商新增默认体积限制。此前首轮记录中的非K3大包兼容边界已通过这次收窄解决，不再是待root决定的问题。

### 本次最小修正

request_policy.py新增is_k3(model)，沿用原先strip/casefold后识别k3或kimi-k3前缀的同一身份判定；safe_tool_choice和默认体积检查共用该谓词。check_request_size现在接收model/settings：K3未配置限制时默认1,800,000字节；非K3缺少max_request_bytes时不增加默认限制。任何模型只要显式设置该字段，仍检查正整数限制；显式None、False、0、负数、浮点数或字符串均失败关闭，不能被当成“未配置”。

transport仍先让httpx序列化完整JSON，再检查并发送同一个Request，meter/request_count顺序没有变化。只修正request_policy.py、transport.py与新增size测试；另外三文件不变。errors、YAML、Registry、旧适配器、U38、迁移和冻结E1来源仍未改。所有写入前继续核对hash，最终六源码/测试再次冻结；没有commit/push。

### 最新源码身份与hash

本次仍基于HEAD `a0788aaf86fb278e95cd9a9c174b8fa877862dde` 的未提交改动。下表绑定最新复验源码，不能使用首轮hash替代。

| 文件（仓库相对路径） | 最新SHA256 |
| --- | --- |
| `mingjing_core/models/anthropic_messages.py` | `18f23496526f6188a1d613c59c99924f529857ddf5115721f519782b10ba8148` |
| `mingjing_core/models/openai_compat.py` | `3f14a3d884ffe7029f6ca6c7d734aa8a8297c6a82ced675a20aa9a01220aac53` |
| `mingjing_core/models/transport.py` | `87f4e56eff9d7b3f7055e991d7aba610858c009aad609b369673bd802715bc70` |
| `mingjing_core/models/request_policy.py` | `e2704ead07779c9a3945cb2653f450e0ba241ea7ebd7b8ef9b4f5ae99ff1152a` |
| `tests/v4/models/test_request_policy_wire.py` | `c0d61cff8b231c75db16c4a4d644e29352b48b48bd8818d94bfa34653b20399c` |
| `tests/v4/models/test_request_policy_size.py` | `932eb977369e7e0055f792598c9f8e8366f517425b209cbfb08e303f3cc56b46` |

### 最新实际复验结果

cwd、P2 Core解释器和清凭据/关追踪父进程与前文完全相同；只重新执行前文列出的两条实际pytest命令（新2模块、相关旧8模块），没有增加测试范围或调用真实供应商。

| 本轮检查 | 实际输出 |
| --- | --- |
| test_request_policy_wire.py + test_request_policy_size.py | `138 passed in 0.31s`，退出0 |
| 前文列明的8个既有相关模型模块 | `244 passed in 0.96s`，退出0 |
| 同前文六文件Ruff check / format --check命令 | `All checks passed!` / `6 files already formatted` |
| AST/注解/UTF-8 LF | 最大256行/文件、52行/函数、120字符/行；注解完整、UTF-8 LF |
| git diff --check | 退出0 |

本轮限定范围合计382项。新增对照在两协议上证明：非K3默认可以发送实际序列化后超过1.8MB的请求（1个HTTP/1次meter/1次request_count）；同一非K3设置显式1.8MB限制后零HTTP/零meter/零计数拒绝；无效显式配置在K3和非K3上均零HTTP/零meter/零计数拒绝。既有K3大包、精确字节边界、选择/采样与安全回归仍通过。

没有运行coverage、全models、旧Core、全部v4、脚本评测、PG或CI；不新增覆盖率百分比，不把首轮或更早整库成绩套在本次源码上。仍无真实模型、服务器、stage/生产或真实飞书请求。

### 未闭环范围

非K3默认大包兼容问题已修正，默认K3的sampling_fixed YAML接线、完整reasoning/签名/缺签名策略、effort、U38中央守卫与0008/所有入口、人工批次门、候选模型配置、真实探针/等价性和实际256k切换依旧未完成。P1b阶段未完成；本记录只更新M2a可观察子范围。已通知独立eval审计代理在冻结源码上只读复核，不把发出复核请求当成审计通过。
