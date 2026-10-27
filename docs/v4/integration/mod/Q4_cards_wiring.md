# Q4 接线指南：卡片、单次操作能力与同卡恢复

本模块线交付的是实际纯计算卡片 builder、内存 token 服务和注入传输的 CardKit 状态机。
没有接飞书、服务器、模型、SDK、现有网关或生产数据库。所有外部字段/方法均标明
**“待对照飞书官方文档核实”**；候选 JSON 通过单元测试不代表飞书已接受，不能直接启用。

## 1. 卡片入口与来源

`mingjing_core.adapters.channels.cards` 提供：

| 入口 | 输入要点 |
| --- | --- |
| `answer_card` | 已提交/授权初稿正文；streaming、status、依据摘要、实际回执、归区标签、受信应用 URL |
| `question_card` | question、why、`CardAction` 选项；selected_label 对应已选回执，移除按钮 |
| `memory_receipt_card` | `ReceiptLine`；只有 saved/updated 才可带撤销 token |
| `proposal_card` | 已授权摘要及三个独立操作 token |
| `followup_card` | 1–3 句、可选 2–3 个快捷回复、真实 category/sensitive 标志 |
| `brief_card` | owner 本地 date、程序历法/安排/象征性反思/结尾；`BriefSection` 分区 |
| `route_card` | `RouteLabel(space, topic, change_token, new_topic_token)` |

`CardAction`、`ReceiptLine`、`RouteLabel`、`BriefSection` 位于 `cards_contracts.py`，不会调用模型。
仅从受信 envelope、当前回执和授权投影构造；不得给卡片再做一次模型解释。
全卡（含折叠层）最多 4 个按钮、1 个 primary，callback 的 value 只有 `{"t": token}`。
需更多按钮时由主线选择操作，不绕开总上限。长回答/依据按候选折叠布局展示。

健康/财务主动消息传真实敏感标志，preview 使用中性固定句，不能用私人正文首句截断代替脱敏。
正文与卡片 JSON 属于私人运行数据，不进公共日志、追踪或 PR。当前 URL helper 只校验有效 HTTPS；
应用 host/applink 白名单、可信域、OAuth 和免登仍由主线实现，不能信任模型给的 URL。

## 2. Action token：从已认证回调到原子业务命令

`ActionTokenService(MemoryActionTokenStore(capacity=...), clock=...)` 的实际入口：

```python
issued = service.issue(owner_id=owner, subject_id=subject, open_id=verified_open_id,
                       kind=kind, entity_id=entity_id, payload_fingerprint=current_fingerprint)
consumed = service.consume(raw_token, owner_id=owner, subject_id=subject, open_id=verified_open_id,
                           kind=kind, entity_id=entity_id, payload_fingerprint=current_fingerprint)
```

原始 token 只发到按钮，不保存到 metadata；store 保存哈希、身份绑定、种类/实体、指纹、期限、used_at。
默认 TTL=15 分钟、最大=24 小时是可配置**离线候选**，没有替用户作产品决定或宣称官方 TTL。

主线接入顺序：

1. 先校验 SDK/回调真实性，再从**当前已绑定**的 open_id 解析 owner/subject；拒绝陌生人、过期绑定和群聊。
   不从按钮、模型或前端接收 owner。回调外部字段与验签/长连接映射仍待官方核实。
2. 用 token 哈希查受信记录得到 kind/entity；服务器白名单选择 handler。加载当前有权限的实体，
   核对撤销/删除/expected_revision 并重算当前 payload 指纹；不能把按钮附带值或旧记录指纹当成当前状态。
3. 在同一个 PG owner 事务内锁 token 行，校验绑定、`created_at <= now < expires_at`、指纹与使用状态，
   并以 `consumed.operation_id` 唯一键写入业务结果或持久命令/Outbox，再提交 used_at。
   涉及外部效果时只在事务内创建唯一命令，外调必须在事务外。
4. `TokenConsumption.should_execute` 首次为 True；重放返回同 operation_id、replayed=True、should_execute=False。
   重放仅查询原收据或让已入队命令继续，不再次执行业务、不重新发 token 来绕过未知结果。

内存服务证明的是同实例原子消费与稳定业务 ID，不提供 PG 事务、跨进程持久性或实体授权。
敏感提案/资料确认、记忆撤销、归区、新话题与提问写入均仍走原服务，保留来源/撤销账本。

## 3. CardKit：预留 → 外调 → 确认

实际入口：

```python
scope = CardScope(owner_id, subject_id, verified_open_id, stable_business_id)
client = CardKitClient(scope, transport=verified_adapter, clock=clock,
                       store=memory_or_future_durable_adapter, interval_ms=400)
client.start(answer_card("", streaming=True))
client.offer_text(current_full_text)
result = client.flush()
result = client.finish(current_authorized_final_card)
```

传输必须明确注入，实现 create/send/update/close 的候选协议；没有默认 HTTP、SDK 或凭据读取。
本地只检查 JSON 2.0 候选的最小 schema/body.elements，并强制初始 streaming=true、最终 false；
不是官方 schema 校验。真正路径、字段、限频、权限、关闭/布局 API 拆分等必须在主线核实后才写真实适配器。

