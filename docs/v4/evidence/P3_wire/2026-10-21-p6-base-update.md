# P6 草稿更新 P3 基线与历史事项投影

记录时间：2026-10-21 08:07，北京时间。仅本机 Windows、隔离 PostgreSQL 15 与 ScriptedPort/loopback HTTP；服务器、真实模型请求和飞书发送均为零。

## 固定输入与合并边界

工作树 `zhiming-v4-p3-wire-p6`，分支 `v4/p3-wire-p6-20261021`。原本机头 `686521365b3b619db8bbf072799295f28d92d82c`（已发布映射 `bcc3a2e8`），经主线授权普通合入本机P3固定 `9a6f882d5454b86df4371e35f318b93502559a59`（远端 `428649b6`、tree `d6a4f0d93ea5fe504d0995a0ebed063100cdc780`）。

执行 `git merge --no-commit --no-ff`，未rebase、强推或提交。唯一冲突在 `AgentRuntime` 构造参数，同时保留 `p6_validation=None` 与 `runtime_config=None`，两套可信构造校验、RuntimeLimits和P6 draft/final桥完整保留；相对P3 Runtime仅17行新增/1行替换。没有未解冲突，合并提交由root统一办理，不向v4/main或main合并。

## 默认关闭与来源字节

P6默认仍为None，生产/HTTP/模型参数没有启用入口；可信构造显式注入同repo的 `P6ValidationBridge` 才启用。错误配置和不可信桥仍拒绝。

`validation/p6_candidate/SOURCE_MANIFEST.json` 固定来源 `ebfa22f8f7c59e486c6632035ae6bc8307f0f438`。合并前后均独立核对11个文件：SHA256 11/11、Git blob及来源提交路径映射11/11、源对象原字节11/11。未修改或格式化11份候选源码。

## 历史事项适配

旧P6投影只接受active/open/pending，不能接收P3现已合法支持的历史事项引用。新适配保留原P3证明：历史case引用走 `assert_case_status_citation`，其中索引分支走现有 `assert_historical_case_index`；open索引从当前owner/run/epoch/seq的真实completed case_list读取结果，交现有 `case_index_lineage` 重算当前投影，并逐项比较精确别名指纹。重复相同索引保留原序号证明，未选事项没有索引证明仍拒绝。

所有case只向P6投影id、title、status、revision、subject_id、entity_kind。现有P6结构检查只取别名集合；case回执只取id/entity_kind/title；旧lint只分组fact和interpretive_claim。因此该白名单保留现有规则使用的证据，未将未选goal、正文、state、source_refs或source_ids带入P6，也未改变P3对真实已选资料的上下文授权。真实选中case单次paused/closed状态写仍须原P3模型、mutation、版本与已完成回执证明。

## 可重复的窄验证

在本机隔离 `core_test_main` 库，测试逐例独立schema，清除进程中的供应商凭据并关闭追踪。下面三组串行，始终仅占一个测试进程；零skip、零warning。

    python -m pytest tests/v4/agent/test_p6_wire_pg.py tests/v4/agent/test_p6_annotation_compat.py tests/v4/agent/test_p6_case_projection_pg.py -q -x

结果：67 passed in 25.92s。保留旧22项；新45项包含真实Runtime的open/paused/closed/done/archived与单次/重复索引，默认关闭和双可信构造选项，精确步骤与伪造证明、撤销、跨owner/subject、旧epoch、无痕及非case状态例外拒绝，选中case单次状态写证明。真实运行不引入未选事项原话依赖，case投影严格为六字段。

    python -m pytest tests/v4/agent/test_runtime_config.py tests/v4/agent/test_runtime_limits_pg.py tests/v4/agent/test_historical_case_index_pg.py tests/v4/agent/test_historical_case_index_guards_pg.py tests/v4/agent/test_case_status_write_proofs_pg.py tests/v4/agent/test_agent_runtime_pg.py tests/v4/agent/test_present_options_runtime_pg.py tests/v4/agent/test_agent_runtime_recovery_pg.py -q -x

结果：168 passed in 68.22s。

    python -m pytest tests/v4/models/test_socket_cancellation.py tests/v4/agent/test_dispatcher_http.py tests/v4/agent/test_eval_v4_pg.py::test_x04_measures_quiet_loopback_http_and_persists_interrupted_partial -q -x

结果：17 passed in 4.10s。真实loopback HTTP、真实PG取消及X04原两秒上限全部保留；没有提高取消等待阈值。

Ruff check与format check（行长120）、双侧diff check通过。格式整理前后AST完全相同；既有Runtime未进行无关重排。新helper65行、最长函数30行，新测试246行、最长函数49行。

## 首轮失败与修正范围

第一轮56通过/11失败：10个新E2E原话缺少现有Z3进展触发词，case_list依法不可见；另1个新反例误写不存在的incognito列。只修正新合成原话和request.incognito字段，未改变可见性或业务断言。第二轮57通过/10失败：新监测误把本轮合法用户message也纳入case白名单断言；只让监测筛选entity_kind=case，保留所有正文、版本、原话闭包与权限断言。修正后最终67项全部通过。旧测试、11候选源与两秒契约未修改。

## 尚未验证

以上合计252项为当前合并候选的本机Windows窄验证，不是新精确头Linux CI，也不是完整v4回归或全部M8评测。P6旧远端头的两个Linux静默流取消失败，需要发布带socket shutdown候选的新精确头后重新核对，不能预告已修复。socket候选对响应header之前的全部平台取消窗口仍未给出新证明。P6 v2 critic、校准、专业claim重验证及farewell仍保持原未接入边界。无新依赖或数据库迁移。
