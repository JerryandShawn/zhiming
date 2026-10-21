# P4 M3游标小片：规范输入与当前owner/run精确行

本ExecPlan遵循`.agent/PLANS.md`；创建时间2026-10-21 10:32:05 +08:00，最终验证记录2026-10-21 10:45:43 +08:00，均由工具UTC换算北京时间。目录`C:/Users/Administrator/Documents/Codex/zhiming-v4-p3-wire-p4`，只读设计基准HEAD `31c49673f0b70de5b595a96d545a9b5a5c5c9603`（M3有界消费者已提交）；root之后批准4个最小生产接点与3专属新测试。当前已在独占范围完成实施/窄验，root统一提交推送，不触碰并行M2 timer文件。

## Purpose / Big Picture

客户端可以用P4提示词要求的`after=<seq>`、既有`after_seq=<seq>`或`Last-Event-ID`续传。所有已给的值都必须是同一个规范非负bigint，不允许悄选其中一个冲突值；非零数字还必须是当前已认证owner/run的实际事件行。撤销已清空正文但保留元数据的行仍可作为合法续传位置，正文永不重建。物理删除后的游标墓碑另片处理，当前不假装支持。

## Progress

- [x] (2026-10-21 10:32:05 +08:00) 完整读RunEventReader、thread_events、thread_routes与web唯一旧v4调用；现有相关回放/HTTP/撤销测试及模块codec/resume/PgEventStore/接线说明。
- [x] (2026-10-21 10:32:05 +08:00) 给出旧断言保护、严格组合表、已擦正文行合法边界、最小文件/函数所有权建议；仅新增本计划。
- [x] (2026-10-21 10:40:57 +08:00) root已批准；纯解析器、GET别名最小桥与精确行门实施；3专属新测试，不改旧断言，不改web/M2/Schema。
- [x] (2026-10-21 10:45:43 +08:00) 最终明确9个目标文件98 passed/18.99s、1既有Starlette/anyio弃用warning、0skip/xfail；本片新60条（纯48/PG5/socket HTTP7）+原明确38条。日志`private/p4-event-cursor-20261021/final-target.log`。
- [ ] 精确物理清理墓碑仍未实现，后片受审；P4整体/旧DOM/真实模型首字未由本片验收。

## Context and Orientation

P4提示词`docs/v4/prompts/P4_真流式.md`的SSE v2明确要求`Last-Event-ID`及查询`after`。当前GET `/api/runs/{ident}/events`只声明`after_seq: int=0`；FastAPI会先把原字符串转成int，丢失前导零等文本信息。`thread_events.event_response`再用`int(header)`，接受空白/正号/Unicode数字等非规范表示，并把after_seq=0当成中性默认。`RunEventReader.validate_cursor`只核数值不超过当前max，允许物理空洞内不存在的非零数字。

`core_run_events`实际为PK(run_id,seq)、FK(owner,run_id)，没有墓碑表；来源撤销的`repositories/privacy_foundation.clear_runtime_outputs`把payload置`{}`，保留owner/run/seq等行。`page`跳过这些正文但按真实seq前进。数字只表示当前请求scope的序号，不带跨owner签名；同一个数字在多个run中存在时不能凭“数字来源”判外来，必须查当前owner/run是否真的有这一行。

模块线只读对象为`origin/v4/mod-organize@ebfa22f8f7c59e486c6632035ae6bc8307f0f438`，已读`docs/v4/integration/mod/Q3_sse_20261021.md`、`streaming/resume.py`、`pg_event_store.py`、`store_serialization.py`、`store_contracts.py`与相关resume/store测试。其parse_last_event_id使用`0|[1-9][0-9]{0,18}`、上限2**63-1；原候选codec也拒非canonical SSE id。本树隔离候选12源闭包没有resume/store，不能声称直接复用了未复制的模块。

模块PgEventStore.replay会对cursor行跑完整row_event，要求正文公共字段；这会拒本树合法擦正文元数据行。因此本片只沿相同规范语法新增host HTTP解析器，保留当前host PG reader的隐私语义，不复制/改写模块文件，不将擦除正文重新补齐。

## 旧断言保护与预期行为变化

