# P3：运行配置进入评测恢复身份

本片遵循`.agent/PLANS.md`，于北京时间2026-10-21建立。root独占runner的source digest、新测试及本计划/证据，不改场景、评分器、冻结v2.1或02点不可变导出。

## Purpose / Big Picture

runtime.yaml现已真实控制循环预算，评测结果与resume必须绑定其字节。原source digest只纳Core代码/提示词、锁、eval代码与fixtures，没有纳runtime.yaml；以后仅改上限可能错误复用旧结果。02点本轮仍有精确Git tree和Config独立SHA，但不能以原source digest单独证明配置身份。

## Progress

- [x] 核实际source digest范围与新运行配置调用。
- [x] 仅将固定config/runtime.yaml存在时加入原哈希路径集合，不扫描配置目录或私人.env。
- [x] (2026-10-21 02:07 +08:00) 新三项、旧源码身份和resume/comparison目标34 passed/14.53s，0skip/warning；只读固定快照不改。
- [ ] 静态检查/提交推送；新固定快照按新digest运行，不覆盖历史报告。

## Plan of Work

保持原相对路径、分隔与原始字节的哈希规则；配置添加、丢失或任意字节改变都会改变结果身份。旧冻结报告/文件/评分不改，未来不匹配的resume继续原规则拒绝。该变更不批准真实调用或安装新依赖。

## Validation and Acceptance

新测试验证稳定重算、真实控制键改变、添加/丢失及不纳私人配置；旧source/resume/对比目标回归仍保持。只用tmp_path，不调用模型或数据库。

## Surprises & Discoveries

在固定2b25175的M8复跑中发现身份缺口；原报告保持原source SHA，另用固定tree明确当时执行内容，不重签旧证据。

## Decision Log

精确加入一个真实运行输入文件，避免泛扫config/private文件或增无实际语义的身份字段。没有新依赖和公共事件契约变更。

## Outcomes & Retrospective

34项目标通过；新增3项保护配置字节/添加/丢失和不泛扫私人文件，既有resume身份拒绝与源码变更失效行为保持。没有更改评分、原47/扩13的场景或冻结v2.1执行源，没有重签02点报告。真实模型/飞书/服务器均0。证据见evidence/P3/2026-10-21-eval-runtime-identity.md。
