# 反思黄金样例跨换行兼容回执

- 分支：v4/mod-organize；PR #10草稿；新提交号单独记日报。
- ExecPlan：MOD_memory_reflection_background_20261021.md。

## 完成了什么

- [x] 比较Git存储与本机字节，发现黄金JSON只有CRLF/LF差异，却只允许CRLF哈希。
- [x] 以tracked HEAD的Git archive在本树private创建隔离LF副本，真实复现1失败/239通过。
- [x] 只允许原CRLF和Git LF两个精确哈希；不泛化归一化、不修改18组gold或原manifest。
- [x] 新增9项双EOL/内容篡改/额外空白/混合换行反例；同一LF副本加两文件补丁249通过。
- [ ] 最新远端Linux CI尚待确认，本地隔离副本仍是Windows运行时。

## 评测分数

原LF副本1 failed / 239 passed / 2.12s；补丁后249 passed / 1.03s。
本树目标249/249也通过，Ruff/format/类型/尺寸检查通过。
原CRLF SHA：c69f9956b75c891b2ca18e7a9df0cecf920f76db11b9a497ed4962f37c06464e。
Git LF SHA：4687a792b15d043f636a7a0f71f338ee5d4d74af17d04db158946a30b80ef918。
测试证明两版本JSON严格相同，任何未列出的字节变更仍拒绝。

## 改了哪些关键文件

仅新calendar_acceptance_support_mod.py helper及test_expected_eol_compat_mod.py。
REFLECTION_git_lf_before_failure.json / REFLECTION_git_lf_patch_success.json保存实际结果与补丁hash。
旧产品18源、旧真值、黄金文件和manifest均未改。

## 数据库迁移与回滚方式

无迁移、运行配置或真实数据修改。隔离复制在本工作目录private内，未下载、安装或删除资料。

## 偏离设计的地方

无逻辑真值变化。保留最初冻结CRLF字节，并明确增加Git LF字节表示的精确允许项。

## 未验证 / 已知风险

本地LF文件不等于Linux执行环境；最新CI仍queued，不能写成远端通过。
既有性能/覆盖的产品源码未变；本新增9项仅为测试格式兼容，不重新冒称模型质量或全部覆盖完成。

## 需要用户或大脑决定的问题

无本地阻塞，继续错峰全量回归与已授权储备。

## 建议后续

所有新冻结文本从生成时显式LF，记录原始hash与语义来源；保持实质变更拒绝，不以去掉hash解决跨平台问题。