| 原测试/调用方 | 必须保留的保护 |
| --- | --- |
| `test_run_event_replay_pg.py::test_error_replay_is_idempotent_per_attempt_and_retry_gets_new_sequence` | 错误同attempt幂等，retry得到更大seq；超过当前已存在位置的游标继续拒绝。 |
| 同文件`test_subscriber_and_runtime_emit_one_final_and_one_question`、`test_corrupt_existing_final_cannot_be_overwritten_or_replayed` | 订阅修复与runtime并发只一final/ask，损坏final不覆盖；解析器不写/修事件。 |
| `test_thread_routes_pg.py::test_thread_api_lifespan_dispatches_core4_and_replays_frozen_sse` | 真实Last-Event-ID只取剩余final、不重复，history与原lease/回执/私有推理规则不变。 |
| 同文件private close、cross-owner、cancel原目标 | 无痕关闭不能复活正文；跨owner禁止；HTTP取消不提前清活跃lease。 |
| `test_event_notify_pg.py::test_missing_or_privacy_cleared_original_is_never_reconstructed` | 缺失或擦除原件不能用稳定operation重新发布；合法擦除cursor也不授予重建权。 |
| M3 `test_event_http_pg.py`1005帧、header=999续传、越界游标 | 真实分页1000–1005保持，999确有行；9000继续422且不留订阅。 |
| M3所有Hub/listener/lifecycle目标 | 解析失败发生在订阅/响应header前，不加新缓存、不重启run，不把NOTIFY seq当cursor。 |
| 模块resume/store纯断言（只读，不修改） | 字符串规范/范围、scope归属、unknown/foreign同错误、真实seq可能有空洞但不能补造。 |

没有找到任何旧断言要求接受`01`、`+1`、重复参数或显式0覆盖其他非零值；收紧这些输入是明确兼容变化，不通过删测试掩盖。现GET隐含默认after_seq=0保持“没有给值”的语义；未来显式`after_seq=0`遇header=2要拒，不能再当成未提供。旧web v4 POST调用只传前4参数，未显式给0，因此默认改成None不会改变这条调用的默认起点。

## Decision Log

2026-10-21 / root：本片先只读设计，不直接实施。范围为after别名、规范组合、非零实际行，保留清正文行，不新增迁移/墓碑/清理，不松privacy。M2 timer独占Runtime/stream/helper新增行，本片不覆盖。

拟采用“所有明确提供者一致”，包括显式0；未提供才不参与比较。每个输入来源最多一次，即使重复值相同也拒绝，防止代理/框架不同取值规则。错误中文固定，不回显不规范输入、其他owner/run是否有行或当前max。

拟仅GET识别两个query别名，旧POST共用event_response仍只处理header及内部可信after_seq，不突然给旧chat POST增加新query语义。不在纯模块框架上再造PG store，也不把int强制转换当语法检验。

2026-10-21 / root实施批准：按以上四生产文件与三新目标实施；header为受信dict的旧组件接口兼容，但真实HTTP getlist严格保留重复证据。旧断言不删改，所有HTTP trust_env=False。执行范围没有扩大；先59新目标通过、97组合通过，随后补真实撤销后合法cursor的完整HTTP反例与空/负header，最终固定源重跑98。

## Interfaces and Dependencies / 已实施文件与函数

1. **新**`mingjing_core/adapters/event_cursor.py`：纯`parse_cursor_text(str)->int`；`resolve_event_cursor(last_event_ids, after=(), after_seq=(), trusted_after_seq=None)->int`。拒非str文本、非单次来源、语法/上限与冲突；内部可信值只允许type is int且0≤n<2**63，不接受bool。函数不I/O，不碰repo/Schema/模型。
2. **最小改**`adapters/thread_routes.py::event_routes/events`：GET声明`after: str|None=None`、`after_seq: str|None=None`保留OpenAPI兼容名称但不先转int；使用Request.raw的`query_params.getlist`/`headers.getlist`防重复，然后调用纯resolve，传已规范的int给event_response。身份仍先core/auth获取。
3. **最小改**`adapters/thread_events.py::event_response`：可选内部after_seq默认None，统一严格解析header+已解析的可信int；现GET会二次验证相同header/整型，成本常量且不丢raw冲突证据；旧POST没给可信值则只解析header，全部缺省为0。不改stream/Hub/Listener/SSE字段。
4. **最小改**`application/run_event_read.py::validate_cursor`：重新执行现authority；0是起点、不要求行；非零查询`owner=%s AND run_id=%s AND seq=%s`精确存在性，缺失一律原固定不可用错误。不得核payload非空或靠max/其他run补齐，不调ensure_terminal、不生成事件。
5. **新专属测试**`tests/v4/streaming_integration/test_event_cursor.py`、`test_event_cursor_pg.py`、`test_event_cursor_http_pg.py`；仅复用已提交M3 loopback helper/p2_repo，不改旧测试。新证据拟`docs/v4/evidence/P4/2026-10-21-event-cursor.md`与本计划。

`web.py`、Hub/listener/service、M2timer/Runtime/Loop/stream、原候选codec/resume、模块/前端文件均未改。依赖/迁移0。OpenAPI继续公开两个可选query名after/after_seq，类型为str以保留规范校验，实测验证；只有HTTP输入规范和精确行门收紧，冻结事件Schema未改变。

## 输入组合与结果

H表示Last-Event-ID，A表示after，S表示after_seq；“缺省”是该来源不存在，显式0不是缺省。

