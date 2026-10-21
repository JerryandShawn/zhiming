# U4资料日期边界补测回执

- 分支：v4/mod-organize；PR #10保持草稿，提交号由总日报记录。
- ExecPlan：docs/v4/execplans/MOD_profile_calendar_boundary_20261021.md。

## 完成了什么

- [x] 新增58项独立测试：农历腊月跨公历年、大小月/闰月过法候选、重复/歧义映射、缺原始纪念年、支持年界、端口异常和错误返回类型。
- [x] 资料构造的归属、确认、日期、布尔和版本类型，以及超大/错误lookup输出在日期产生前拒绝。
- [x] 明确候选不自动选日，端口错误不回显合成私密异常；P2与全部产品、原测试/黄金不改。

## 评测分数

新增目标首次58/58通过0.14秒。08:58实际目标目录1761/1761通过3.86秒，源快照无漂移；不是全项目回归。
四文件profile*_v2.py：行318/333=95.4955%，分支120/132=90.9091%，综合438/465=94.1935%。
原同范围280/333行、92/132分支、综合80.0000%；分母不变，未增加排除配置。
profile_calendar_v2单文件86/89行、40/44分支，综合94.7368%（原61.6541%）。

Ruff规则E/F/I/B/UP/SIM及120列格式通过。真实模型、网络、PG、通知和运行态写入均0。

## 改了哪些关键文件

仅新增tests/v4/timeparse_extended/test_profile_calendar_boundary_root_mod.py、独立计划与证据。
PROFILE_calendar_boundary_20261021-085848.json保留实际北京时间起止、命令、stdout和源hash。
PROFILE_calendar_coverage_20261021-085848.json保留每行/分支明细，SHA256：
813e04e90fc746239a74e0ee7b5f9a01a7c6b18403cb939bc1171976517177a9。

标准可复跑命令（另选全新data与输出路径）：

    python -m coverage run --branch --source=mingjing_core.timeparse --data-file=private/mod-week/<unique>.data -m pytest tests/v4/timeparse_extended -q --basetemp=private/mod-week/tmp/<unique>
    python -m coverage json --data-file=private/mod-week/<unique>.data --include=mingjing_core/timeparse/profile*_v2.py -o docs/v4/evidence/MOD_2026-10-21/<unique>.json

## 数据库迁移与回滚方式

无迁移或真实数据写入。新测试可以停用，现有运行行为不变。

## 偏离设计的地方

无。注入日历表全部明确为合成协议样例，不伪装中国农历的独立实值真值；不为数字调用私有分支。

## 未验证 / 已知风险

仍有15行/12分支未执行，原始raw完整保留。默认protocol省略行的排除沿用coverage默认，未改配置。
不证明P2全历法准确、真实资料授权、生日自然语言完整性、PG保存或提醒投递；更早盲评/模型与全PR覆盖未重判。

## 需要用户或大脑决定的问题

无新增本地阻塞。闰月/大小月/闰日过法仍须明确选择，不擅自决定，继续其他储备。

## 建议后续

主线接资料来源时同时接撤销/版本账本；候选日期不能自动产生记忆写入或循环提醒授权。
