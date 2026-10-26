# E2 M2输入线索与配对：离线只读审计

观察时间：2026-10-21T01:28:00.555755+08:00，北京时间。分支v4/p8-calc。

## 结论与边界

当前14条M2无盘输入都只有question/options，15类显式线索标记均未命中。宽松对照只换birth，
没有把捐赠案例的题文、选项、答案标签或case身份替进原题；原题/目标年/选项保留。
这个结论只针对具名规则可观察的输入结构和词法线索，不是题面已语义去识别、无训练记忆、
没有任何隐含线索或专业控制已经可评分的认证。未人工逐题展示私有原文，也没有模型判读。

发现两个跨来源的无盘题面指纹簇：NFKC和去空白后的题文相同，选项正文多重集相同，
不比较选项顺序。14条对应12种这样的题面，但仍是14条官方纳入记录、80题赛季分母和9个源内case。
同题面不证明同一命理案例：这两个簇的原birth九语义字段指纹实际不同，见下表。
没有去重、删题、更改14/66、seed、供体、题文、目标年或评分；专业分数仍为null。

## 方法、隐私与输入真相源

先完整读当前M2控制/载入/匹配/无盘构造和历史C0请求代码，按文档定位已有private/e2-sources缓存。
获root批准后仅用1个Core过程，offline_runtime拒绝网络并额外拒绝所有子进程；没有Git、Charts、
数据库或模型调用。复用原loader筛选2025赛季，6个缓存总360题，实际纳入MingLi9+BaziQA5。
读取前后文件SHA与既有M2审计固定SHA完全相同，未下载或写回题库。没有查证源仓库HEAD是否干净。

只在内存比较birth语义字段及原题属性，不输出出生值或出生指纹；输出仅题/案例身份hash、输入hash、
标记类型计数和簇比较的same/different/布尔。原题、选项、答案正文/字母以及原始ID均不进证据或日志。
缓存位置、来源名和已有文件SHA只用于复现，不是当前用户出生资料。

| 来源缓存文件 | 读取SHA256 | 原始题数 |
| --- | --- | ---: |
| mingli/data.json | 8a1eb273ff555b757a618651a7175800564c48f6f17111d09d1c28ea5c7068ce | 160 |
| baziqa/contest8_2021.json | 96fbdaff6ba3f0ffbebc387dd7acbea0b49c48821153b444e5c139e038801cef | 40 |
| baziqa/contest8_2022.json | d2e7978f61100a2c1104d01b5bbaee29008dcacf2c63ca51f8a52903f0aa5bef | 40 |
| baziqa/contest8_2023.json | 920afd8acbc1e17c360dc940c79833b096893a7483420b832f9929a1d8f0eed4 | 40 |
| baziqa/contest8_2024.json | df82d66b948206f755d7d5255583b8c3a217ed01de787283ef79ab73a52e769a | 40 |
| baziqa/contest8_2025.json | 6b39f6cea061ec54e92f0b2cace4a168389be1aa1eabb2ef3877d39f07880e2c | 40 |

## 固定控制的重放与字段不变量

固定seed=20261020。相同输入构造两次、同一输入倒序再构造，按问题身份重排比较均一致。
所有题只改birth；同一源case的多题始终同一供体，供体出生与原birth不同。原答案只保留在评分侧
Question结构内，未作为no_chart_input可见字段；选项重排后正文多重集逐题等于原选项。

14/14出生被替换；14/14原题/宽松的无盘显示完全相同；14/14无盘两键allowlist满足；9/9源内case供体一致。
重新生成的完整pairs与原M2审计逐项相等，pair SHA：`d2e93d7f66756fd73c33338ae4a53bd099ee3168eff2643f53c93302c0603538`。
原时间预检的2/14供体晚于目标年阻塞保留；本轮未改匹配、重试、重抽、造时区或运行排盘。

本轮是只读诊断，不是新增pytest案例、专业题库准确率、Charts可计算性或模型成绩。

## 显式线索标记