| H | A | S | 解析结果 |
| --- | --- | --- | --- |
| 缺省 | 缺省 | 缺省 | 0 |
| `0`或缺省 | `0`或缺省 | `0`或缺省 | 0（各来源最多一次） |
| `7` | 缺省 | 缺省 | 7，再核当前owner/run有行7 |
| 缺省 | `7` | 缺省 | 7，同上 |
| 缺省 | 缺省 | `7` | 7，同上 |
| `7`或缺省 | `7`或缺省 | `7`或缺省 | 7，至少一项提供 |
| `7` | `0`或`8` | 任意 | 冲突拒绝，不“优先header” |
| 缺省 | `7` | `8` | 冲突拒绝 |
| 任一来源重复 | 任意 | 任意 | 拒绝，即使重复值相同 |
| 任一`''/01/+1/-1/1.0/1e3/空白/Unicode数字/控制字/超过19位` | 任意 | 任意 | 规范语法拒绝 |
| 任一`9223372036854775808` | 任意 | 任意 | 范围拒绝 |

合法语法：ASCII `0|[1-9][0-9]{0,18}`且n≤9223372036854775807。URL百分号由HTTP正常解码后检查数字值，不把URI编码形式本身当游标权限。HTTP库禁止发送的控制字用纯测试覆盖，不能为测试去放松真实client门。

## Validation and Acceptance / 已执行目标

纯测试矩阵覆盖三来源单独/相同/不同/显式0、重复header/query、每种不规范表示、bool/float等内部非整型、bigint边界；固定异常不泄输入。不启动HTTP/PG/模型。

真实PG用M1真实leased writer写1/2/3，再在合成故障夹具物理移除2保留max3：validate(2)必须拒，validate(1/3)合法且page(1)只返回3，不伪造2。另实际bob/其他run存在seq2也不能补齐alice缺的2，unknown与foreign-number-unavailable使用相同固定错误。注意若alice自身seq2真实存在，即使别的run也有2，alice的2仍合法，不能声称数字自带来源签名。

撤销用真实invalidate_derived清payload，行1/2存在仍合法cursor、page只发新SOURCE_REVOKED错误，不发旧正文；0不依赖表内已有事件。正常cancel/retry/error/final修复旧门继续原样。非法游标不调用ensure_terminal、不新增event/operation、不开Hint订阅。

真实socket HTTP：分别A/S/H从同一真实位置续传得到逐字同seq；所有给定相等时等价；冲突/重复/非规范值在SSE header前422且订阅0；合法擦除位置能续传终态、无旧正文。默认hint关和可信开启两路径代表性复验，所有httpx显式trust_env=False，清凭据/追踪、TZ=Asia/Tokyo、只本机随机隔离PG。每次仅root授权1窄目标进程，不跑整个streaming/tests/v4。

已按root给的单窄位串行复验原`test_run_event_replay_pg.py`、`test_thread_routes_pg.py`和M3四文件，加本片三文件共98；没有跑目录宽测。最终输出1条warning来自旧TestClient导入的anyio.abc.BlockingPortal弃用；新纯/PG/HTTP行为没有靠warning屏蔽或xfail过关。M2源码同期由其作者提交，不借其结果当本片验证。

## Idempotence and Recovery

解析与validate_cursor纯读取，可重复；不分配seq、不补metadata、不修已清除内容。缺失非零行立即停请求，调用方可重新读取运行状态；不能自动从0恢复而导致重复披露。当前合法清正文行仍有真实scope身份。将来物理清理需要持久墓碑/提交信封恢复视图独立设计；本片明确拒无行游标，不给所有owner造一个通用“曾存在”许可。

权限或撤销在验证后变化，后续每page仍走现authority/隐私清理门；本片不把一次cursor验证当永久授权。物理删除与验证之间的并发清理尚无生产实现，未来必须和墓碑事务一起验，不能靠本片存在性查询声称解决。

## Outcomes & Retrospective

本片修复两类现缺口（int文本强制转换、max代替行存在），GET支持after兼容别名并严格核三来源一致。真实PG/HTTP证明物理洞不能借别的run补齐、真正擦正文行仍可作为合法cursor但旧正文不复活。最终98明确目标通过，未改旧断言；兼容收紧（显式0冲突、重复/非规范值拒绝）如实列出。详情`docs/v4/evidence/P4/2026-10-21-event-cursor.md`；不等于物理清理墓碑或P4整体完成，root接手9件冻结与提交。

## 修订记录

- 2026-10-21 10:32:05 +08:00：完成只读设计和旧断言核对，列严格组合、擦正文合法游标与最小所有权；未实施、未pytest。
- 2026-10-21 10:45:43 +08:00：按root批准实施4接点、3新测试，最终98通过/1既有warning；保留原59/97结果、不修改旧断言，冻结最小游标片，墓碑仍后片。
