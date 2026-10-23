# 09:00 P1b/P3 固定接线完整回归

记录：2026-10-21T09:14:24.749706+08:00，北京时间。固定本机/远端同SHA `5b691475c41791b4df2166db96dd3db54cc78d2b`，tree `7c46d8239fba2ab28a3ba7ce3e7ba47ec624a275`，从git archive导出，逐一核1263个tracked文件原始blob完全相同、0差异。没有混入主树B1在途工具。测试TZ显式Asia/Tokyo；调度/本文为北京时间，JUnit原时区按显式偏移换算 `2026-10-21T09:00:02.673152+08:00`。

| 范围 | 实际固定结果 |
| --- | --- |
| v4完整 | 2732通过 / 0失败 / 0错误 / 1严格xfail / 0普通skip；console 780.9s；exit 0 |
| 旧Core | 581项；792.303s；exit 1；错误/失败节点见下 |
| M8原集 | 46/47，79合成步骤，框架20.677s，唯一X03四断言失败 |
| M8独立扩展 | 13/13，27合成步骤，框架5.412s，不能改变原47分母 |

v4实际开始 `2026-10-21T09:00:00.920615+08:00`，结束 `2026-10-21T09:13:03.945574+08:00`；Core `2026-10-21T09:00:17.047633+08:00` 至 `2026-10-21T09:13:32.947477+08:00`，都在00–15窗口开始。JUnit suite 780.871s与console时间各自保留。警告计数按同名JSON原console汇总，不过滤。

## 失败与预期失败

v4无failure/error。

- test_hermes_manifest_last_retarget_preserves_stub_original_and_load_order (test_core_incremental_native.NativeAdapterTests.test_hermes_manifest_last_retarget_preserves_stub_original_and_load_order)
- test_native_quiesced_backup_and_hash_check_use_only_injected_ports (test_core_incremental_native.NativeAdapterTests.test_native_quiesced_backup_and_hash_check_use_only_injected_ports)
- test_pinned_release_rejects_changed_source_and_extra_file (test_core_incremental_native.NativeAdapterTests.test_pinned_release_rejects_changed_source_and_extra_file)

旧DOM节点`test_legacy_dom_displays_actual_core4_memory_receipt`源装饰器严格strict=True且仅接受LegacyReceiptMissing；旧页读取memory_receipts而core4为receipts，仍算未完成，不能把xfail计作通过。X03原发送断言保留、无伪造Outbox或改评分。完整M8四份报告及墙钟详同目录0900-scripted-v4。

仅本机隔离PG/ScriptedProvider/MockTransport/回环HTTP，清供应商凭据、关追踪。真实模型/飞书/服务器访问0；Scripted步骤不是供应商调用或盲评质量。未合integration/v4/main/main，当前结果不构成P3验收或B1放行。后续修复另固定tree复验，旧08点失败不覆盖。

## 私有原始产物字节索引

仅摘录元数据，不复制原话、推理、DSN、凭据或完整异常栈；以下hash为未归一化原始字节，非公开LF报告的Git blob。

| 原始产物 | bytes | SHA256 |
| --- | ---: | --- |
| core.log | 11467 | `e00dfa2c042b8d4c3fd5f55619c69c65c35341aa2f157a78db32a9f2602afbaa` |
| core_metadata.json | 220 | `ffdd01deafeefd403ba85dd0a6031d7da41ce133e5a39c6475c01f1ab7d7df9d` |
| m8-scripted-metadata.json | 4011 | `c0610f66872fcfb2556358cee0633b3b3921950b10f3ac2b9db496db98d3849e` |
| metadata.json | 252 | `af7c3ae8c6daaad2edfe6713c1da3de0522510bcb81a1ba848deaaf6a484f37f` |
| scripted-extensions/2026-10-21-scripted-v4-scripted-v4.json | 33476 | `7e19baa0a7004d1250f161ec9f65dfa3b7696bdb348b189a9a4ae7c5dcac53d6` |
| scripted-extensions/2026-10-21-scripted-v4-scripted-v4.md | 4102 | `835b625d60b718add12ecc5e56984415385a707145d1951ca3ddcb28e459aa1c` |
| scripted-extensions.log | 752 | `a18bf87cb9aa1949640676d08fc291124978a50a652e7681ce9e35b036f44d93` |
| scripted-full/2026-10-21-scripted-v4-scripted-v4.json | 97504 | `050495f46c63971e25230190adcc24c67c1635da21f5285d808c643681d9b82c` |
| scripted-full/2026-10-21-scripted-v4-scripted-v4.md | 9071 | `d52ab363003430617bf6b146bb1a1ce7d3a9f5073d2b62db6d7f1afbb30261ef` |
| scripted-full.log | 1525 | `62629729d9b271c3111b2f364b43904dc762b53f0b5eb73882bb8b046ac540bb` |
| v4.log | 3700 | `2225f06802653c9036766ffe7f088144f40f957086d103816d8f7cda2aac7368` |
| v4.xml | 607739 | `3fa390b384249c52876c3be8c198ba47c66fd6352084792a55d7ed9499486c32` |
