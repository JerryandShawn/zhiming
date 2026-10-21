# core3/core4 历史回复回填证据

时间：2026-10-21 01:27，北京时间。只修改`mingjing_core/memory/backfill.py`及新测试/文档；没有迁移，没有服务器、供应商真实请求或飞书发送，没有对真实历史执行回填。

## 行为

回填只读取成功run，通过共用`read_result`严格区分版本。core3按明确core3 schema/validated格式读取cited_fact_ids/cited_claim_ids；core4严格验信封后读取used_fact_ids/used_claim_ids，另外核持久run/operation/runtime身份。未知schema、无效final、混版字段、跨owner/subject、来源/声明撤销、采用版本不符均跳过，不能靠正文猜引用。

core3声明是native claim_id，对应本run/epoch的实际PG声明行；core4用真实声明entity ID和精确采用版本。core3 current_source_*临时事实只在已提交evidence与injected_ids一致、原运行实际采用的原话版本/区间逐字可核时保留原ID，不新建长期fact。普通事实须真实存在且授权、版本/原话匹配。实际事实原话和专业声明来源补入助手source_ids，作为撤销血缘，不捏造来源。

无痕message不会在元数据回填中被改成life线程，无痕run回复也不回填长期历史。已有助手行、撤销回执和Outbox不改写；保持原owner事务覆盖dry-run/apply/中断回滚。

## 实测

    python -m pytest tests/v4/agent/test_backfill_results_pg.py tests/v4/test_p2_threads_backfill.py tests/v4/test_p2_history_window.py::test_backfill_prefers_exact_feishu_request_source_and_rejects_cross_subject -q

最终 **38 passed，22.99s，无skip**；其中新PG28项，旧P2回填/精确来源10项。仅一条既有Starlette TestClient/AnyIO弃用警告，不加忽略配置。此前27/27、36/36（22.85s）、37/37（19.90s）为重叠的迭代验证，不能相加。最终版新增显式validation.schema冲突反例；旧core3缺该字段仍按原兼容，不拒绝原300轮夹具。

新core4正向不是手填信封：实际共享ChartsService（合成底层引擎）→真实Chart工具/PG产物与专业依据→可信c/r→Loop→AgentFinalizer提交终稿；仅删除该合成助手行模拟历史缺失，再由backfill重建。core3用真实PG历史提交夹具，包含native专业声明和实际current_source_context生成的临时原话事实，分别核原引用格式。

测试覆盖：core3/core4/临时事实；dry-run不写、重复apply元数据/回复零变化；错误schema/validation/run/runtime、跨owner/subject/缺采用版本/声明版本变化/布尔epoch/源修订/撤销；旧core3不能被新used_*覆盖，core4不接旧cited_*额外字段；实际私密Runtime完成的原话/助手/信封不转life，FTS与原行保持；sent与uncertain Outbox逐列保持，仍拒绝再次claim。旧300轮回复重建、中断回滚、删除/部分撤销的FTS与来源保护均保留原断言通过。

    ruff check mingjing_core/memory/backfill.py tests/v4/agent/backfill_support.py tests/v4/agent/test_backfill_results_pg.py --select E,F,I,B,UP,SIM --line-length 120
    ruff format --check mingjing_core/memory/backfill.py tests/v4/agent/backfill_support.py tests/v4/agent/test_backfill_results_pg.py --line-length 120

Ruff/format/diff通过；业务文件358行，所有新增/修改函数≤60行、行≤120。无新依赖。测试清凭据、关闭追踪，只用本机独立PG15 schema；外部HTTP/子进程入口由夹具拒绝，Chart底层为显式本机合成runner。

## 限制

目标通过不表示真实库已处理、完整P3/新精确头CI绿色或生产部署可执行。旧历史若缺少可证明的声明/原话/版本，选择skip并留计数，不能还原猜测的血缘。现有固定B1包b9不变，本片不进入其发布范围；任何真实数据回填仍需另次受审授权。
