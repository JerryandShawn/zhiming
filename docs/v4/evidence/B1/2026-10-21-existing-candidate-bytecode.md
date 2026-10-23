# 既有候选 Python 入口：缓存隔离证据

2026-10-21 09:23 +08:00，北京时间。主线初始 HEAD `38473401fdc124c00ed9ba117f79b4affb0c68ca`，本片待 root 提交。仅加强两个旧入口的 argv：

- `tools/b1_restore_replay.py::run_candidate` 保留候选 Python、-I/-B、验证/ledger/env/回执/错误边界，补 `-X pycache_prefix=<os.path.abspath(os.devnull)>`。
- `tools/core_incremental_pg.py::PostgresPort.candidate` 保留固定词法解释器与原 body/env/payload，补 -I/-B/-X null-prefix；其迁移/回填/withdrawals 调用方不改。

当前仍 No-Go；本片未执行 Linux、PG、stage/生产、真实模型或飞书，固定 b9 源码不变。

## 实际验证

清空供应商/飞书/测试 DSN 与 inherited PYTHONPYCACHEPREFIX，关闭 LangSmith/LangChain/OTEL；使用团队唯一窄测试槽，未启动整库：

    ../zhiming-v4-p2/.venv-core/Scripts/python.exe -m pytest tests/v4/release/test_b1_existing_candidate_bytecode.py tests/test_b1_restore_replay_contracts.py tests/test_core_incremental_pg_port.py -q --junitxml=private/b1-restore-proof-20261021/existing-bytecode-1.xml -o cache_dir=private/b1-restore-proof-20261021/bytecode-cache

**26 passed、4 subtests passed / 0.73s，退出0，零 fail/error/skip**。新4项、原B7契约17项、原PG port5项；JUnit tests=30 包含4个子断言。原始 timestamp `2026-10-21T10:23:00.319109+09:00` 等同北京时间09:23:00，JUnit内部时间0.433s。

真实构造同字节长度的合成 poison/source Python 文件，先编译 poison 的 timestamp-valid pyc，再改回 source 并恢复原 mtime/size。旧 -I/-B 对照确实导入 poison；两个旧入口构造的受保护向量实际启动后导入 source，且 isolated=1、dont_write=True、pycache_prefix 为绝对空设备路径。原 source 与 cache 字节逐次保持不变，没有删除缓存来让测试通过，也没有 mock import 或仅自报标志。

边界说明：B7 测试对其 source verifier 做调用记录替身、worker body 做合成导入替身，实际 request/ledger 校验保留；坏 ledger 在 source/进程边界之前拒绝。PostgresPort 保留真实构造的固定 release/bin/python argv，注入 runner 仅将 Linux 词法可执行路径映射到现有 Windows Python，所有 flags/body/env 保留后真实启动，connector 一旦被调用即失败。这些是 argv/缓存隔离证据，**不是 b9 业务重放、PG 或原生 Linux 通过证据**。

root 明确批准唯一旧测试变更：`test_core_incremental_pg_port.py` 原 `args[1]=='-c'` 改为核完整 `[-I,-B,-X,null-prefix,-c]` 前缀。固定解释器/候选 source、清供应商凭据、payload、禁止 freeze 的所有其他原断言保留。生产 guard 没有因测试放宽。

Ruff `--select E,F,I,B,UP,SIM --line-length 120`、format120、AST尺寸、diff检查通过：四个代码/测试文件最大274行，最大函数59行。没有新增依赖或安装。

## 身份摘要

| 文件 | 字节数 | SHA256 |
|---|---:|---|
| `tools/b1_restore_replay.py` | 7533 | `c761336c67e6e20c7cd88ba226974b137f1d831abf9335c185cffa463b75c5cf` |
| `tools/core_incremental_pg.py` | 12287 | `56b6605a9659c46bb609e38848e9b0992a3a843699328a54512ba0ed438a39c5` |
| `tests/test_core_incremental_pg_port.py` | 7885 | `273db8c33a8bf5da02611d3a53dc7db3f0767e95bad4db485c1fe078217d4c58` |
| `tests/v4/release/test_b1_existing_candidate_bytecode.py` | 7772 | `6a80a7067f0aedcb96572ecabf4b31ae57c4f82310990d4460bd6f15583d9ce6` |
| `private/b1-restore-proof-20261021/existing-bytecode-1.xml` | 4790 | `2c1e0c27dc5d0d98b1cf49ab166bf29d5b6dba93d4e3664e35a59f7cd4c4fc1d` |

## 未验证 / 后续

正式 Linux/PG/systemd、全部 B1 演练、真实模型/飞书/服务器均未运行。旧 PostgresPort 首连隐式 libpq 路由仍由独立下一片硬化；本片不将 cache 修复描述成解决该问题。B6 文本/资产摘要另片更新。工具摘要变化后旧审批不可复用，root 提交后重新核当前 controller / proof 摘要。
