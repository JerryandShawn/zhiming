# 标准库行执行覆盖：固定分母与 Core 小试

记录时间：2026-10-21T00:52:33+08:00（北京时间）。状态：离线研究工具与极小采样完成；未做完整覆盖采样。

## 固定来源与分母

- 基线：`f23b942ce698a3f7ee0b98c918d43053fe773433`。
- 观测源提交：`6c140cd635e8769dac5481b91c0da2520cd78680`；实际采样 HEAD：`45006aae5b98adea781c704335eb4080ee775aba`，后者只增加证据文档。
- 范围：上述两提交间 `mingjing_core/` 与 `tests/v4/` 下全部新增/修改 Python 文件，按完整文件建立分母；不是所有自身代码。完整清单与每文件 Git blob、raw SHA256、归一 LF SHA256、可执行行号都在 manifest。
- 共 173 文件、18,006 行；未导入文件也按全部行计 0 命中。另固定所选目录全部已提交 Python 与 pytest.ini 的 229 个执行守卫。
- `scope_is_complete_for_own_code=false` 固定为 false。此工具及其新增测试当时尚未提交，不属于 6c 分母；其他未纳入范围、C/JS、其他线程与子进程均不冒领。
- 分母限定 CPython 3.11 的 compile(optimize=0) 与递归 code object 的 dis.findlinestarts 正行号，不含 line 0/None；不是 coverage.py 分母，更不是分支覆盖。

## API 和边界

三个工具在 `mingjing_core/adapters/charts/benchmarks/`：

1. `line_coverage_manifest.build_manifest(root, base_commit, commit, scopes)`：仅完整 40 位提交 SHA、既定前缀、真实本工作树或 private/tmp 下新合成仓库。Git ls-tree + cat-file --batch 读取真实 blob；逐条核响应 identity/type/精确字节/hash/分隔符与无余留。不会执行归档转换、export-subst、脚本或任意导入入口。
2. `check_worktree(root, manifest)`：从 Git 重建分母以拒绝重新签摘要后改路径/漏文件/重复行/假源码；运行前后复核执行守卫及真实 HEAD。允许只有文档变化的 HEAD 前进，任何所选已提交 Python/配置差异均拒绝；工作树内容按 LF 比较，raw SHA 另记，合法 CRLF 不被误拒。
3. `line_coverage_run.collect(manifest, node, traced=...)`：只允许指定 Core 解释器和 3 个确切纯 Core pytest node。拒绝任意路径、节点、脚本及已有 trace。采样过程中清凭据、禁追踪/网络/子进程、禁第三方 pytest 插件与 conftest；临时目录为本工作树 private/tmp 下新 UUID，绝不复用已有 basetemp。pytest 输出进入不保留文本的丢弃流；失败仅固定标签，不落异常/题文/出生资料。
4. `line_coverage_merge.merge_reports(manifest, reports, root=...)`：逐行核同提交/同 manifest/同路径与 LF 源 hash、完整行集合、非负整数计数；拒绝重复回执。输出总并集和 `per_runtime` 各自计数，Core 和 Charts 不混称。摘要仅绑定内容完整性，不是签名或独立证明运行确实发生。

CLI：`python -m mingjing_core.adapters.charts.benchmarks.line_coverage_run`，仅有 `--mode manifest|baseline|trace`、`--manifest`、白名单 `--node` 和 `--output`。输出只限本分支 evidence/P8 的新 JSON，已存在的路径以 exclusive create 拒绝覆盖。无 Charts collector，也没有任意 entrypoint 参数。

## 正式小试（2026-10-21）

选用确切节点：`tests/v4/test_p8_e2_night28_controls.py::test_matching_is_reproducible_and_independent_of_input_order`。顺序各 1 个 Core 进程，Charts 进程/真实模型/网络请求均 0；未跑完整 v4、旧 Core 或 Charts 原生套件。

- baseline：00:50:51.896046 → 00:50:52.427717；计时区域 0.197151 秒，退出 0。
- trace：00:50:53.092785 → 00:50:53.998794；计时区域 0.485667 秒，退出 0。
- 两计时区域合计 0.682818 秒；带 trace / baseline 约 2.46 倍。计时区域包含 pytest 与追踪开销，不是产品函数性能；前后 Git 核验/I/O 不算进该区域。

