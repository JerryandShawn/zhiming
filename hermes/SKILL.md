---
name: zhiming
description: 调用明镜 Core 处理传统命理解读、连续问事、塔罗与定期报告；Hermes 仅核验渠道来源及传递已校验结果。
---

# 知命明镜台：Hermes 薄渠道适配

## 唯一问事入口

所有命理、塔罗、现实决策、复盘、记忆更正和支持性交流都调用 `core_consultation.py`。Hermes 不另行解释、不自由改写、不把新核心结果交给第二个模型再总结。普通追问也由核心选择所需模式；不固定调用四套体系。

渠道身份必须来自管理员已配置的 PostgreSQL `PostgresRepository.resolve_channel()` 绑定。飞书默认 `external_id` 是真实 Hermes `sessions.user_id`；明确配置的私聊 `chat_id` 绑定另带 `--binding-kind chat`。不得凭昵称、档案名、第一条私聊或群聊认领用户，不得由技能新增绑定。缺少真实消息 ID 或绑定时如实说明，不能捏造原话、自行拼接聊天后传入。

对真实飞书当前用户消息运行：

```text
python3 {skill_dir}/core_consultation.py --channel feishu --external-id 实际已绑定用户ID --format json consult --message-id 当前真实用户消息ID
```

CLI 只读 Hermes 原始库，核验渠道、私聊、作者、active 状态与消息角色，只同步当前身份的用户原话；撤销来源跳过，当前消息已撤销时拒绝处理。传给核心的是已经同步的权威 `source_message_id`，不能把飞书文字另注册成网站消息绕过删除规则。

技术超时或回复丢失后使用原消息 ID 与原 `--request-id` 重试。默认业务编号由渠道与原消息 ID 得出。不得每次重试换编号、新建事实、重抽牌或重新生成已完成解释。已明确事项可加 `--case 事项ID`；含混且影响回答时核心会简短确认。深度可选 `--depth fast|standard|deep`，预算由核心统一计算，不额外启动辅助模型。

只使用成功 JSON 的 `answer` 原文，或将命令的 `--format json` 改成 `--format text` 取得同一正文。结果必须带 `schema_version=core3.0`、`validation.valid=true`、`validation.schema=core3.0` 和 `meta.core_run.run_id/dependencies`。报错或未配置状态不能伪装成已校验答案。“已记住/已更新”的描述必须来自真实写入回执，Hermes 自带人格笔记、摘要和 `archive.json` 不再独立保存用户事实。

## 确定性输出与专业边界

专业依据由核心引用计算字段与版本化知识规则；白话与现实判断在前，专业解释在后。Hermes 保持这一顺序与同一解读版本。传统解释不等于科学预测；相似主题不作为独立证据，不能补写概率、总分、疾病寿命、保证发财或第三人心意。

塔罗固定 draw 与可修订 reading 分开。模型错误、补充背景与重新解释不能改变牌、方向或牌位。塔罗问题无需强求生日；资料不齐的命盘请求由核心展示部分结果或必要澄清。普通担心不自动升级为危机，现实危险优先现实安全支持。

## 定期报告准备与投递

报告使用管理员已绑定的 `report` 任务身份，进入同一个 ConsultationService。示例只准备完整报告，不发出真实消息：

```text
python3 {skill_dir}/core_consultation.py --channel report --external-id 已绑定晨报任务ID --output /tmp/zhiming-core-daily.json report --kind daily --date YYYY-MM-DD
```

输出文件包含完整已校验正文、权威 run/reading、报告业务 ID 与日期；文件已经存在时命令拒绝覆盖。需要后续队列准备时调用：

```text
python3 {skill_dir}/core_consultation.py --channel report --external-id 已绑定晨报任务ID prepare-delivery --result-file /tmp/zhiming-core-daily.json --delivery-channel feishu --target 已绑定投递目标
```

prepare-delivery 从持久 run 读取结果，重新检查 owner、目标绑定和依赖版本；输入文件不能给队列灌入任意正文。此命令只建立 outbox，不调用飞书消息 API。独立渠道 worker 投递同一完整 payload，不能让 Hermes 收到摘要后另写报告。

时区保持 Asia/Shanghai：晨报 06:45 准备、07:00 投递；周日周报 19:45/20:00；每月 1 日月报 08:45/09:00；1/4/7/10 月 1 日季报 09:45/10:00。不得新增随机塔罗、提醒频率或真实测试发送，不修改现有生产 cron 配置。报告日期 2026-09-30 起的结构化门槛继续有效，旧报告保留 historical_unverified，旧文本不能补偿成新已验证报告。

投递前必须再核验依赖版本。外部网络结果不明属于 DELIVERY_UNCERTAIN，停止自动重发并对账；没有外部可靠去重不能宣称 exactly-once。明确拒绝也按有限重试处理，核对前不能另换业务 ID 发送一份。

## 退役路径与失败处理

`chat_agent.py`/`v6_agent.py` 旧总循环、`context_query.py` 的独立解释校验、`report_store.py --structured` 的自由模型 JSON、`archive.py merge` 的事实旁路均不再是本技能的生产路径。计算引擎、旧历史与迁移工具保留在受控适配或迁移流程，不承担总控。

权限错误不能让模型修复；来源撤销、数据陈旧、数据库故障、缺少知识与模型不可用分别如实呈现。不得静默回退旧 Agent、模板或 mock。当前部署切换及真实飞书联调状态以仓库验证记录为准；技能文件本身不是已联通或已上线证明。
