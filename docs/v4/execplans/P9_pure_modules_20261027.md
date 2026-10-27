# P9纯模块及后续接口契约队列

## Purpose

按用户直接授权及mod板v14，先P9六类卡片JSON、回调验签/去重/幂等与假服务，再独立树v4/mod-api-contracts起草四组接口契约。中档，不开子代理；每项另树从指定e578e2d5d83dcf3b63c74af6e1b9f1a4c86453bd建立；本树zhiming-v4-mod-p9、v4/mod-p9，不改原树或stash，不改Agent/闸门/现有路由。

## Progress

- [x] (2026-10-27T16:22:45.119264+08:00) 读mod v14、05/P9；26号已读总览、卡片结构与回调段，余下章节按切片继续完整读。续作自动任务p9-11-2-22-00已创建，20分钟周期至11-02 22:00北京时间。
- [x] 选择性复用旧cards_official_v3与动作能力模块，逐依赖审阅后移植；不沿用旧cards的反斜杠转义和未修正协议。
- [x] 六类卡片：回答/提问/决策/记忆回执/塔罗/合盘确认，JSON隔离、按钮t、体积/元素约束与敏感预览。
- [x] 回调原始body验签/已认证长连接映射，app/chat/message/open_id绑定、动作一次性、事件去重/幂等、unknown不重发。
- [x] 假飞书服务、合成完整动作链及26号协议针对性测试；一页回执，P9模块就绪后进入接口契约。
- [ ] 接口草稿四组Schema/错误码/幂等/revision及Schema测试；两项完毕才暂停。

## Surprises & Discoveries

旧模块已有cards_official_v3，26号修正可以复用；旧cards.py仍候选协议且有旧依赖，不能整包照搬。官方公开页面本轮能打开但web工具未返回正文，不能称本轮逐字段重新核实；26号2026-10-20官方转录是当前合同依据。仅查公开文档，无飞书业务API请求。

## Decision Log

优先纯JSON builder和现有动作能力，不加载网络客户端。首发缺旧streaming JSON工具与P7预览函数，所需纯工具封装在channels内，避免带入其他未授权运行模块。记忆撤销服务按变更ID+修订号，卡片的opaque action token只是按钮能力，不新建memory undo_token。回调的PG/实际绑定/一次性持久事务由主线适配；内存测试不冒称PG授权。

## Outcomes & Retrospective

进行中，尚无本候选P9测试结果；不声明平台验证/上线/权限已开通。下一步先交可独立验证的卡片JSON与动作能力，再补六类与回调边界。

2026-10-27T16:24:36.674018+08:00 第一段133项定向通过（1.50s），六类JSON模板和已有动作能力生命周期可独立使用；回调验签、事件级幂等和假服务仍待做，暂不写P9模块就绪。仅复制cards_contracts、card_limits、cards_official_v3和token3文件；纯JSON/预览在channels内封装。旧ReceiptLine.undo_token改为action_token，明确只表示卡片按钮能力；撤销业务仍按变更ID+修订号，未修改memory层。相应测试仅改字段拼写，不删保护断言。

2026-10-27T16:45:46.588782+08:00 160项定向通过（1.57s），包括原始字节签名→AES-CBC解密→schema/token/app核对、已认证连接入口、当前chat/message/open_id绑定、事件与逻辑动作双幂等、两线程一次命令/副作用、撤销后worker拒绝、unknown不重发。加密布局与签名拼接已对照本地固定lark-oapi 1.7.3 decryptor.py/dispatcher_handler.py；未建立SDK连接。测试首次lint E731为lambda赋值，改def后lint通过，测试均未删改保护行为。26号已分段补读结构/流式/回调/权限/未说明事项与修正清单；平台实测项仍未验证。

Decision：v14明确任务为卡片纯模块+回调+假服务；不移植旧CardKit真实调用层或Agent监听器。26号两步finalize/close、序号/频控和权限/实体卡回调边界交给主线接线说明，当前不宣称完整05/P9产品阶段验收。
