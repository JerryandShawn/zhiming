# 02:00 固定提交回归与早间复核

记录于 2026-10-21 07:34:45 +08:00，北京时间；测试 TZ=Asia/Tokyo，检查不依赖本机时区。

固定本机 `2b25175884af6fc8d6756c9f8c7f20922fd73fc7` → 远端 `54308ab45ec0cb1a88cf35688fa36861f37f3a5b`，共同 tree `b85ae557d7e9a3e2a34d10a2d48342abdced1609`。两组从同一 git archive 执行，不含共享工作树当时未提交的并行/恢复工具代码。命令、开始/结束时间、报告字节hash见同名JSON；公开报告按仓库LF规范保存，另记原私有CRLF字节hash与长度；仅换行归一，原私有日志/导出副本保持不变。

| 固定范围 | 实测结果 | 北京开始–结束 |
| --- | --- | --- |
| `python -m unittest discover -s tests -p 'test_core*.py'` | **581通过**，711.278s，exit0；已配置真实本机pg_dump/pg_restore，含恢复测试 | 02:00:33–02:12:28 |
| `python -m pytest tests/v4 -q --junitxml=<私有路径>` | **1768通过 / 1失败 / 1严格xfail / 0skip**，513.42s，exit1，6warnings | 02:00:23–02:08:59 |
| `tools/eval/runner.py --mode scripted --target v4` 原指定集 | **45/47**，78个合成ModelPort步骤，21.423s | 原集与扩展串行，总02:01:41–02:02:45 |
| 同源独立 `scenarios_v4_extensions` | **13/13**，27个合成步骤，5.651s | 同上 |

所有请求仅本机隔离PG/回环HTTP、ScriptedProvider；清供应商凭据并关闭追踪，服务器、真实模型、真实飞书均0。全量启动在用户规定00–15分钟窗口。

## 失败、警告和已知缺口

v4唯一失败为原 `test_eval_v4_pg.py::test_scripted_provider_drives_real_runtime[TA02]`。同源M8失败为 **TA02和X03**，不能把前一轮46/47或后续定向修复拼成这轮成绩。TA02旧manual牌缺完整来源区间而没有新c/r缓存，Loop错误强制缓存证明；07:29在当前工作树重验52项目标通过，修复单独提交 `3e732a6b` → `417ad6a8`，不改本轮旧报告或原场景。下一次新固定头完整回归尚未开始。

X03四条原发送断言仍把网页memory_write的queued Outbox与飞书投递/消息数混绑，待大脑裁定；不制造Outbox或修改评分。X04本轮真实本机静默HTTP取消15.9999999996ms，只是本轮测量，不覆盖旧32/47ms记录。

严格xfail为旧DOM仅读memory_receipts而core4真实回执在receipts，正文/历史往返通过不代表回执显示通过。主线保持前端独占和冻结信封，交前端兼容。6告警为1项既有Starlette/AnyIO弃用、5项JUnit xunit2与record_property冲突；没有关闭业务警告或以skip掩盖。

原集/扩展源码SHA均 `602b0acde2b4dcfc8964892c8c41a645e5762b9eb82204e67f04c8c235ee5182`，评分deterministic-eval-v1.0.0、原集契约 `aebc92157a4d3cebc7f2408757413e8e92e634006b6ad7e51ed828717cdb17f6`；扩展契约 `d0e932d174a38ea1406c7cbd903eda1384f08cdff236fb691e517450def48978`。后续e29f93c增加runtime.yaml指纹，不回签旧报告。

## 中断事实

约02:09起三个协作代理报告usage_limit，自动续作未产生新的主线提交；最后一条真实小时记录02:01:35。02点已启动任务独立结束，用户07:28左右发送continue后恢复。03–06小时记录及≤40分钟推送要求未达，明确列异常，不补造。该空档与28号记载的上一夜电脑停机是两次不同事件。

本轮不能宣布P3完成、完整绿色、真实模型质量或部署通过。
