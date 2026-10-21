# B1：为离线测试提供可核验的固定历史候选

本 ExecPlan 遵循 `.agent/PLANS.md`，2026-10-21 09:29 +08:00 创建。复用 `tests/test_b1_restore_replay_support.py::materialize`、`b1_restore_proof_support.py::pinned_candidate` 和 `verify_candidate`；固定 b9 的完整文件清单与 manifest 校验不放宽。只修改本线工作分支的 CI checkout 配置和本计划，不改 B1 包、锁文件、测试断言、PG allowlist 或任何服务器。

## Purpose / Big Picture

B1 纯契约测试实际导入受核验的历史候选。默认浅 checkout 只有当前提交，无法读取 b9 的 636 个原始 blob；这应作为环境缺失报错，不能退回当前开发代码或跳过契约。本片让既有 CI checkout 带完整 Git 历史。归档导出场景则显式提供已核验的 `B1_PROOF_TEST_CANDIDATE_SOURCE`，由独立可移植性切片验证，不在测试中自动联网。

## Progress

- [x] (2026-10-21 09:29 +08:00) 完整阅读 CI、旧 materialize 和新 pinned_candidate 调用链，确认浅历史与无 Git 归档是两个不同前提。
- [x] (2026-10-21 09:29 +08:00) checkout 仅增加 fetch-depth=0，执行步骤、依赖、服务、凭据与模型禁令不变。
- [x] (2026-10-21 09:30 +08:00) YAML解析后去掉新增checkout.with，整份结构与HEAD相等；从实际Git逐blob重建636项manifest，原字节摘要完全匹配；0PG/0网络。
- [ ] 精确新头 hosted CI 待完成，不能从本次静态门推断成功。

## Surprises & Discoveries

Windows 本机有旧 b9 对象且缓存已物化，可能掩盖 CI 默认浅历史的问题。反过来，完整 Git 历史不能解决没有 `.git` 的 immutable archive；该场景必须传明确绝对候选目录，逐文件重新验证，不能靠环境存在就签通过。真实 PG 19 项测试另需显式 PG15 admin/tool 配置；本配置不把它们的 opt-in 跳过冒充完整 B1 验收。

## Decision Log

2026-10-21 09:29 +08:00 / root：保留现有历史候选物化方式，只修其 CI 读取前提，不复制历史源码进当前仓库，不更换候选，不引入运行时网络下载或新依赖。CI checkout 仍由既有 GitHub Action 完成，测试进程自身不 fetch。07 场景集 R02/F01 的撤销/恢复不变量不改；本片不改变评测分数。

## Context and Orientation

工作树 `C:/Users/Administrator/Documents/Codex/zhiming-v4`，分支 `v4/p3-agent-runtime`，初始本机 ca266a6908f6a50d41384b1cac896f1fc9509ecb。被保留的历史 b9 为 b9a89b6f84f7bebb640de080548010859aae630c，其 manifest 原字节 SHA256 为 49038f8c0dc6bb293ba688af91018cbe6339b319c388d290fd000a256e36b33c。不是当前 P3/P1b 包；0008 不进 B1。

## Plan of Work / Concrete Steps

检查 YAML 仅 checkout.fetch-depth 改变，四个生产测试阶段及 always 清理原样保留。本机静态读取确切 b9 Git 树并通过既有 verifier 重建，测试无 Git 的结果由独立 portable 证据记录。后续在10:00窗口从固定新头导出完整回归；不能提前启动宽测试或借本次静态检查宣称 CI 绿。

    python -m tools.b1_restore_proof --help
    git diff -- .github/workflows/ci.yml

以上 help 只检查入口导入，不连接 PG；服务器、真实模型与飞书均为零。

## Validation and Acceptance

观察 YAML 节点为 checkout@v4、with.fetch-depth 整数0，jobs/steps/run 文本及 permissions 未被其它改动覆盖；固定 b9 的完整清单仍可被现有 verifier 接受。本机已有缓存成功不等于 hosted 完整门通过。需要精确 CI 新头的实际结果，保留失败、排队和 opt-in 未执行范围。

## Idempotence and Recovery

没有数据库迁移或发布。普通提交回退可恢复浅 checkout；不能用强推或删候选缓存制造通过。显式 archive 候选仅允许原 manifest 完整验证后的私有目录，不创建正式 restore-proof。

## Artifacts and Notes / Interfaces and Dependencies

仅两份跟踪文件，不增加安装、依赖、外部服务或 API。原始检查记录留 private；公开摘要写本计划，真实 B1 Linux 环境仍阻塞，30 No-Go。

## Outcomes & Retrospective

checkout 前提修复及静态核验完成：去掉唯一新增with后整份YAML结构与HEAD相同；636项真实历史blob逐一核Git对象身份，再重建manifest与批准摘要匹配。没有PG或网络动作；本机已有缓存不参与这次重建。不代表完整 Linux 演练或精确新头 CI 已通过。当前服务器/模型/飞书访问0，不合并 v4/main/main。

## 修订记录

- 2026-10-21 09:29 +08:00 创建，区分浅 Git 历史、无 Git 归档和真实 PG opt-in 三类前提，保留所有产品门。
- 2026-10-21 09:30 +08:00 记录YAML精确结构对照及636历史blob原manifest重建，hosted CI待验。
