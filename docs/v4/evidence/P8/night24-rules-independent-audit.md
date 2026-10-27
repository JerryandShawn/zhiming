# 24号十项修订：独立只读复核

执行时间：2026-10-18 23:45–23:55 Asia/Taipei；分支 `v4/p8-calc`，复核时HEAD为 `6cd04ad0fcb2bedaf6183525b495391c58c64ec2`，另含正在收尾的未提交P8工作树。这里的“独立”指另一代理重新读代码和编写临时核对表达式，不代表专家校勘或独立命理理论验证。

结论：对照24号§6全部10项、`rules-review.md`及实际P8实现，未发现新的代码级缺陷。没有修改算法、规则、测试或原有证据文件；本报告是本次唯一新增文件。模型请求0，服务器请求0，未重新检索原刊。

## 指令与实现核对

| 项 | 实际核对 | 结果与边界 |
| --- | --- | --- |
| 1 伤官牵制 | `p8_structure.restraint`、`conditions.exposed_combination` | 正官透出才触发伤官牵制，七杀不阻断；庚辛例外明确输出。旧v3 AVOID仍为七杀，属于用户要求保护的旧口径，不据此报新缺陷 |
| 2 其余牵制与七杀支持 | `restraint`、`reviewed_useful` | 七杀正偏财同查且须无食神透出；印正偏财同查；财比劫及七杀同查；食神偏印保持。七杀支持增加正偏印；JSON输出使用list，不修改legacy tuple。印轻/财轻比重、制伏有效和救应未判均可见 |
| 3 气位与三格 | `reviewed_regular`、`reviewed_extra`、规则注册表 | 气位和杂气notes存在；三格各含3个布尔子条件，分别注册为1条复合候选。总数38≤40，未用删除旧ID凑数；没有声称已经完整实现原文成格法 |
| 4 出处与领域 | `rules_v1.json`、`conditions.climate_missing` | 官杀/食杀39、伤官印41、俗称财多42、调候主源穷通及透藏分列；24个格局domains与同一十神映射逐项相等 |
| 5 交互映射 | `interaction_metadata`、`interaction_mapping` | 排序仅子平/通用，展示为项目口径；传统宫分、现代领域与待核六亲配法随annotation_basis输出；没有健康规则 |
| 6 神煞异表 | `schools.json`、`named_stars` | 天乙庚辛异说显式可选；阴刃第三说带待核状态，默认不变；基础章错字已修 |
| 7 紫微 | `flying_profile`、飞化函数及技能01/03 | 默认iztro壬科左辅、quanshu仅壬科改天府；保留actual生年/运限。时间主口径、北京时间并列与晚子月末差异均明示；全书原刊待核没有被升级为已校勘 |
| 8 调候 | `climate_review_24.json`、`reviewed_climate`、技能04 | P8独立来源复核层标佐神未全收、乙申总论/专段/条件区别；共享旧表及120键候选未改 |
| 9 西占技能 | 技能02/04与rules-review补证 | Lilly定位和软件容许度差异已记录；项目6度未改，没有以书中方法为数值算法背书 |
| 10 正反例与保护范围 | 下列临时命令 | 114个fixture条件断言、114个公开盘完整assessment断言及3份hit列表通过；受检35个旧文件LF内容无变化 |

38条的实际组成是24 `pattern_condition`、5 `exposed_combination`、4 `palace_activation`、3 `extra_pattern`、1 `wealth_weak`、1 `climate_missing`。`rules-review.md`覆盖全部38个rule_id；三份公开盘各含38个assessment。

## 80,000组合：构造、期望与独立性

核对对象是8格的牵制布尔，不是整盘，也不是新增80,000个pytest case。遍历10个日主和10种十神的3个有序透干位置（允许重复，10³=1000），每组检查8格：`10 × 1000 × 8 = 80,000`次谓词比较。位置排列和重复会产生相同十神集合，因此这些不是80,000份统计独立样本，更不是80,000份真实出生记录。

期望直接按24号§6第1/2项写成集合布尔表达式；未调用待测函数生成期望，未读取其`checks`作为答案。输入只用十神标签和日主，不经过排盘，可专门发现条件方向翻转。它仍与实现依据同一裁定，不能排除两者共同误读原文，也不测天干到十神的历算映射。存在未判断的力量条件不在期望中偷偷补全。

