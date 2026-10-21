# 00点固定快照回归

北京时间2026-10-21 00:00:07启动，耗时284.68s。固定源码为本机103431a1f282ade913d404a65c5dff59f6bf3953，对应远端064954eeb47f2ca3bf0dc7fa32bc93902f083e04，tree7b58b87a51826cc8dffe55b5cd3eb4d39dcdbfa0。使用git archive导出到全新独立目录，测试期间不修改该源码。

`python -m pytest tests/v4 -q`：1288 passed，0 failed，0 skipped，2 warnings。本机Windows PG15.19、显式loopback测试DSN、独立随机schema；凭据清空、追踪关闭、TZ=Asia/Tokyo。警告为既有Starlette别名弃用与JUnit属性模式提示；不是产品失败。

范围：截至该首M6 Runtime提交的所有v4测试。后续读取端、无痕 Runtime、M7调度与M8新目标不在本次固定快照中，须另有目标/后续回归证明。真实供应商/渠道/服务器请求均0。00:19核新头CI仍进行中，不把本机回归当作GitHub精确头已绿或部署完成。