在问题正文和选项正文分别扫描；下表为至少命中一次的题数和总出现数。出生日期/地点值只在内存
作原字段字面比较，没有输出值或其指纹。标记是候选线索，不以出现某个词自动认定泄漏。
年份单独出现不能一律当出生年；本批明确目标年属于必须保留的原题，不因扫描而删除。

| 标记类型 | 命中题数 | 出现数 |
| --- | ---: | ---: |
| birth_context_word | 0 | 0 |
| calendar_date_literal | 0 | 0 |
| two_or_more_ganzhi_tokens | 0 | 0 |
| chart_or_pillar_term | 0 | 0 |
| explicit_answer_label_candidate | 0 | 0 |
| option_label_cross_reference | 0 | 0 |
| clock_time_literal | 0 | 0 |
| branch_hour_literal | 0 | 0 |
| explicit_gender_phrase | 0 | 0 |
| answer_explanation_marker | 0 | 0 |
| age_literal_cue | 0 | 0 |
| option_order_relative_reference | 0 | 0 |
| original_birth_ymd_value_match_candidate | 0 | 0 |
| raw_source_identity_literal | 0 | 0 |
| original_birth_location_literal_candidate | 0 | 0 |

这些规则覆盖中英文出生上下文、完整数字日期、钟表时分、地支时辰、明确性别短语、年龄、
连续干支/柱盘术语、显式答案/解析、选项标签互指与以上/上述等顺序词，以及原生日/出生地/ID字面匹配。
全0不排除汉字日期变体、隐含的反推条件、事件内容、常识先验或模型曾见过题库；它不等于语义脱敏证明。

## 逐题输入摘要（均15类标记0）

输入SHA按现有records.fingerprint的有限JSON序列化计算；包含原题和同seed重排选项，不含gold或birth。
它是内容绑定，不是授权签名，也不保证不同语境下的推理独立。

