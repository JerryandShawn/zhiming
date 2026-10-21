# ec2a59d 公开证据只读核验

核对提交：`ec2a59d0fb00d24a1ef98210a8d08789cc02c80a`。在09:45三轮全量冻结期间只读核对，
没有修改产品、测试、fixture 或历史证据，也没有运行 pytest、coverage、性能工作负载或业务请求。
本轮只新增本文，显式 UTF-8 LF；没有 Git 提交、推送或外部访问。

## 工作字节与提交字节

通过只读 `git show <commit>:<path>` 读取提交 blob，与当前工作文件原始字节逐一比较。
以下6份新公开 JSON 加375项静态报告共 **7/7 字节完全相等**，均无 CR 字节；JSON 解析成功。
表中 SHA256 同时适用于工作文件和该提交 blob，不是 Git object ID。

| 文件（均在本目录） | SHA256 |
| --- | --- |
| [RPF01 普通模式探针](RPF01_assert_mode_normal_readonly_probe_20261021.json) | `df957bb90a03637cb53dc00abcce47f24e6a50207667326b8404c6f660c3b11b` |
| [RPF01 优化模式原反例](RPF01_assert_mode_optimized_readonly_probe_20261021.json) | `0ec931aef507b03360546d49d0c30173f2ce4fdda5fed0049c28081d5dda939c` |
| [RPF01 测量模式守卫](RPF01_measurement_mode_guard_20261021.json) | `3529068c953a83cabe8c29f1baff92d0c09fee0a1232537703738fa824545c22` |
| [RPF01 公共输入探针](RPF01_public_input_readonly_probe_20261021.json) | `aac1dd9cdb823422b1ed356f74664570ae9399e2a00c12b9aede7e250ed36187` |
| [Outbox 主体原失败](STREAM_OUTBOX_public_review_failure_20261021.json) | `25ec73577731c3ff91bcc363b0aebed73ff41e1b260834186a61a168c192a220` |
| [Outbox 主体修后验证](STREAM_OUTBOX_public_review_verification_20261021.json) | `d5f07884643997e3b72860fbad8f5234a8aa247d847ef06be0632a9c1ade512d` |
| [375项静态报告](MORNING_preflight_0943.json) | `4da373237da1a85c442fb357bcd7a0953e829a2ac33e3941de74b2bc30fe5d22` |

## 引用与源码谱系

- Outbox 修后记录的 first_failure_sha256 等于上述当前公开首失败字节 SHA256。
  首失败仍保存2失败/10通过，修后记录12项目标和1967兼容项；本轮没有重跑这些观察。
- 修后7份产品摘要和43项产品/套件快照均与当前文件一致，0差异。
  375项静态报告含375个来源摘要，当前逐项重算亦0差异；其 size_issues、non_additive 均为空。
  本核验只复核报告与字节，没有重新执行静态检查器，不能代替正在运行的三轮回归。
- RPF01 旧工具备份、普通/优化模式原探针及09:07历史性能报告都绑定
  `3ea3b1fa6b51899a04a056f2164efb92cc6fc659b67b83e1151ffc82a2348089`。
  私有备份字节 SHA256 与该值相等，未覆盖旧性能。
- 当前工具及新守卫记录都绑定
  `3878721ba37c645cd48924973c756931ac65232f4036351b77b81fcb71393e2d`。
  新 default/-O/-OO 三例测试文件摘要与记录的
  `654fa0b3282099019f0edc3a59954d3a99f13eaa7ff0d9737a4168feb0246f91` 一致。
  本轮只读代码，确认优化模式显式拒绝位于 Core 导入之前，没有重新导入或运行工具。

## 说明文档的口径

[core3 主体接线说明](../../integration/mod/STREAM_OUTBOX_core3_subject_20261021.md)
工作字节与提交 blob 相等，SHA256 为
`b3cc2beaa0f67cf569acc908876193b8b7788e6ecba5c0acdae94277683a0d44`。
它要求权威主体及两次 freshness，未将 hash 自洽当成 PG 查询证明，也未称已发送或已部署。

[RPF01 公共边界审查](RPF01_public_boundary_readonly_review_20261021.md)
工作字节与提交 blob 相等，SHA256 为
`a40c233b67d76408218ed74ff99d60f114d05de0c6d5cf3e6d244822f9d86731`。
它与守卫 JSON 都明确：新工具尚无新的完整链性能，09:07观察仍属于旧工具；没有把旧性能哈希当作新工具测量。

本轮未发现公开字节、首失败引用或新旧测量身份混用问题。核验范围只到本提交证据与读取时文件，
不报告全量新结果、整个PR覆盖率、CI、远端推送状态、真实来源授权或线上验收。
