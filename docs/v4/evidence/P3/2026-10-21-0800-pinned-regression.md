# 08:00 固定回归证据

记录：2026-10-21T08:16:55.859836+08:00，北京时间。固定本机`9a6f882d5454b86df4371e35f318b93502559a59` → 远端`428649b624d739b247f6a8f429f4a9f11775902d`，tree `d6a4f0d93ea5fe504d0995a0ebed063100cdc780`。本文据已完成会话及原始产物复核，公开元数据由root归档；没有重新运行测试。正文、推理、完整异常栈、DSN与凭据均不复制。

固定导出1146个受版本管理文件逐一与Git blob原字节相符，0差异。元数据记录测试TZ为Asia/Tokyo，日志记录用北京时间；JUnit原时间含显式+01:00偏移，按其偏移换算为北京时间2026-10-21T08:00:17.636276+08:00，不按本机时区猜测。

| 检查 | 08:00 固定结果 | 结论 |
| --- | --- | --- |
| v4完整回归 | 1934通过、1失败、1严格xfail、1warning；616.49秒 | 失败，不能称全绿 |
| Core旧回归 | 581通过；766.530秒；exit 0 | 仅固定本机候选通过 |
| M8原场景 | 46/47；79个Scripted步骤；21.210秒 | X03仍有4断言失败 |
| M8扩展 | 13/13；27个Scripted步骤；4.954秒 | 不能改变原47分母 |

v4从08:00:15.945671开始至08:10:34.479533结束，exit 1。Core从2026-10-21T08:00:36.168722+08:00开始至2026-10-21T08:13:26.141364+08:00结束，exit 0；结果基于已落盘的最终core_metadata及日志，不推断在途成功。 已完成套件的起始记录均在北京时间00–15分窗口。JUnit记录1936项=1934通过+1失败+1xfail，0普通skip、0error；suite计时616.474秒与日志616.49秒分别保留。

唯一真实失败为`tests.v4.agent.test_tool_interactions_pg::test_case_updates_and_events_preserve_originals_replay_and_revision`：case_update直接幂等回放在pending own-effect证明校验处触发EvidenceError。保留失败，不用后续WIP修复或窄测试覆盖此次固定结果。

严格xfail为`test_legacy_dom_displays_actual_core4_memory_receipt`，旧页面读取memory_receipts而非core4 receipts。JUnit确认为pytest.xfail；固定源装饰器核到strict=True且只接受LegacyReceiptMissing，不能算通过。唯一warning为Starlette TestClient调用弃用的anyio.abc.BlockingPortal别名，是DeprecationWarning；未隐藏或改写。

M8原X03仍失败：turn[1].db[2]、turn[2].db[2]、turn[2].db[3]、turn[2].events；TA02在08点原场景结果为通过。真实供应商请求、飞书发送及服务器访问均0，Scripted步骤不是供应商请求，也不是盲测质量证据。

02:00历史原封保留：固定2b251758→54308ab4/tree b85ae557，v4为1768通过、1失败、1严格xfail、6warnings/513.42秒；Core581通过/711.278秒；M8原45/47（TA02、X03），扩展13/13。两次套件项数不同，不能用通过数增加直接声称质量提升。

## 原始产物字节审计

以下为私有原始产物未做换行归一化的字节数与SHA256；仅公开元数据，不复制正文。02点原始产物审计同时保存在JSON历史段。

| 原始产物 | bytes | SHA256 |
| --- | ---: | --- |
| core.log | 6273 | `66c049633d5e495eec00038ade4abb4e40e06cbc4d7a7b5776851ae23a8f7260` |
| core_metadata.json | 220 | `be6fc3dd0b80c65cb0dfcc9d221c9a774dc35b36857500e533bef05f4daa395e` |
| m8-scripted-metadata.json | 4010 | `3da576df04bb382025ed2afa4a2bc3152b285c70cd20d08430a32de5343979f5` |
| metadata.json | 252 | `0ba386798cf99bef7f9ab48dda5eba8f09c6c487cbfbc5e83f14e195000f7771` |
| scripted-extensions/2026-10-21-scripted-v4-scripted-v4.json | 33546 | `53d2aa130b447128c2e517833808d46c15f9d55e9d70b0210c7c42e0a3b14ef6` |
| scripted-extensions/2026-10-21-scripted-v4-scripted-v4.md | 4102 | `b60c0db005627284a31ca0610ea4076857e54767c3a7a95b2e1f46f3f99244b4` |
| scripted-extensions.log | 740 | `2391d1290a901c91e2dec8268b3d99d06d057fb1613c4c08efeb1e46af519a4c` |
| scripted-full/2026-10-21-scripted-v4-scripted-v4.json | 97462 | `e1bcf29b257de685327f35e69b98a4b95e9505ad14950e808608e6df7fbc1e2b` |
| scripted-full/2026-10-21-scripted-v4-scripted-v4.md | 9071 | `889292c48276254b3d5e4501d826a6a09fa6facf8a1babc2477933d3aca0a3b9` |
| scripted-full.log | 1513 | `6dfd5fdf20d5a7c87dcbfa96ce4104daf9c35b121490663a061cf8ce4bb8aff8` |
| v4.log | 7389 | `e79703a8563907ff8bb8ee93489eb6b77d15b78f52176f612b5b4c760d83daeb` |
| v4.xml | 437207 | `62281fc5629fa8573b365c05e3da08153e9ec4683c62bf65324a278536e92ea8` |

当前仍有v4真实失败、原X03及旧DOM兼容缺口；本记录不是Linux CI、P3验收或上线凭证。02点历史、固定源码和原始失败不变；配套日报及ExecPlan另记后续进度。