| 来源 | 题身份SHA256 | 案例身份SHA256 | 无盘输入SHA256 |
| --- | --- | --- | --- |
| MingLi-Bench | 28c69bf996835433f4c11ee9173c48ca4810907c6465c30dca1522735edf4128 | adcc402d9b36ac9eb01c622a67d52b8584d0aa3ca41999f1f74fafd54487f362 | e6242baec8a317570ea7cac7437eb00227c792e38ce627f06dd3fe90b042960d |
| MingLi-Bench | a34184f22b3ff78d9aa8e117cc11906cfb8cd10b63839cd6186eced06bab9f5f | adcc402d9b36ac9eb01c622a67d52b8584d0aa3ca41999f1f74fafd54487f362 | c8a6ff3a3b8ef6be33a8afa861f330b9406fab1162a49c83fea262b7524e218b |
| MingLi-Bench | c4b29fb216468c80854c776c663a72cbf6d0b2c6501a65afdefb95c3066e8802 | 1206150b1b2377993d7de65883c0f7b6b358f8f99d8443e81e6e628ce43ce5c6 | 182c2b4d50e6ec0b6d011c73b6292565645de9d1f6adcea4c7555005056a017e |
| MingLi-Bench | 932ea6dedada9ef6f9f7667cccb3bcbe5999c25a184fa190b2b32572e7da8e84 | 91a9bc61ca24e21df6b01456d44f620c21ecea0f6bf1e047943e0d2055ee26e0 | 3448d0b5719f4c84c73df0ce903f115bf12b6220e9399c35f9c260a4d7594b46 |
| MingLi-Bench | e00fb8971fe3ee0a1f413c935a32fd94e6cf9f2f4d62dfd070c0dd4f3dc370e9 | e55891995e64bd6c2d19d6e4b6d777441453e14b34a3dcfaa7d21361c41b1807 | 3994a98157100b38d51c1cd956c8967e4c975dff99d251ab5bab10c65c791b78 |
| MingLi-Bench | 88a714d6e3d758ba5742c9f10696dc9428b9ca3ddf2a462157b4605256e3c5dc | e55891995e64bd6c2d19d6e4b6d777441453e14b34a3dcfaa7d21361c41b1807 | 8e0d41b7719240ae6519a08d36804afb078a6fdd2f81cc27b2f7de42383eef29 |
| MingLi-Bench | 873c148bf90b5f266c084a835cd6b757dbb051fd735cc19633c5b3ea02f7da02 | 75aac7684729050a22897323aaa8f1583a205338625d9274b6ef894699ba2caa | cc44c600842db4c9b47da98921d6f5f2c9677bf9a50c1138c81ffb4ccc837076 |
| MingLi-Bench | a42fd86ad870e25aa29f999b278fd48c8c2c8f46f0cc6c95ae5b567d72fe2b2f | cc78f4d88cabefbcb99a2ed3f62d87edf065db9c80a50fa652b5b3662e68f335 | 67af4c1f63eda6a391b803f8fcf4ab2b5f3cfed3740c79fe3fb05dea7e365b59 |
| MingLi-Bench | e6fbf53ed8d60c52f02e08cf5005a946585be5eaa7e67fdd83510ba26b4d4a26 | cc78f4d88cabefbcb99a2ed3f62d87edf065db9c80a50fa652b5b3662e68f335 | b98987d7b23a87f1a8ba2146c388877678b8e2d5241de3ba23c12ad4570a78db |
| BaziQA | 484cb80021ddf63974c796ebb4199403d33533ac4aac0c151bf629f9f7cbe1e9 | 72f868f61e1b4ccb0c25bac5ad930c328b2ac84709f2fd39f9373b67dba22cb8 | 6d233f2d25aa6971ec01b17ecf7fab519b7f867e5b687bbcae0c9c843bc3d79a |
| BaziQA | 4b2cdd433a85a2c18e6d8c310a626c581f8802dca2c2673a31b26baa25f33351 | 72f868f61e1b4ccb0c25bac5ad930c328b2ac84709f2fd39f9373b67dba22cb8 | 68aaec0d4ff54ff826b3c3267ba2d4b506e5d822eaa25f75f52ba8c802cea6e3 |
| BaziQA | bee32fa733e414f9cfc1ef87a291d77dcc27880cb9e5f7e7d7bec1850d1e472a | 6709015614cc88b6af03be209eccbfd608098a64cdd6709abf66990b97cee0d1 | bb3004068bd8b221d1491b7415032a2e00117e8f9e5fc1f4aeb5341f22a8a2f5 |
| BaziQA | 3c2fc947abf8824b03df76cda08cc6ea769603d115faa16cd347b80881b22aa0 | 6709015614cc88b6af03be209eccbfd608098a64cdd6709abf66990b97cee0d1 | 1a563d15f1ff49073973569928ef8dd3712d4accc4e1b2d5c6402785d20a9780 |
| BaziQA | 35750486bd46040f2de0b1f25ecb166d871a3888fd1e1fb7279e0914807003bf | b936a8a347f4741c8bdd102164662dfecc8bdeb2d00dd1e6f8de44219a86e86c | d0c87944124877b35e96b47ff1e92f0fdf8a48c7d15f17b62453622dd4df2bf5 |

## 两个题面簇与原条件比较

在内存比较的birth字段仅为year、month、day、hour、minute、gender、location、calendar、approximate，
不混入source/case身份。指纹比较结果只发布same/different及计数；不发布出生指纹或字段值。
target_year与gold对应原选项正文也仅发布相同/不同，不公布年份值、答案正文或正确标签。
缺失和已有值不强行合并；来源记录不同或精度未知也会产生different，因此也不据different断言一定是不同真人。

簇1题面指纹：`98c093744e15e1eb0b17e7c38f772f24c1015b15555ed6759ffed160e8097e6c`。

| 来源 | 题身份SHA256 | 案例身份SHA256 |
| --- | --- | --- |
| MingLi-Bench | 28c69bf996835433f4c11ee9173c48ca4810907c6465c30dca1522735edf4128 | adcc402d9b36ac9eb01c622a67d52b8584d0aa3ca41999f1f74fafd54487f362 |
| BaziQA | 484cb80021ddf63974c796ebb4199403d33533ac4aac0c151bf629f9f7cbe1e9 | 72f868f61e1b4ccb0c25bac5ad930c328b2ac84709f2fd39f9373b67dba22cb8 |

