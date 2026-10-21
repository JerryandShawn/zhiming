# P4 M3游标首片：canonical输入、GET别名与精确事件行

记录2026-10-21 10:45:43 +08:00（工具UTC 02:45:43换算北京时间），本机TZ=Asia/Tokyo。独立目录`C:/Users/Administrator/Documents/Codex/zhiming-v4-p3-wire-p4`；root统一提交/推送，PR保持Draft，不代表合并、部署或P4整体验收。

## 实际结果

最终单进程串行9个明确目标文件：**98 passed/18.99s，1条既有Starlette/anyio弃用warning，0failed/skip/xfail**。本片新60条（纯48、真实隔离PG5、实际socket HTTP+PG7）与原明确38条全部保留。原输出`private/p4-event-cursor-20261021/final-target.log`；先前59新目标/5.38s、97组合/19.54s是真实中间结果，97日志保留为`initial-97-target.log`，不是最终数字。

    python -m pytest tests/v4/streaming_integration/test_event_cursor.py tests/v4/streaming_integration/test_event_cursor_pg.py tests/v4/streaming_integration/test_event_cursor_http_pg.py tests/v4/agent/test_run_event_replay_pg.py tests/v4/agent/test_thread_routes_pg.py tests/v4/streaming_integration/test_event_hub.py tests/v4/streaming_integration/test_event_listener_pg.py tests/v4/streaming_integration/test_event_http_pg.py tests/v4/streaming_integration/test_event_http_lifecycle_pg.py -q --tb=short

使用Core已锁Python、显式本机PG15/55480与每测试随机schema，清供应商凭据/关闭追踪，全部HTTP客户端`trust_env=False`。真实模型请求0、飞书发送0；未访问stage/生产，未尝试Docker/WSL。Warning仅为旧TestClient导入的`anyio.abc.BlockingPortal`弃用，未屏蔽/改依赖或断言。

Ruff E,F,I,B,UP,SIM line-length=120检查7个生产/测试文件通过；5个新/已默认格式文件默认format检查通过，2个旧120列格式文件（thread_routes/run_event_read）按其原120列格式检查通过；diff check通过。7文件最大200行、最大函数44行、最大行117字符，均在项目上限内。

## 保护行为与观测

| 目标 | 实际观察 |
| --- | --- |
| 纯48条 | ASCII canonical `0\|[1-9][0-9]{0,18}`、≤2**63-1；拒空/前导零/符号/浮点/指数/空白/Unicode/控制字/越界/bool；三来源明确一致，显式0参与；任何来源重复即使同值也拒；trusted内部值严格int；真实Headers getlist保留重复，旧受信dict接口兼容。 |
| PG空起点与实际洞 | 没有事件时0合法、1不合法；真实M1写1/2/3后合成故障删除2，1/3合法、2即使小于max也拒；page(1)只返回3、不补造2。 |
| PG owner/run门 | bob与另一个alice run实际有seq2，仍不能补当前alice run缺的2；unknown与缺失foreign-number同固定中文错误。当前run真正有3时，即使别处也有3仍合法，数字不带跨scope签名。跨owner fetch原门保留。 |
| PG真实撤销 | 实际invalidate_derived清payload但保留行1–3，validate(1/3)合法；page只发送新seq4 SOURCE_REVOKED，原3行正文仍空，绝不重建。 |
| PG检查无写 | failed run未补terminal时检查不存在4，event原件/usage不变，不调ensure_terminal、不增event/operation。 |
| 旧bridge组件 | 受信dict header=1可用，legacy桥不消费新GET query after=2；只返回seq2/3/4，验证旧POST查询语义没有被扩大。 |
| 真实socket HTTP两候选模式 | 默认hint关闭、显式开启分别验证H/A/S单独或相等得到同seq2–4，显式0得到1–4；OpenAPI仍声明after和after_seq两个可选str query。 |
| HTTP规范/重复/冲突 | 两query别名的各种非规范值、重复query/header、显式0与非零冲突、空/负/非规范header全部在SSE响应header前422，固定中文无输入回显；订阅数0，原event不变。 |
| HTTP缺行与擦除 | 物理删除的2不能被bob同seq/max替代，响应与未知999完全相同；payload已空的1仍合法，后续只seq3/4。另真实来源撤销后after=1只seq4 SOURCE_REVOKED，旧片段不复活，订阅回0。 |
| 旧明确38条 | 原RunEventReader final/ask并发修复、损坏final拒绝、retry新seq，thread_routes真实提交/历史/无痕关闭/cancel保lease，以及M3原28条连接/提示/回放/撤销全部保留通过，没有删改旧断言。 |

H=Last-Event-ID，A=after，S=after_seq；所有明确提供者须相等，缺省不参与比较，三者全缺省从0开始。GET先保留raw字符串/getlist，避免FastAPI int coercion抹掉`01`等证据，再把已规范int交公共桥；公共桥再次核header+内部int。旧v4 POST仍只header+内部可信int，不突然读GET query别名。身份仍原core/auth/RunEventReader，每页继续原owner/人物/线程/撤销门。

## 兼容变化与来源

原API曾把after_seq=0当中性默认，即使header非零也接受；现在**显式**0遇其他非零来源会冲突，未提供仍保持默认0。`01/+1/Unicode/空白`以及重复参数不再被int/框架悄转或选最后一个。这是有意的输入兼容收紧，未发现旧断言要求这些模糊输入，全部旧断言未改。

模块线`origin/v4/mod-organize@ebfa22f8`的resume/codec规范与host新解析器一致；resume不在本树12源候选闭包，本片没有复制/改它，也不谎称直接调用。模块PgEventStore要求cursor完整正文；本树撤销保空正文元数据，不能用那个要求逼出正文恢复。因此host只核当前owner/run/seq实际行存在，不要求payload非空，不据max或其他run推断。

本片4个生产文件为新`adapters/event_cursor.py`、小改`adapters/thread_events.py`、`adapters/thread_routes.py`、`application/run_event_read.py`；三专属测试+ExecPlan/本证据，共9件。冻结raw-byte manifest在私有目录，root可独立重算。没有改web、M2timer/Runtime/Loop/stream、Hub/listener、原模块、前端、Schema、迁移或依赖。

## 未完成

物理删除事件后的持久游标墓碑/提交信封恢复视图仍未实现；当前不存在的非零行明确拒绝，不能静默改从0读取。将来清理与游标验证的并发事务需在墓碑片独立验，不由本次存在性查询证明。M2联合Runtime流/完整X08三次随机断线、旧DOM逐字兼容/可见回执、真实模型首字与全部P4验收均未由这98条覆盖；本片只记录已批准的最小游标门。
