# 命理研习20课草稿：数据、题目与依据验证

归档观察时间：2026-10-21 00:15:37 +08:00。由工具UTC `2026-10-20 16:15:37` 转北京时间，未依赖宿主时区。
分支：`v4/p8-calc`；本增量未自行提交/推送，交由root统一发布。

## 已起草的范围

对应大脑33号第二节第5项。先读完整33号与公共规则、指令板meta v1、AGENTS、
`P8_night28_week_2026-10-20.md` 和既有P8计划；先将20课目录与纯数据输入/输出方案发root审阅，
获通过后才写正文。前18课由四柱、时间依据、十神与透藏进入具名条件、候选与限制，
末两课用真实合成阿远紫微和西占样例解释跨体系边界。

- `knowledge/p8_learning_lessons/curriculum_v1.json`：20项目录、3个case、6份原输入SHA、20条观察依据、来源版本及限制。
- `knowledge/p8_learning_lessons/lessons/lesson-01.json` 至 `lesson-20.json`：每课独立目标、两段原创白话、实际例子、2道小测验、流派差异、出处ID与具体待核，共40题。
- `docs/v4/contracts/learning_lessons.md` 与 `.schema.json`：供前端读取静态JSON的契约；未新增HTTP、工具或用户进度存储。
- `tests/v4/test_p8_learning_lessons.py`：Core专属数据/依据验证与异常边界。

全部课程状态为 `draft_for_review`。正文起草和本地检查通过，未声称20课已经专业人工逐课验收、
前端已经接入、模型会正确授课或学习者掌握了知识。没有把研习草稿变成当前用户排盘规则。

## 题目与引用的实际检查

40题由20道真实观察/规则输入题与20道具名概念题组成。三选项答案位置实际为a 11、b 14、c 15，
不是所有答案同一位置；正文段落、题干没有整段重复。每题都有独立解释。

实盘题从目录case找到固定原信封，再解析已有c和相对Pointer，比较实际值、expected及正确选项值。
20条依据包括真实false候选，不把false补成r。含r的三条分别为：

| 教学观察 | 实际c/r | 证明范围 |
| --- | --- | --- |
| 正印候选透干条件 | 八字c7/r8 | 单项条件满足，不能独自替整章成格 |
| 伤官候选显性牵制筛选 | 八字c12/r1 | 本条牵制检查通过，庚辛只作概念说明 |
| 真太阳交界输入 | 八字c26/r10 | 原始坐标为边界规则实际引用，前后敏感性样本不是出生事实 |

三个case分别保留owner/subject/revision/operation；同号c不得跨operation混用。
未计算的阴刃异表、庚辛其它盘和未实现可选技法都由source_id说明，不伪装阿远真实命中。
学习卡仅作为相关伴读链接，实际计算信封仍是观察依据。

## 测试命令与结果

在独立Core环境清理API Key/Token、关闭LangChain/LangSmith追踪后执行：

    <Core Python> -m pytest tests/v4/test_p8_learning_lessons.py -q
    <Core Python> -m ruff format tests/v4/test_p8_learning_lessons.py
    <Core Python> -m ruff check tests/v4/test_p8_learning_lessons.py
    <Core Python> -m ruff format --check tests/v4/test_p8_learning_lessons.py

修后结果为 **82 passed，0 skipped，0.27秒**；Ruff检查和默认88列格式通过，测试文件287行。
格式器只重排测试，没有改断言或数据；没有据格式重排扩大原测试覆盖声明。

82个pytest用例的构成为：目录1、三case及原学习卡重放3、来源注册1、单课契约/出处20、
逐题答案40、内容去重/答案位置1、诊断盘/缺Pointer2、跨case/错误值1、假r/错误输入关联2、
规范Pointer6、错误答案类型/概念假别名1、安全路径4。不要把一题多个字段断言或100个解析字段另算用例。

测试读取三份chart_compute及三份learning样例并做完整文件SHA校验，复跑纯规则 `learning_outline` 与原卡相等。
每个原信封自身的hash、scope、原生c/r绑定由已有学习输入验证继续检查；普通hash不证明来源签名或现实授权。

### 首轮失败与修复事实

首轮为78通过、4失败，两个问题各触发单课及该题检查：

1. 课程作者序列化将实际浮点 `63.0` 写成整数 `63`，严格期望检查拒绝。修正课程自身expected和选项为原值表示，未放宽布尔/数值边界。
2. root按最新API边界修复重算输入后，西占主盘短号由此前c6变成当前c1。课程误沿用旧短号，被主盘检查拒绝；改为当前真实c1，未改原样例、算法或测试。

这说明短号不能跨重算假定稳定。未来样例变化必须连同原引用重新核验，不能只更新SHA绕过观察值检查。

## 固定输入与本增量指纹

| 内容 | SHA-256 |
| --- | --- |
| 课程目录 | `0348759805ad6a83288888ebbd8dceea07d772b419ef74aab990baecf34c1ec3` |
| 课程Schema | `ee521572c0c6eb58ead1fb215f544c5f572095179b53213c52eddaaa9fa70b4b` |
| 默认88格式后测试 | `f1c909468dddaf0cdb1513c25bf2f1b07f040bd55f580bacb78d1603dc66bdb1` |
| chart：八字阿远 | `8f8e8dafb6ee9ad4cfd9fc6042b10def0f1ed660a7c91f6b440964c020bbb28a` |
| chart：紫微阿远 | `125de08efaa75586ded08ef0feb8f25dc9f8a7c09653af5d9658154cdcaa3bc2` |
| chart：西占阿远 | `fc8f39223f0a1532921c97666bfc4eb81550f732afac7b61d8fce7143c2cabf7` |
| learning：八字 | `5bb275406c2364f6e027d532c7d302bb4ecdfd8486bddd58f0a04f5b35d8c11b` |
| learning：紫微 | `c2d60900b4a73a3df615949fa9b14a68c8be9ac5f523ee7df0c66db18414d0c2` |
| learning：西占 | `80a25586fae04daa1d5787b568713cc9a7fee35afbbbedad7d3a24f2bf2df9be` |

全部SHA在课程目录和专属测试内绑定。本增量没有改动词典、learning运行时代码、charts、web、旧v3或其它工作树。

## 未验证、待核与安全范围

本次只启动单个Core测试进程，fixture使用offline_runtime并拒绝网络与子进程；Charts、数据库、模型、服务器、飞书访问均为0。
测试完成后当前进程为0。已按root要求冻结课程数据、Schema和测试，供00:15–30合规窗口完整回归；
本报告只证明82项专属结果，不预借完整回归或新HEAD CI绿色。

来源使用已交付36项注册表，5个外部官方URL本次未重新外访。各课保留司令异表、参数未标定、
调候全文未覆盖、阴刃逆行原典未找到、壬科天府版页未核等不同限制；不编页码、不删除待核。
第20课明确本命沿用民用UTC近似UT的旧实现口径，和western_timing实际UTC/UT1新法分别描述，
没有把技术来源存在说成预测效度验证。倒推继续冻结、隐藏、诚实拒绝。

无数据库迁移；回滚为撤回本增量静态课程/契约/测试。前端读取、当前用户授权与课程进度持久化仍由相应主线接线。
