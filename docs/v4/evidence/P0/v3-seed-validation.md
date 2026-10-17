# P0：v3 Target 初态与执行链验证

2026-10-17（UTC+08:00）。本验证只使用合成资料、回环隔离 PostgreSQL 15 与现有 `FixtureModel` / `ProgrammableProvider`；仅替换模型输出，保留真实 `ConsultationService`、`MemoryService`、仓储和 LangGraph。没有调用真实模型、收集密钥或发送外部消息。

## 全语料准备与服务烟测

80 个 YAML 全部落齐后，schema 收集得到 **44 个适用 v3 的场景、36 个 v4 专属场景**。`tests/v4/test_v3_seed_corpus.py` 对 44 个场景逐个建立独立 PG schema、初始化 seed，再执行第一轮真实服务。

该测试检查初始化与执行能否完成、run 是否成功、模型尝试数是否与替身观察一致，并核对历史原话的角色、渠道、时间以及事实的原话来源引用。**不比较替身措辞是否达到场景产品预期，也不把它计作真实模型基线分数。**

主执行者运行组合命令：

```powershell
.venv-core\Scripts\python.exe -m pytest tests/v4/test_v3_target.py tests/v4/test_v3_seed_corpus.py -q
```

当时结果：**57 passed in 28.57s**，包含全部 44 个场景烟测；没有 `target_exception`、服务执行错误或 skip。随后独立审查增加以下 9 项回归，没有重复运行完整 44 项。

最新完整验证由主执行者运行 `.venv-core\Scripts\python.exe -m pytest tests/v4 -q`，结果为 **119 passed in 32.90s**，包含本文件描述的 44 个场景烟测和 9 项新增回归。

## 独立审查与修复确认

1. 原 seeder 为已有事实另造“请保存…”来源，改变历史时间与来源关系。现改为先导入历史，再用严格 `SourceRef` / `Fact` 契约初始化已有授权的合成初态；事实引用原始用户消息，事项引用 `entity.data.source_ids`。真实运行中的记忆动作继续使用未修改的业务服务。
2. libpq 环境变量可能覆盖连接路由。现将 hostaddr 和 port 明确固定到规范 DSN，拒绝继承的 `PGSERVICE`；server 检查与仓储使用相同连接参数。
3. 执行异常曾可能仅表现为断言 0 分而仍产出完整基线。现保留脱敏 `target_error_code`，报告可区分供应商或业务执行错误，基础设施错误不会伪装成完整能力评测。
4. 旧 v3 用 fact 保存默认 profile，v4 profile 为单独对象。统一 `entities` 计数视图现在仅排除 seeder 记录的默认 profile 初态 fact ID；raw `fact` 列表与真实服务上下文保留这些资料。显式 `seed.facts` 和真实服务新增事实不被过滤。
5. 旧业务仍有真实取时筛选 `valid_from` 的行为。初始 fixture 声明已经有效，因此初态 `valid_from=None`，原始时间留在 source.at；冻结到未来不会错误隐藏已知资料。P0 没有改动范围外旧业务取时。

## 新增回归结果

```powershell
.venv-core\Scripts\python.exe -m pytest tests/v4/test_eval_local_db.py -q
```

结果：**6 passed in 0.48s**。覆盖 `PGHOSTADDR` / `PGPORT` 不能改变既定回环目标、继承服务配置在打开连接前被拒绝，以及验证连接使用规范路由。路由拦截测试使用连接调用观察对象，没有向合成外部地址发起连接。

```powershell
.venv-core\Scripts\python.exe -m pytest tests/v4/test_v3_seed_corpus.py -k 'normalization or future' -q
```

结果：**3 passed, 44 deselected in 2.18s**，均使用真实隔离 PG：

- 默认 profile 初态在统一视图中计为 0 条普通事实，raw fact 仍大于 0。
- 显式 seed fact 仍可见；真实服务收到有效保存候选后，统一视图与 raw fact 都精确增加 1，并产生真实 `saved` 回执。
- 冻结到 2099-10-17 后，默认出生资料与性别仍在真实 `MemoryService.snapshot` 中有效。

上述两份新增测试文件的 `ruff check` 与 `ruff format --check --line-length 120` 均通过。

## 验证边界

本文件证明评测适配器能正确建立合成初态并进入真实 v3 执行链；不证明真实模型回答质量、v4 行为、预测准确性、浏览器视觉、渠道投递或生产部署。真实模型结果必须另行运行授权后的 live 评测并记录报告。
