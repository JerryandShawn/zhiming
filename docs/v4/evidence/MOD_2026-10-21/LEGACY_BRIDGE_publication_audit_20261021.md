# 旧消息桥发布字节只读核验

核验时间：`2026-10-21T11:19:22.126712+08:00`（Asia/Shanghai）。指定发布提交：`9fe06056a591607027be78607972cdd5b310d2dd`。
本轮只读取本地文件、JSON 和该提交的 `git show <commit>:<path>` 原始字节；没有测试、coverage、性能、产品修改或 Git mutation。
只新增本审计文档。不查询当前 CI，不把指定提交核验外推为当前 HEAD、PG 授权、部署或真实用户操作验收。

## 已发布 JSON 与 Git blob

root 指定 6 份 JSON 以及额外的原 15 冻结矩阵共 7/7：工作区原始字节与指定提交 Git blob 逐字相同，
双方均 UTF-8、无 CR 字节、JSON 可解析。SHA256 对原始字节计算，没有经 PowerShell 文本转码或换行转换。

| 路径 | 字节数 | 工作区及 Git blob 共同 SHA256 | 字节 / 换行 |
| --- | ---: | --- | --- |
| [LEGACY_BRIDGE_independent_first_20261021.json](LEGACY_BRIDGE_independent_first_20261021.json) | 17925 | `6bb2395267b4462f8657fae8a49f0d59490ca18cf0baa6a09af75674f3661adc` | 相同 / LF |
| [LEGACY_BRIDGE_independent_postfix_20261021.json](LEGACY_BRIDGE_independent_postfix_20261021.json) | 19239 | `ec7ccd38ba153e6d0b0cd63b7bf0eb56406ac57634284fa6fca73c29e7844e7e` | 相同 / LF |
| [LEGACY_BRIDGE_compatibility_coverage_20261021.json](LEGACY_BRIDGE_compatibility_coverage_20261021.json) | 41346 | `49419da399476a6cc28ee9f12360014aa24d2754400744034a24880eb672abda` | 相同 / LF |
| [LEGACY_SCALAR_frozen_matrix_20261021.json](LEGACY_SCALAR_frozen_matrix_20261021.json) | 5219 | `7b164849815b572f2dcbc583b2718c523965df5546b4dc227f3811b4d6a7cff9` | 相同 / LF |
| [LEGACY_SCALAR_independent_first_20261021.json](LEGACY_SCALAR_independent_first_20261021.json) | 10577 | `cbd7aa1fc7f560a143dae5a44d70fff829b34124a2a3d5c7e606c102504fdc50` | 相同 / LF |
| [LEGACY_SCALAR_independent_postfix_20261021.json](LEGACY_SCALAR_independent_postfix_20261021.json) | 10690 | `82d14457481eb7959a0bbb96cc6fdd772d3c9a52dff9b9e1a4ef2dd852778968` | 相同 / LF |
| [LEGACY_BRIDGE_frozen_matrix_20261021.json](LEGACY_BRIDGE_frozen_matrix_20261021.json) | 15077 | `883b171aa7589aa1ee807d439c1779714ee91f588c9a2b0755b269b07b3491b2` | 相同 / LF |

## 修复来源、矩阵与测试未漂移

修后 `mingjing_core/organize/supplement_v2/legacy_bridge.py` 当前原始 SHA256：
`78ec7567a947388968d3d85d8565495aa904bdd8696ca63969ab30a74c3fc793`，与修后及兼容运行绑定一致。
原 bridge/scalar 首失败中的同源 SHA256 均仍为
`e6b5a98bf95241d29470d2236b899a05bfd86615b130c13445a5529e85451c9b`；历史没有改成通过或改绑修后来源。
原 bridge 15 例矩阵 raw SHA 为 `883b171aa7589aa1ee807d439c1779714ee91f588c9a2b0755b269b07b3491b2`，
scalar 5 例矩阵 raw SHA 为 `7b164849815b572f2dcbc583b2718c523965df5546b4dc227f3811b4d6a7cff9`，均保持。
两矩阵 cases canonical SHA 也分别仍为 `d2a66eac57234f68afc8c602394a8b359628addb8f4d7a938271840acdefa711`、
`2543357173da255a975c00fa7edc60a1f639e1ece6fa654a65dadd8485bdb9a2`。

三个新增 Python 的原始字节仍匹配兼容运行记录；两个既有测试也包含在下述 33 快照中且未变：

| 新增测试 / helper 路径 | 当前及兼容共同 SHA256 |
| --- | --- |
| `tests/v4/organize_supplement_v2/test_legacy_bridge_calendar_mod.py` | `cd3cdc7bb2bb1f726fe79e9e94c0d1d50477595299c2ce4dfa06f852e61a5c05` |
| `tests/v4/organize_supplement_v2/legacy_bridge_calendar_support_mod.py` | `92686c3d294ccf3d788df3136e058454539817fa3479c0a49ff25e09c2af2e24` |
| `tests/v4/organize_supplement_v2/test_legacy_scalar_acceptance_mod.py` | `dda0e8ee5aa798bb0e6e56860b3312d6deda242601f8e6bc5b88723de957246b` |

## 529 兼容快照复核

逐一读取 [兼容证据](LEGACY_BRIDGE_compatibility_coverage_20261021.json) 的 `after_sha256` 共 33 路径，
当前 33/33 仍一致，无漂移。范围为 21 个相关产品、两套全部 5 个 Python、2 synthetic fixture、2 冻结矩阵和 3 历史/修后证据。
活 ExecPlan 和 root 可能独立追加的 runner 不在该域快照；它们的文档或其他材料维护不冒充域源漂移。

这里只复核既有 529 passed 历史快照及字节绑定，没有新运行 529、原 15 或独立 5。
先前覆盖范围仍仅 supplement_v2 九产品；综合 705/803=87.7958%，不因发布核验变成整 PR 或新的覆盖成绩。
K3 的另一个提交和 root 的工具材料/静态检查不属于本轮域源，未读取其正文或声称复验。
本轮未读 Q5 B/私人 75、未访问外部，后续 Git 发布及 blob 核对仍由 root 管理。
