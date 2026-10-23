# 评测执行身份包含真实循环配置

北京时间2026-10-21 02:07，本机离线。`tools/eval/runner.py:_source_digest`新增固定`config/runtime.yaml`原始字节与相对路径；没有泛扫config目录、私人.env或其他资料。配置添加、丢失或修改均使未来缓存恢复身份变化；配置缺失本身仍由Runtime的严格加载闸门拒绝。

    python -m pytest tests/v4/test_eval_runtime_fingerprint.py tests/v4/test_eval_framework.py::test_source_digest_invalidates_results_after_code_changes tests/v4/test_eval_resume_comparison.py -q

**34 passed /14.53s，0skip、0warning**。新3项覆盖稳定重算/真实上限改变、添加或丢失配置、其他配置和私人文件不纳哈希；旧source/resume/comparison断言保留。清凭据、关闭追踪、测试TZ=Asia/Tokyo；没有数据库、供应商或渠道调用。

02点不可变`2b25175`快照仍按原digest执行，报告不改写；本次修复只改变以后报告的执行身份。没有改场景内容、评分器、冻结v2.1文件/哈希或旧结果，也不把source digest当服务端tokenizer/模型等价证据。无迁移、新依赖或公共契约升级；回退这三行只会恢复原身份缺口，不能作为安全发布办法。