| 分表 | 文件 | 固定分母行 | 本节点执行行 |
| --- | ---: | ---: | ---: |
| runtime | 67 | 6,272 | 191 |
| research | 47 | 5,021 | 542 |
| tests | 59 | 6,713 | 41 |
| 所选范围总计 | 173 | 18,006 | 774 |

总计 774 / 18,006 ≈ **4.30%**。这只是极小节点的行执行观测，不能推出 90%、断言充分、解释质量或完整运行时覆盖。Core-only 真实合并回放已完成：`runtimes_collected=[core]`、`not_collected=[charts]`；per_runtime.core 与合并总表一致。测试中的合成 Charts 回执只用于验证算法，不是真实 Charts 采样。

正式文件（不覆盖先前小试）：

- `night28-line-coverage-manifest-6c140cd-raw-blob.json`，manifest SHA `b900855113bfded1a53ea986f2255805dd3b2930e0616d53afae0301d0271312`。
- `night28-line-baseline-core-6c140cd-raw-blob.json`，report SHA `72e2eb4084b956a9724f5d7a4eb66458dad526a07d88ae887d181f46899a7ba5`。
- `night28-line-trace-core-6c140cd-raw-blob.json`，report SHA `38e5c2e74e817cb45b0309871c31d130e80dd3da26057219a0ece9e9a25f32d7`。
- `night28-line-union-core-6c140cd-raw-blob.json`，union SHA `47bf40541d72d5cb8971098d9e60516aff0064a7ccc2fe6255ef1089161e1bd3`。

## 工具来源和验证

以下为本次正式采样前后复核一致的 LF SHA；它们是采样仪器来源，不属于固定 6c 的覆盖分母：

| 文件 | LF SHA256 | 行数 / 最大函数行数 |
| --- | --- | ---: |
| line_coverage_manifest.py | `86c3a2e38d2eebb6bc332ffab88ab4ddc93f8eef485b55fa29bf659d15098654` | 262 / 45 |
| line_coverage_run.py | `6f9deeac5af3cc22efb80c6d58fe366fb532b2ad0f1f4c12cc7460535a87b5ea` | 309 / 40 |
| line_coverage_merge.py | `08e1453afdc3c005ee2c05418eda796e52feee1f48f62d9bcc4ad7524223d7af` | 117 / 43 |
| tests/v4/test_p8_line_coverage.py | `0e90ebefafdfeff9c8ebc2992d0f62cd3dd71639cfd20ff7b4d938f69581019d` | 380 / 24 |

最终专属 pytest **38/38 通过（4.24 秒）**，Ruff 默认 88 格式和静态检查通过。覆盖：完整/冷文件分母、原始 Git blob 与 export-subst、LF/CRLF、前后源码/配置、文档 HEAD 与源码 HEAD 区别、篡改后重签摘要、负数/bool/非整数计数、路径/重复/缺失、同文件别名合计、按解释器计数、任意入口拒绝、独占证据创建与输出丢弃。不把每字段断言次数另算测试用例。

中间过程保留事实：初版 33/33 和其 3 份小试 JSON 保留；补强 raw blob 检查曾出现 2 失败、11 通过、25 夹具错误，原因是合成仓库 Git archive 按 autocrlf 改变字节。已改直接 cat-file，不通过删除守卫消除失败。实际本仓库受属性约束，新旧 manifest 的 LF、分母和 raw 元数据均一致（raw 差异 0），同一 manifest SHA；旧初版 JSON 不含仪器 SHA，不将它们伪称本次新采样。

## 后续扩大采样方案（本轮未执行）

U12 等源提交后，当前固定 6c collector 会因所选 Python 改变而诚实拒绝。这时可对旧回执继续作 Git 固定来源的历史合并验证，**不能在新 HEAD 自称已重跑 6c 或已覆盖当前全部代码**。

下一轮须明确新完整 40 位观测提交与分母基线，生成新 manifest 和新的文件名；工具不自动提升 commit、不修改旧报告。先审计新增/删除/排除文件、分母范围和来源 hash，再分别批准 Core 的确切节点及 Charts 的原生节点/独立采样器。Charts 不得假定继承 Core trace，不改 worker/CI/依赖来偷接追踪。分别观测开销、遵守进程预算和整点错峰后才扩大；仅在 hash 和完整行集合一致时合并，保留每运行时来源及缺口。若目标是“全部自身代码”，须先另立可审阅的完整范围清单，本轮固定 changed-file 范围不得冒充该目标。