每个外调前预留 pending operation ID、payload 指纹、序号及时间；确认后推进 last_acked_sequence。
update/close 的序号严格增长，已预留后即使明确未执行也不倒退/复用。默认 400ms，允许 300–500ms；
节流窗口内保留最新完整文本，`deferred.next_due_ms` 告诉主线下一次驱动时间，不 sleep。
P4 text_delta 在主线累积成全文；text_reset 覆盖全文（可以为空）；最终 ask_user/回执由 builder 生成完整布局。

PG 接线必须让预留和最新 lease/fence 版本在**短事务内持久提交后**才出网；网络调用不持有事务。
确认回执时重新核对 owner/business、pending operation、目标、序号与 fence generation；旧 worker 不能覆盖新状态。
模块的本地 version/RLock 只是同实例 CAS，不是跨进程 fence。恢复前应停旧 worker 并取得主线持久租约。
同业务目标已固定；不能改 open_id 或换 business ID 绕过未知状态。

## 4. Unknown、恢复与降级

| 情形 | 实际离线行为 / 主线责任 |
| --- | --- |
| create 结果不明 | 保留 pending，无 card_id 时不猜、不再 create；先取得有证据的真实卡片 ID |
| send 结果不明 | 保留现有 card_id，不重发；对账确认 message_id 或明确未发送 |
| update/close 结果不明 | 不重发、不换卡；close unknown 也不自动发纯文本 |
| live in_flight | 禁止 reconcile，避免还在飞行的旧请求被提前释放 |
| 重启遇 pending | from_snapshot 把 in_flight 转 uncertain；仍需停止旧 worker、真实证据与 fence |
| close 明确拒绝 | 只返回 fallback_intent（固定业务 ID、卡/消息 ID、最终指纹），没有正文，也不发送 |

`client.snapshot()` 只有版本、scope/远端 ID、状态、指纹、序号、pending 与对账引用，不含正文、卡片布局或 preview。
这些标识仍属受保护 metadata。内存 snapshot 不提供自动落盘、认证或防回滚。

同卡恢复：`MemoryCardKitStore.from_snapshot(snapshot, scope=authenticated_scope)` → 新 client →
`recover(current_authorized_final_card)`。最终正文必须从当前仍有效的持久 run/outbox/助手 revision 重新投影，
重新检查撤销与依赖；不可从 checkpoint 猜正文或使用旧进程私有缓存。recover 不 create/send。
存在 unknown 时调用 `reconcile(operation_id=..., delivered=bool, evidence_ref=..., card_id=..., message_id=...)`，
证据由主线实际核实；未发送证明不同时夹带成功 ID。对账本身不调用传输。

fallback_intent 不是补发授权。主线需确认初始卡已送达、关闭明确失败且无未知 pending，
再以稳定 fallback operation ID 经 Outbox 发一次权威纯文本；有需要再独立更新原卡提示。
未知关闭或任何送达不明时先对账，不用新 run/业务 ID 绕过。

## 5. 需要主线接入的已有位置（本夜只列出，未修改）

- `adapters/feishu_gateway.py`：目前只注册文字入站；新增已认证卡片事件、图片/post 和后台任务移交，保持现有绑定/群聊过滤。
- `adapters/channels/feishu.py`：现有为真实 HTTP 纯文本 transport；不可当作 CardKit 默认值。新适配器须先核实官方 API。
- `adapters/channels/delivery.py`：现 worker 发送持久 final answer；卡片/流式需新的受信投递分派，保持未知不重发。
- `adapters/delivery.py`：现 `_fresh/prepare_delivery` 要求成功且 core3.0 验证的 run，不能拿它直接发送运行中的占位卡，
  更不能放宽旧报告的验证。主线另设计受 lease/依赖保护的 stream intent。
- 同文件 `reconcile_delivery` 当前整块替换 reconciliation；将来需事务性合并 `reconciliation.cardkit` 等命名空间，
  保留既有送达证明，避免抹掉 card_id/sequence/pending。
- Repository/迁移：主线按当前迁移序号登记持久 token 与 CardKit 状态/唯一业务键/fence；本模块没有抢占迁移编号。
- P3/P4 event consumer、finalizer 和 P7 投递策略：主线确定真实入口，接当前回执、ask_user、授权 final 与免打扰/脱敏规则；
  本模块没有创建假 Agent、SDK 回调或生产入口。

## 6. 离线性能 case

`tools/mod_overnight/benchmark_cards.py` 的 `cases()` 返回 `(name, callable, item_count)`，每次 job 都新建状态：

1. 1000 次真实七类 builder 轮转，并 JSON 序列化；不是 1000 条外部消息。
2. 1000 次真实 token issue + consume + replay，容量 2000；只返回首次执行/重放/哈希记录数。
3. 单卡 1000 次真实 client update，以 FrozenClock.advance 400ms 驱动，再 metadata 快照 → 新 store/client → 同卡 close；
   fake 只替代 wire。处理数为 1000 更新，另有一次 create/send/close，不是 1000 张卡。

root driver 负责五次计时和一次 tracemalloc。脚本不输出 token、正文、卡片 JSON、凭据或外部请求。
这是本机纯计算吞吐/分配证据，不能外推飞书网络延迟、真实限频、官方可用性或生产送达保证。
