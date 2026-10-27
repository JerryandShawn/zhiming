# P5 首轮离线全量与相关补证

代码候选 `f407017`（包含 `f2d2653` 的记忆服务）。2026-10-23 北京时间 23:30:08 启动 v4，23:31:06 启动旧 Core，共两个测试进程；只运行一次全量。PG 为本机隔离 core_test_p2/15.19，每例独立 schema。供应商密钥移除、追踪关闭、Python 回环网络守卫启用，无模型下载或真实模型/飞书/外部服务器请求。

| 范围 | 首轮结果 | 用时 |
| --- | --- | --- |
| pytest tests/v4 | 3963 passed，18 failed，72 skipped，1 warning | 943.17s |
| unittest test_core*.py | 584 项，1 failure | 846.498s |

首轮失败没有算通过，72 个跳过项不能算已验证。P5 新增记忆测试不在失败清单中；整个项目的全量验收仍未通过。

## 相关补证

复用已安装的 `.venv-k3` 本地编码器依赖、Node22、前端线 jsdom、现存 PG 备份工具，只改测试子进程路径，没有下载、安装或修改共享运行环境。评测观察器此前在来源撤销后读取已清空的 runtime_step 抛 EvidenceError；现在显式读取删除状态并返回空 L4，不恢复私人内容、不改撤销/提交守卫。

仅重跑失败涉及的 live MockTransport、恢复、回环 DOM、生产启动测试文件及 PG 备份恢复检查：64 passed / 56.98s。名字含 live 的测试使用替身和本机隔离账本，没有调用真实模型。相关静态/格式检查通过。原始日志留在 ignored private/p5-offline-tests，不提交原文或配置。

## 未解决

`test_eval_v4_contracts.py::test_v4_cli_is_offline_only_and_default_fake_is_unchanged` 期待异常文案 Supported modes，当前实现返回 Live preflight failed。CLI 与该测试均未被本线修改，已写进主线配合项，不以放宽断言刷绿。

未重新跑整套测试，也不声称“全量已绿”。单值槽/冲突、过期归档、画像反思、认证按钮接线及全部指定 --target v4 scripted 场景仍待完成；没有“记忆2.0就绪”结论。