会话实际使用PowerShell将以下Python内容从标准输入交给Core解释器执行；脚本没有保存到private或新增测试文件。仓库根为 `C:\Users\Administrator\Documents\Codex\zhiming-v4-p8`。

```powershell
$env:PYTHONUTF8='1'
@'
from itertools import product
from mingjing_core.adapters.charts.p8_structure import restraint
GODS=['比肩','劫财','食神','伤官','偏财','正财','七杀','正官','偏印','正印']
cases=0
for master,exposed in product('甲乙丙丁戊己庚辛壬癸', product(GODS,repeat=3)):
 p=set(exposed)
 expected={
  '正官':'伤官' in p,
  '七杀':bool(p & {'正财','偏财'}) and '食神' not in p,
  '正印':bool(p & {'正财','偏财'}),
  '偏印':bool(p & {'正财','偏财'}),
  '正财':bool(p & {'比肩','劫财','七杀'}),
  '偏财':bool(p & {'比肩','劫财','七杀'}),
  '食神':'偏印' in p,
  '伤官':master not in '庚辛' and '正官' in p,
 }
 for god,blocked in expected.items():
  actual=restraint(god,list(exposed),master)
  assert actual['blocked'] is blocked,(master,exposed,god)
  assert actual['metal_water_exception'] is (god=='伤官' and master in '庚辛')
  assert actual['not_evaluated']
  cases+=1
print('independent_predicate_truth_table', cases,'passed')
'@ | & 'C:\Users\Administrator\Documents\Codex\zhiming-v4\.venv-core\Scripts\python.exe' -
```

实际输出：`independent_predicate_truth_table 80000 passed`。每次比较另核庚辛例外标志及未判说明非空；不把这些附属断言再算成新增样本数。

## 114 + 114断言及旧文件LF核对

下列也是实际执行的stdin脚本。第一组是38条×正例/反例/额外反例，114次`met`断言；第二组按三份公开盘的38项逐一比较完整assessment字典，共114次等值断言，另比较3份hit_id顺序。这里复用现有合成fixture和既有公开快照，属于重复计算与变更核查，不是独立原典或预测效度验证。

```powershell
$env:PYTHONUTF8='1'
@'
import hashlib,json,subprocess,sys
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path('tests/v4').resolve()))
from p8_rules_sample_context import make_data
from mingjing_core.adapters.charts.rules import evaluate_rules
fixture=json.loads(Path('tests/v4/fixtures/p8_rule_cases.json').read_text(encoding='utf8'))
condition_assertions=0
for ident,cases in fixture['cases'].items():
 for label,case in cases.items():
  actual=evaluate_rules(make_data(case['pillars'],case['layers']))
  row=next(r for r in actual['assessments'] if r['rule_id']==ident)
  assert row['met'] is (label=='positive'),(ident,label)
  condition_assertions+=1
snapshots=json.loads(Path('docs/v4/evidence/P8/rules-public-snapshots.json').read_text(encoding='utf8'))
snapshot_assertions=0
for case in snapshots['charts']:
 actual=evaluate_rules(make_data(case['pillars']))
 assert len(actual['assessments'])==len(case['assessments'])==38
 for observed,expected in zip(actual['assessments'],case['assessments'],strict=True):
  assert observed==expected,(case['label'],expected['rule_id'])
  snapshot_assertions+=1
 assert [r['rule_id'] for r in actual['rule_hits']]==case['hit_ids']
base='f23b942ce698a3f7ee0b98c918d43053fe773433'
paths=subprocess.check_output(['git','ls-tree','-r','--name-only',base]).decode('utf8').splitlines()
exact={'mingjing_core/adapters/charts/adapter.py','mingjing_core/adapters/charts/worker.py',
       'mingjing_core/knowledge/p8_bazi/climate.json'}
protected=sorted(p for p in paths if p.startswith(('hermes/','mingjing_core/calculations/')) or p in exact)
entries=[]; counts=Counter()
for path in protected:
 old=subprocess.check_output(['git','show',base+':'+path]).replace(b'\r\n',b'\n')
 now=Path(path).read_bytes().replace(b'\r\n',b'\n')
 assert old==now,path
 entries.append([path,hashlib.sha256(now).hexdigest()])
 counts['hermes' if path.startswith('hermes/') else 'calculations' if
        path.startswith('mingjing_core/calculations/') else 'default_and_shared']+=1
aggregate=hashlib.sha256(json.dumps(entries,ensure_ascii=False,sort_keys=True,
                                  separators=(',',':')).encode('utf8')).hexdigest()
focus={p:s for p,s in entries if p in exact or p=='mingjing_core/calculations/bazi/structure.py'}
print(json.dumps({'fixture_condition_assertions':condition_assertions,
 'snapshot_assessment_assertions':snapshot_assertions,'snapshot_charts':len(snapshots['charts']),
 'snapshot_hit_lists':3,'protected_base':base,'protected_file_count':len(entries),
 'protected_groups':dict(counts),'protected_mismatches':0,
 'protected_LF_manifest_sha256':aggregate,'focus_LF_sha256':focus},ensure_ascii=False))
'@ | & 'C:\Users\Administrator\Documents\Codex\zhiming-v4\.venv-core\Scripts\python.exe' -
```

