# P3：按指令板v14完成首发脚本门与评测代码交接

本计划遵循 `.agent/PLANS.md`；全部人工记录为北京时间，新增测试仅隔离PG/Scripted/Mock，无真实模型、服务器或飞书动作。

## Purpose / Big Picture

指令板v10含v9 R11–R13，已解除原十二项延后功能误作首发门的口径阻塞，并把首发模型指定为k3.1-pro/high。目标是让真正的脚本放行器落实同候选的48/7/69/X02等价/core30组合，保留原全81报告的失败与延后说明，不能靠旧结果或手填布尔值放行。模型配置保留k3/k3-256k和旧v3路径，首发显式选择新配置，实际wire和响应身份消费者必须匹配配置承诺。

## Context and Orientation

当前eval分支父97d8aa8，PR18的CI仍待实际结果；release-prep081b48f是另一路服务资产，不混称本候选。复用ModelRegistry/生产Agent装配、原P1b中央守卫、StreamingHTTP与两个既有协议适配器、正式candidate/source脚本gate与真实X02故障驱动。不得改原题gold、记忆/P5或暂停线。未获同候选门前，真实请求保持零；Linux恢复与runbook属于上线门，不作为评测门。

## Progress

- [x] (2026-10-24 13:05 +08:00) 原c74在13:00:00–13:02:36同源实际完成P3 48/48、日期7/7、全81 71通过（指定69全通过）、core30 30/30；总编排仍blocked，未通知门通过。根核四报告同源/clean/零外发，定位新assessor误要求保留延期失败的原81报告status必须complete，实际runner诚实标incomplete。仅修assessor接受core的最终passed/failed集合与指定69通过，保原incomplete/失败，其他三套仍需complete；新增必要正反行为1/1、0.72秒（private/safe-narrow-1ee2062f10474c37af03a5b7a0f44132），根核三原件。新候选再执行一次完整R11以解决此实际门失败，符合13:00–15启动窗，不改gold或原报告。
- [ ] 按v14脚本门真正通过后立即提醒用户降到中档、找Claude接手评测；再完成core30_handoff_for_claude.md及必要stage代码交接。本代理不再执行任何真实评测/stage，模块暂停。

- [x] (2026-10-24 12:01 +08:00) 完整读取v10，R11/R12/R13/R16采用；板标写12:30晚于实测读取钟，按实际读取时刻记录，不回填未来。
- [x] (2026-10-24 12:04 +08:00) 官方Kimi模型文档确认精确ID/high要求/关闭思考拒绝及错误ID静默降级风险；未调用模型。
- [ ] 首发独立模型配置与真实响应身份拒绝门完成必要离线验证。
- [ ] R11实际candidate gate及X02等价断言接线，保留全81报告及十二项延后标记。
- [ ] 记录R12/R13执行边界，更新续作任务，根审测试/证据后小提交推送。

## Surprises & Discoveries

13:05发现：runner把全81中延期特性失败也标为report.metadata.status=incomplete，即使81题都已执行。R11的69适用子集应有独立完成态，不能为了门过改原报告complete。新增raw_report_status保原事实；禁止任何用例仍为incomplete，非core三套仍complete，指定69缺一、停机原因、额外/缺题、错源或非零外发继续拒绝。原c74 blocked运行和首次2fb网络门失败都保留。

旧turn_policy对会员K3只记server_default/high，未发送显式high；K3.1默认max，不能沿用此证据。旧transport.done写的是请求self.model，不能拿它当返回模型的核验。新增响应消费门必须早于任何text/reasoning/tool暴露，错/缺ID不重试或fallback。

R12明确停止继续同run/累计预算投入，原Durable/clear/witness成果保留但不再开发。新方向为整题quota中断、窗口恢复后新run从题头重跑，废请求照计，旧expired不延长/重签且0POST。ordinary runner已天然新建/丢弃隔离schema，但题级缓存、计分/历史物理量及公开lifecycle门仍需后续收口，本片不擅称R12整链就绪。

## Decision Log

2026-10-24 13:05 +08:00：v14将真实评测/stage交大脑，本代理只补必需代码与交接。R16显式profile/身份消费者已在release-prep父47d完成，R2限定stage新库/关门对调已推b7ba6ed，未混作c74的脚本源码。现先修R11控制器实际失败并在新SHA重新运行；不创建第二份审阅器、不手填gate或拼旧结果。

