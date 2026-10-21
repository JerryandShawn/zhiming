# Core组合回归：固定候选Native夹具误带0008

北京时间2026-10-21 09:15，独立wire基准5b691475c41791b4df2166db96dd3db54cc78d2b。原固定0900快照Core终态**581项/792.303秒、errors=3、exit1**，原日志和metadata保留，不被新窄组结果覆盖。

三条错误为`NativeAdapterTests`的`test_hermes_manifest_last_retarget_preserves_stub_original_and_load_order`、`test_native_quiesced_backup_and_hash_check_use_only_injected_ports`、`test_pinned_release_rejects_changed_source_and_extra_file`。三者均在`HostFiles.release`的`require(actual == MIGRATIONS, 'PACKAGE_MIGRATIONS')`失败，尚未进入各自原本要检验的安全行为。窄复现三个精确node，**3failed/0.91秒**；unittest原ERROR在pytest下呈failed，原因相同。

读取相关完整函数后核对：`tests/test_core_incremental_native.py:_release`用glob复制当前所有SQL到“固定b9”的合成目录；当前wire因P1b合法含0008_model_usage.sql。批准MIGRATIONS只有1–7，实际复制集合1–8，且**已批准1–7规范化checksum全部匹配**，唯一额外项8。这是测试输入构造漂移，产品严格包门正确拒绝，不应把产品MIGRATIONS扩成8或改固定b9。

root授权仅修夹具/补反例；先建立独立ExecPlan，再选择批准版本并验证完整键/精确checksum。新增负例把0008写进合成包且重算其manifest，使“文件登记”层通过后仍由PACKAGE_MIGRATIONS拒绝。原10条安全测试和全部原断言保留。当前尚未宣称新测试通过。

## 09:17 修复与窄验收

`tests/test_core_incremental_native.py`仅增加hashlib/MIGRATIONS导入，并从遍历当前所有SQL改为遍历批准七项；每项用单值解包要求唯一文件，并断言规范化checksum。原文件396→400行，无任何原断言删改、产品门变化或迁移修改。新`test_core_incremental_native_fixture.py`64行，用模块导入和组合构造原夹具，不在模块级导入原TestCase，避免重复发现旧10项。

两条新测试分别验证：正确七项可被HostFiles接受，然后篡改批准SQL并重算合成manifest依然以PACKAGE_MIGRATIONS拒绝；加入真实0008并登记/重算合成manifest也以同码拒绝。两条均额外要求主机命令记录为空、维护门尚不存在。它们证明迁移集合/内容门独立于文件登记/manifest摘要，不靠放松产品校验取绿。

    python -m pytest tests/test_core_incremental_native.py tests/test_core_incremental_native_fixture.py -q --tb=short

TZ=Asia/Tokyo，Core3.11，清供应商凭据/隐式PG环境、追踪与飞书关闭；仅一个pytest进程。结果 **12 passed、5 subtests passed /1.97秒**。其中原10条和全部原安全断言保留，新2条没有重复发现原TestCase。Ruff/格式、每文件≤400/函数≤60、diff检查通过。测试全程为假主机/假PG控制流；不代表Linux/stage/真实PG或系统切换通过。

冻结4件：原Native测试、新fixture反例测试、本证据、`docs/v4/execplans/P3_wire_core_native_fixture_20261021.md`。root统一提交/推送；其它P4计划、M8/0900报告不归本片。原固定5b691475下581项/errors3结果保持，下一固定源完整Core结果尚待10:00独立复验，不能把12项绿回签成旧全量绿。

本任务只用本机假主机/假PG注入的Native测试；未访问服务器、stage/生产、Docker/WSL、真实模型或飞书，没有任何发布。其它线v4/M8结果不能替代原Core错误。下一10:00固定新源Core宽回归由root独立安排，本片不重复581或回写历史通过。