实际结果：fixture **114/114**；公开assessment **114/114**；公开盘 **3**；hit列表 **3/3**。保护基点为`f23b942ce698a3f7ee0b98c918d43053fe773433`，受检 **35文件**（hermes 25、calculations 7、默认入口/共享表3），**0项LF内容差异**。这里只报告本代理实际检查的35份，不能替代主代理更广的141文件保护检查。

按路径排序后的`[[path, LF_sha256], ...]`使用代码所示有限JSON序列化，清单SHA256：

`f4daba29d9c35b92f174c237a996bafb69dc6bc4f3e0fff86c53c279df0dc6c7`

| 保护文件 | LF归一SHA256 |
| --- | --- |
| `mingjing_core/adapters/charts/adapter.py` | `073c8e572b9466250f14a8203fcb323dc3529b51743f1fcbca5385c0b355ef2d` |
| `mingjing_core/adapters/charts/worker.py` | `a6d1ff8d471fc6c0fbcc68e513243a6ba9ee97107137804adb3744724d03fad0` |
| `mingjing_core/calculations/bazi/structure.py` | `fd571fb968f5b5204faa89a0824f05d80d67e00d042b521388eebfb54adbaec2` |
| `mingjing_core/knowledge/p8_bazi/climate.json` | `8fe8e8ee0ff2af8fba1daaa9f5ba0157b2513318dd1c1452f54163e6c9af20f4` |

另实际执行了：

```powershell
git diff --name-only f23b942ce698a3f7ee0b98c918d43053fe773433 -- hermes mingjing_core/calculations mingjing_core/adapters/charts/adapter.py mingjing_core/adapters/charts/worker.py mingjing_core/knowledge/p8_bazi/climate.json
```

输出为空。用于确认上述受保护路径没有已跟踪新增、删除或工作树差异；未宣称覆盖未跟踪文件或所有仓库路径。

## 未覆盖与解释限制

- 临时真值表直接操作十神输入，不验证出生历算、十神映射、整盘真实精度或完整成败救应；三格复合条件、神煞和源元数据另经代码阅读与现有fixture核查，不属于80,000项的覆盖。
- 气位为所选司令表逆序这一具名项目定义，`qi_rank=any`仍允许并存候选；没有将其说成已作本气优先定格。
- 原刊、异本、女性配法、阴刃逆行、完整调候及其他已标待核内容，本次没有重新取得原典，不能据软件检查解除待核状态。
- 公开快照复算与fixture命中不等于专家评审或现实预测通过；没有新增模型实测、服务器、数据库、浏览器、主线接线或完整CI验证。
- 哈希保护对比35份基点已跟踪文件的LF内容，不检查运行时安装包、锁文件、服务状态、未跟踪文件，也不是来源签名。

复现代码完整保存在本报告内，不另写一份与实现镜像的pytest文件；本次未以增加用例数量冒充新增专业能力。
