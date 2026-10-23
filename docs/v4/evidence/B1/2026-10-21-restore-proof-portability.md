# B1 恢复证明测试可移植性：本机归档验证

记录时间：2026-10-21 09:28（北京时间，UTC+08:00）。本片只改测试夹具与证据，不改五个生产生成器模块、consumer、CI、固定 b9 包或数据库迁移。

## 验证结果

- 最终归档联合目标：**88 passed /13.90秒**，退出0；B3纯契约48项、App纯契约40项，0失败/错误/跳过。这是本机Windows实际Python契约验证，包含真实子进程和污染pyc对照，未运行Linux。
- 独立真实Windows隔离PG15目标：**11 passed /66.11秒**，退出0，0失败/错误/跳过；显式使用既有PG15工具和本机55480管理入口，每例只创建并清理自身随机库/角色。未使用服务器、stage或生产数据。
- 严格Ruff（E,F,I,B,UP,SIM）、format及尺寸检查通过。真实模型请求、飞书发送、服务器访问均为0。
- 正式Linux恢复证明仍未生成，stage仍为**No-Go**。本片不证明Linux/容器/正式路径权限或GitHub CI已通过。

## 实际归档边界

基础归档为本机提交 `ca266a6908f6a50d41384b1cac896f1fc9509ecb`，tar SHA256 `220656850b010e5c04411c9f82cda4b5fc42b6d11a8061fbfffda4124a904ce0`，仅覆盖下列三个测试文件的工作区字节。归档展开在仓库外临时目录，`.git`不存在，实际Git探测退出128；测试子进程PATH为空，PG_BIN显式指向不存在目录，未传管理DSN。传入的唯一候选来源是外部已准备的固定b9目录，每次仍核原manifest与全部blob；不fetch、不安装、不凭参数跳过核验。

| 覆盖文件 | SHA256 |
| --- | --- |
| tests/v4/release/b1_restore_proof_support.py | `602d69ddea5a143bdfb5742d7068f6e2110823b85943d909703ea6ebc0bb6349` |
| tests/v4/release/test_b1_restore_proof_contracts.py | `2167a937c1f4257df2df7f8e99009e128a814615c4bfd8593c04349fde97cd51` |
| tests/v4/release/test_b1_linux_application_contracts.py | `c0fc45a66df8db6633d59d387b9b2b462edb0db83379bb2136e77a0b6025db0f` |

固定发布候选仍为 `b9a89b6f84f7bebb640de080548010859aae630c`（0001–0007）；0008不在本片恢复包里。

## 变更与旧断言保护

`B1_PROOF_TEST_CANDIDATE_SOURCE`支持无Git归档，要求绝对路径并始终逐blob核固定b9。未设置时保留本地已存在Git历史回退，不主动拉取；坏显式路径不会悄悄回退。App只将夹具直接materialize改成共用此helper，40项旧断言不变。

B3纯夹具使用临时regular文件及实际hash供默认零副作用校验，绝不执行该合成工具；真实PG夹具单独要求显式管理DSN，并在连接/创建数据库前核实际PG15 dump/restore工具。工具目录可由绝对 `B1_PROOF_TEST_PG_BIN`指定，操作系统决定后缀；不搜索PATH。新增4项反例保护坏pin、相对pin、错误工具版本及缺工具零执行。

纯夹具dump及passfile显式chmod0600，保留正式private regular门。Windows归档验证包含这两行，但未实际执行POSIX权限分支，仍需Linux固定头CI验证。

## 原始证据（私有路径，不提交正文）

| 原始产物 | 字节数 | SHA256 |
| --- | ---: | --- |
| private/b1-restore-proof-20261021/portable-no-git-combined.xml | 13787 | `8f8021295a053655e20bb253580d0e60285887c33d671b5560f40c18ec1cd671` |
| private/b1-restore-proof-20261021/portable-no-git-combined-observation.json | 1012 | `fb436fbbc6cb43e4492ba41edbc24512b0ff8ffbf4d2d874d988e4699d740dc7` |
| private/b1-restore-proof-20261021/portable-pg.xml | 2049 | `55bdcf24a630a91b0b6c6f9cb842db17529f4c599738d21b37df164e1df70cf3` |

JUnit原生本机时间保留为+09:00，不能修改原件；联合目标原始开始10:27:55+09:00对应北京时间09:27:55，真实PG开始10:22:41+09:00对应09:22:41。公开记录均使用北京时间。

历史复验保留：先单独B3归档48 passed /10.54秒，加入两处0600后48 passed /10.32秒；最终联合88包含上述48，不能重复累计。上一片生成器证据中的“此次53”可移植性段落实际对应最终55项里程碑，旧原件不重写，在此更正。第一片55项与本片88+11亦非同一次全库回归。

## 剩余边界

真实PG11项仍需显式opt-in，默认CI不会自动执行；默认浅克隆/无Git归档若没有显式已核候选仍会正确拒绝，固定b9历史/候选的CI准备由root后续接线。现存Windows默认工具路径仅为本机兼容回退；Linux须提供真实PG15工具目录。所有正式目标名、PG15/5432、Linux平台、受保护路径、双角色、最新撤销/收据与权限门均未放宽。