原birth九字段：different；6/9字段相同；
差异字段仅列名：hour、location、approximate；非null字段数分别8/9。
目标年相同：true；gold对应原选项正文相同：true。

簇2题面指纹：`fb450800c6a03f9687f008c94c24db106c00a8637539a36b49e9557d4df705ec`。

| 来源 | 题身份SHA256 | 案例身份SHA256 |
| --- | --- | --- |
| MingLi-Bench | a34184f22b3ff78d9aa8e117cc11906cfb8cd10b63839cd6186eced06bab9f5f | adcc402d9b36ac9eb01c622a67d52b8584d0aa3ca41999f1f74fafd54487f362 |
| BaziQA | 4b2cdd433a85a2c18e6d8c310a626c581f8802dca2c2673a31b26baa25f33351 | 72f868f61e1b4ccb0c25bac5ad930c328b2ac84709f2fd39f9373b67dba22cb8 |

原birth九字段：different；6/9字段相同；
差异字段仅列名：hour、location、approximate；非null字段数分别8/9。
目标年相同：true；gold对应原选项正文相同：true。

两个簇都不是完整birth语义相同的记录。因此只称“两个无盘题面指纹簇、12种题面”，
不能改称“只有12道独立专业题”或仅凭题面合并案例。无盘去掉条件后相同问题/选项、
及同case内多题相关性，都需要评分协议另行处理；本审计不修改样本、gold、权重或方差。

## 旧C0与本轮无盘的接线区别

night28_controls.no_chart_input是本M2无盘allowlist入口。旧protocol_v2._request的C0语义是
“无排盘但有原出生资料”，仍携带record.birth.public_input()；payload还包含question_id。
这是README已有声明，不能说本轮已经向模型泄漏；当前没有真实请求或Agent接线。
主线接M2无盘须显式走新两键入口，不能把旧C0改名后当无出生控制。原ID可能编码出生资料，
本轮仅核新入口没有ID，不重新发布原ID，也未声称旧C0是恶意或新增缺陷。

## 待核与复现证据

待核：题面与原条件丢失后的含义、跨源相近题与同case相关性对统计推断的影响、人工语义泄漏复核、
训练集污染、真实输入地理/历史时区/精度、专业三组完整可计算性、2/14时间阻塞的裁定，以及主线真实传输边界。
未改14纳入/66排除/seed/供体/题文；未加专业成绩，corpus_scores=null。

私有可复现扫描：private/p8-validation/e2_input_leakage_scan.py（仅本机，不作为新的运行时变体发布）。
私有诊断JSON也只含本报告类型的hash和计数，原文没有写入。执行前已清凭据、关追踪，
拒绝网络与所有子进程；源文件读取前后SHA一致。所有进程现已结束，未提交/推送。

扫描脚本LF SHA：`8036d05d8ced7e7ad042d8efcecce6e35ac4c2ee9b581dde1efc71127b025078`。
私有哈希诊断LF SHA：`f8f3b25c67e13e22669272ee82ba705642f9c822d4597d3dd2761f0f99938122`。

| 控制/载入源码 | LF SHA256 |
| --- | --- |
| night28_controls.py | 634a7e2883d67a968db8679dbe387e7993d91543f67b2658aafa66200228cc49 |
| controls_v2.py | 06b9496f189811ce98564da237c28b3759d33c776f72833925de7d4a093a003a |
| loaders_v2.py | 9c7ec60f7312860b87dcd644577ee85951c083db69b3196073a3e7ce3840585a |
| eligibility_v2.py | 5239f38db7c4329df5d433c7cc77b510826259c35eea4bd3b85c61a48644945b |
| records.py | 2a5b56126841c65100f2524ea39f896c0605902adcf75d535e11c1a01609a656 |

落盘后再以内存原记录核对报告字面导出：14条原题全文、原选项正文、原始题/案例ID、出生地点
的匹配数全部0；没有将出生指纹、日期值或gold正文写入报告。检查只输出上述计数，不输出未命中/命中的原文。

模型、Charts、DB、网络、服务器、飞书请求均为0。产品源码/题库/控制记录写入0；本轮唯一公开新增为本报告。
