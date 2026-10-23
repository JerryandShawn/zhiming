# 画像反思、确认与上下文接线（01:37 +08:00）

本线已有真实应用服务、PG 隐私传播和上下文记忆接入；专业档案/背景触发/认证通道仍待主线。没有新增迁移，profile_doc 和 proposal 已存在。

## 后台整理

`ProfileReflectionService(memory).prepare(owner, subject, fact_ids, incognito=False)`：最多 100 个当前授权事实，返回八节标题、事实/原话 ID、事实版本和保守分节线索。不能把模型提供的 owner、来源或授权标志传给它。当前第七节明确 unavailable，需主线提供有口径/稳定度/专业依据的真实档案读接口；用户事实不冒充命盘判断。

主线在后台运行自己的已持久化模型步骤，按 06 P3 的 reflection 提示生成工具输出，随后调用：

```python
service.consume_patch(owner, subject, ops, fact_versions=snapshot['fact_versions'], operation_id=stable_id)
```

ops 沿用 profile_doc_patch 的 add/update、item_id、section、text、source_ids；可选 confidence。source_ids 须精确来自 prepare 的事实范围，后台生成只能创建同一 P3 proposal（proposal_type=profile_doc），不能直接写画像或用户事实。`propose` 是以 fact_ids 为输入的内部等价入口。remove 尚未接入；用户删除 API 不能伪装成后台 remove。

不要在 PG mutation callback 内发模型请求。prepare 与 consume_patch 分开，后者会复核所有给定事实的版本/来源、有效期、授权、人物和事项，模型处理期间的变化导致拒绝提交。该接口目前未注册进 Agent 工具列表；本线不修改循环/模型层或后台 lane。

## 认证确认/忽略/撤销

`ProfileProposalService(memory).act(owner, subject, proposal_id, expected_revision=..., message_id=..., action='accept'|'dismiss'|'undo', operation_id=...)`。

真实认证操作形成 user/web-action 原话，命令分别为“请采用这条画像建议”“忽略这条画像建议”“撤销这次画像确认”。一条操作消息只绑定同一提案及操作；源修订、原话范围、时间、当前用户角色和 owner/subject 重新验证。请显示所绑定提案的实际内容和版本，不能让模型参数变成授权。

接受后画像仍是 inferred/derived，confirmed_by_user=true；保护 pinned/edited_by_user，后台只给建议，用户明确接受才替换。更新后再次用户编辑会阻止撤销覆盖。撤销恢复完整业务字段，审计修订递增，并失效画像派生引用；来源或事实忘记会清除画像/提案/快照，不能恢复已忘记资料。

内部批量建议回执含 ids；现有 loop_codec.candidates 只自动读取 receipt.id，尚不识别批量画像和 profile_doc 工具来源。主线需要为后台工具登记各 proposal 的真实 PG 依赖，并为确认的 profile_doc 回执补来源闭包和外部回执映射，不得仅放宽 kind 白名单。真实对话读取 profile 的来源闭包已通过现有上下文接口与原最终提交门验证。

## 上下文

context_entities 已读取已确认、来源与事实版本仍有效的 profile_doc；context_profiles 生成 p 别名和确认/推断标记进入 L2。画像未覆盖的事实继续保留，硬约束即便已被画像引用也保留原文；避免尚未整理完就丢限制。注入版本包含 profile、底层事实及确认/原话。过期、未来、越界、修订变动、撤销资料不能借画像进入上下文。当前 L2 改变稳定/前缀哈希；L5 epoch 的既有压缩语义不变，发送时仍执行原租约/修订守卫。

证据：`docs/v4/evidence/P5/20261024_profile_slice.md`。Scripted 的一条真实对话引用 p1 并成功最终提交，不代表全部指定产品场景完成或线上已接入。