按v10配置与开发要求实施；旧线上v3不操作。主/外部评分同k3.1-pro，effort明确high，不启用highspeed。保留原k3/k3-256k回退配置，不改变已完成历史报告。官方文档只证明协议要求，不证明当前账号可用、计量相同或接入验证通过；≤20次正式接入验证要等同候选脚本门及直接用户授权边界核对，不用探针偷发请求。

R11首发门为P3 48/48、日期7/7、原展开81中的69通过、X02新等价断言通过、核心30离线30/30，全部同一个候选。全81原失败保留；M08第二批P5，P01–P06后续P7，X01/X06第三批P6，X08第三批P4，L02/X02原多供应商口径首发不适用，X02另测连续错误时U41友好/无重复写/不吞已提交答案。

R13允许官方Docker Hub最多三次重试、间隔至少30分；不改代理/WSL/ACL/镜像源，三次失败仅记需要用户开代理再切下一项。不把读取新版或任务提示当stage/生产授权。

## Plan of Work / Interfaces

先完整读配置/适配器/放行器和调用方，再以最小独立配置及实际消费者校验实施；不为通过新配置改旧v3默认路径或给旧k3测试强加新响应字段。具体文件与新接口在验证后补本计划。R11与R16分别限定代理拥有文件，测试由根统一授槽，主线最多2个pytest。

## Validation and Acceptance

只运行必要新目标与直接受影响旧兼容目标。Mock真实HTTP wire应显式high/无off-none-disabled，U39工具后reasoning回传保留，错/缺响应model在内容前失败且0后续请求；旧配置和v3默认不切换。R11负例须拒错candidate/source、缺任一套/额外失败、错误延期表和无X02等价证据，不修改评分gold或据历史69/81直接放行。

## Idempotence and Recovery

纯配置/消费校验无DB迁移；当前禁止真实调用、模型切换部署、删除旧报告或旧配置。所有旧报告/失败保留；未知模型身份保守停。未实现的真实接入、完整同候选脚本与Linux门保持关闭。

## Artifacts and Notes

官方依据：[Kimi Code模型配置](https://www.kimi.com/code/docs/kimi-code/models.html)，实际读取2026-10-24，北京时间。这里只概述要求；未证明Anthropic特定effort字段，不能凭猜测发真实探针。后续只登记一次原始定向metadata/JUnit/log来源。

## Outcomes & Retrospective

当前只读审计与计划完成，尚无本片测试/实际接入结论。首发、实际Linux/部署/新授权未就绪，真实模型/服务器/飞书及其他外发为零。

## 修订记录

2026-10-24 13:05 +08:00：记录c74实际四组完成但门失败原因，R11 core原报告incomplete的最小判定修复及必要1/1证据；采用v14接手分工，准备新同源候选运行。

2026-10-24 12:04 +08:00：先建计划，按新版区分评测门/上线门，停止旧同run投入，保护v3和现有结果。

2026-10-24 12:13 +08:00：已执行指令板v11，单代理，停止额外改进与同run投入。新增R11独立执行/评估器，保留全81原gold/报告，另测四次真实Mock503耗尽后的原生友好答案与公开runtime重读零写。首链5纯门通过/1新观察器误用core_outbox表名失败；只修为真实delivery_outbox后仅原目标1/1通过（14.85秒），没有改业务或断言。原件分别private/safe-narrow-b82d6c6b1ccd4c669b57d86f4c9155e1及private/safe-narrow-5e8cd6a48d44447498fc510327034dd7；不是一次6/6。R11全套将从同一提交运行并仅写private/candidate-eval/该SHA/R11目录，未跑之前不称通过。评估产物不是新模型或真实接入批准，原真实门继续关闭，R16尚未实施。续作自动化已按v11更新，截止与通知策略不变。

2026-10-24 12:18 +08:00：2fb036d正式首跑12:14:07–12:14:53取得P3 47/48，在X04 TimeoutError停止；原件private/r11-run-6b42c828f6f34185b6585c227e8d668f与其metadata.output。根定位为本片HTTPTransport封锁连回环也拦，非原取消时限回归；只允许数字回环HTTP、外部仍硬拒。必要新回归节点首1/1、1.87秒（private/safe-narrow-ebaaada4eccf4c63a4df4fca08cd5902），真实quiet socket/PG取消<=2000ms；原失败不删除、其它绿色定向不复跑。下一完整R11冻结新提交，按00–15分窗口排13:00北京启动；结果仅以该次private原始产物为准，尚未通过。
