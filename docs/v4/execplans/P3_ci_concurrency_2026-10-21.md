# P3：只对主线分支合并同事件 CI 的旧运行

本 ExecPlan 遵循 `.agent/PLANS.md`，时间为北京时间 UTC+08。

## Purpose / Big Picture

减少主线频繁小提交积累的旧 CI，同时保留 push 与 PR 两份独立检查。按主代理随后扩充的准入，只包括 v4/p3-agent-runtime、v4/p3-wire-*、v4/p1b-*、v4/integration；其他线、main、v4/main、标签及外部 fork PR 不参与主线分组。新配置不会追溯取消原本没有 concurrency group 的旧运行，也不手动取消它们。

## Context and Orientation

08:08–08:10 通过既有 GitHub connector GET 完整分页核到35条 queued、20条 in_progress，其中23对/46条为同工作流、分支和 head 的 push/PR 双触发。主线当前只有 `.github/workflows/ci.yml`（Core v3 checks）与 `timezone-data.yml`（Timezone package data parity）；前者 push/pull_request，后者两种事件按六个时间包文件过滤并保留 workflow_dispatch。

当前真实 check 名为 core、Packaged tzdata on ubuntu-latest、Packaged tzdata on windows-latest；不能改 workflow/job/matrix 名。分支保护的 required 配置没有读权限证明：main endpoint 403，v4/main encoded slash 被 connector 路径校验拒绝400，因此不能宣称这些 check 已配置为 required，也不能宣称没有必需检查。PR9 API核到 P1b准确分支 v4/p1b-k3-hardening@8087d7fa64839dc5a080491fd5db4e358f5814ec，仍open/Draft。

## Progress

- [x] (2026-10-21 08:13) 完整读取两份工作流及 P1b精确分支、可见 check 名和权限限制；只读未修改/测试/取消。
- [x] (2026-10-21 08:17) 仅添加两份 workflow-level concurrency；按主代理最新指令将 wire 准入统一为 v4/p3-wire-*，原 on/name/jobs/steps 原样。
- [x] (2026-10-21 08:17) 现存 PyYAML BaseLoader 完整结构对照通过；两份各35个准入/非准入示例及各35个run_id隔离对照通过，事件与工作流隔离通过。
- [x] (2026-10-21 08:18) git diff --check 通过；更新证据与四活节，冻结四文件交主代理；无提交、推送、pytest或手动取消。

## Surprises & Discoveries

只限制 cancel-in-progress 不足以保护其他线：同组默认仍会替换既有 pending。因此非准入必须用独立 github.run_id，而不是共享分支键。event_name 保留后，同 head 的 push 与 PR 不互相取消，减少的是各事件内被新提交替代的主线旧运行，而非抹掉 PR 检查。

首轮本地静态求值脚本没有给多行逻辑表达式加外括号，发生Python SyntaxError，矩阵未执行；修正静态脚本的括号后原31例通过。随后因主代理扩充wire前缀，增加新wire分支与相似名字反例到35例，未因此放宽原非准入预期。两份YAML始终可由BaseLoader读取，不能把脚本求值错误误写为托管CI失败。

## Decision Log

2026-10-21 08:13：主代理明确授权只改两份主树 workflow 的 concurrency，所有 on/name/jobs/steps、必需检查名字不改。group 包含 workflow、event；仅本仓库所列主线 branch 使用 head_ref||ref_name，其余回退 run_id。cancel-in-progress 使用相同准入谓词。标签不按 branch 准入，fork 同名 head 不占主线组。

2026-10-21 08:17：主代理将wire前缀从v4/p3-wire-p6-*统一扩为v4/p3-wire-*，覆盖新接线草稿v4/p3-wire-p1b-20261021；不增加其他线或主干准入。静态矩阵按最终准入重跑35例，原P3研究分支仍不准入。

## Outcomes & Retrospective

两份配置均通过35个静态示例、35个run_id对照及事件/工作流隔离；去掉concurrency后与当前已提交HEAD的BaseLoader结构完全相等。diff只增加51行，原on/name/jobs/steps均未变化。尚未提交或推送，因此GitHub托管解析、新分组实际取消行为未验证；没有取消旧CI或运行本机pytest。08:08–08:10既有排队盘点只是当时快照，不构成故障诊断。

## Plan of Work

在两份工作流权限/job前插入相同 workflow-level block，使用 GitHub原生表达式；不新增 job、环境参数、依赖或辅助 CI 步骤。PR从 head_ref 归一，push/dispatch从 ref_name 归一；自有仓库条件隔离外部fork。用 BaseLoader 保留 on 为字面键，移除新 concurrency 后与已提交原结构逐字段相等。

## Concrete Steps

仅静态读取与解析，不启动工作流或测试套件：

    python -c "import yaml; yaml.load(open('.github/workflows/ci.yml',encoding='utf-8'),Loader=yaml.BaseLoader)"
    git diff --check
    git diff -- .github/workflows/ci.yml .github/workflows/timezone-data.yml

使用现有 Core Python/PyYAML，从两份实际 YAML 读出表达式并在受限本地环境按支持运算符逐例求值；这是静态示例核对，不是 GitHub托管执行器验收。

## Validation and Acceptance

准入集合只包括明确四类分支；main、v4/main、模块、前端、P8、研究、相似名字、标签及fork均独立 run_id/cancel=false。同一允许分支同事件不同run_id的组相等；push/PR组不同，两个workflow组不同。非允许分支不同run_id组必须不同。原工作流解析结构除 concurrency 外完全不变，包含触发、名称、权限、job、matrix和所有steps。

## Idempotence and Recovery

没有运行时数据、迁移或服务器操作。回退只需主代理在候选分支撤回新增两段 concurrency，原触发和检查保留。新块不追溯给旧运行加group，清旧队列需要单独授权及逐项保留验收头，当前不执行。

## Artifacts and Notes

证据：`docs/v4/evidence/P3/2026-10-21-ci-concurrency.md`。只持有这份计划、证据与两份workflow；其他文件由原代理持有。

## Interfaces and Dependencies

仅 GitHub工作流级 concurrency group/cancel-in-progress；复用已有PyYAML，不新增依赖/锁文件/公开检查名。GitHub分组和表达式按平台语义处理大小写，现有准入ref均为已核小写，不建立仅大小写不同的分支别名。

## 修订记录

- 2026-10-21 08:13 创建窄准入实现与静态验收计划；尚未执行静态矩阵。
- 2026-10-21 08:17 按最新授权扩wire前缀，两份各35例静态核对通过，原触发/检查结构相同。
- 2026-10-21 08:18 冻结两份workflow、计划和证据，无本机pytest、托管执行或旧run取消。
