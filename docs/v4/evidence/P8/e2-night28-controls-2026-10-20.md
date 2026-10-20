本评测衡量的是与命理比赛标准答案的一致性，不是现实预测的效度；2025 年比赛题可能已进入 2026 年发布模型的训练数据；40 题量级的子集，95% 置信区间约为 ±15 个百分点。

# E2 M2控制脚本演练（2026-10-20，北京时间）

本轮14题专业分数和置信区间均为null；上述40题±15个百分点是旧方案粗略说明，不是本次实测区间。

## 来源与真实分母

2025只用于筛选比赛赛季。完整来源与2025子集分别计数，其他赛季不混进本轮排除题数。
文件SHA256绑定本次实际读取内容；commit仅记录缓存仓库HEAD，不冒称工作树已校验干净。

| 来源 | 全量题数 | 全量结构有效 | 全量年度纳入 | 2025原题 | 2025纳入 | 2025排除 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| mingli | 160 | 160 | 22 | 40 | 9 | 31 |
| baziqa | 200 | 199 | 26 | 40 | 5 | 35 |

| 来源 | 缓存commit | 文件 | 文件SHA256 | 全量题数 | 2025题数 |
| --- | --- | --- | --- | ---: | ---: |
| mingli | `b7433280fd86d7a7c27debbc47d0303c218f0bfd` | data.json | `8a1eb273ff555b757a618651a7175800564c48f6f17111d09d1c28ea5c7068ce` | 160 | 40 |
| baziqa | `8ea8222f8bd8ef8a6f1a5fb012344935a66e7686` | contest8_2021.json | `96fbdaff6ba3f0ffbebc387dd7acbea0b49c48821153b444e5c139e038801cef` | 40 | 0 |
| baziqa | `8ea8222f8bd8ef8a6f1a5fb012344935a66e7686` | contest8_2022.json | `d2e7978f61100a2c1104d01b5bbaee29008dcacf2c63ca51f8a52903f0aa5bef` | 40 | 0 |
| baziqa | `8ea8222f8bd8ef8a6f1a5fb012344935a66e7686` | contest8_2023.json | `920afd8acbc1e17c360dc940c79833b096893a7483420b832f9929a1d8f0eed4` | 40 | 0 |
| baziqa | `8ea8222f8bd8ef8a6f1a5fb012344935a66e7686` | contest8_2024.json | `df82d66b948206f755d7d5255583b8c3a217ed01de787283ef79ab73a52e769a` | 40 | 0 |
| baziqa | `8ea8222f8bd8ef8a6f1a5fb012344935a66e7686` | contest8_2025.json | `6b39f6cea061ec54e92f0b2cace4a168389be1aa1eabb2ef3877d39f07880e2c` | 40 | 40 |

## 逐题纳入清单

本次实际纳入14题，**不是40题样本**；没有运行专业题库排盘、Agent或模型，也没有分数。
源公开ID也可能编码出生信息，所以本报告一律只发布题身份/案例SHA256，不复印ID、题面、选项、答案或出生资料。

| 来源 | 题身份SHA256 | 案例SHA256 | 比赛年 | 题目目标年 | year_basis | reason | 年份字符区间 |
| --- | --- | --- | ---: | ---: | --- | --- | --- |
| MingLi-Bench | `28c69bf996835433f4c11ee9173c48ca4810907c6465c30dca1522735edf4128` | `adcc402d9b36ac9eb01c622a67d52b8584d0aa3ca41999f1f74fafd54487f362` | 2025 | 1980 | question_explicit_target_year | explicit_target_clause | [[0, 5]] |
| MingLi-Bench | `a34184f22b3ff78d9aa8e117cc11906cfb8cd10b63839cd6186eced06bab9f5f` | `adcc402d9b36ac9eb01c622a67d52b8584d0aa3ca41999f1f74fafd54487f362` | 2025 | 1993 | question_explicit_target_year | explicit_target_clause | [[0, 5]] |
| MingLi-Bench | `c4b29fb216468c80854c776c663a72cbf6d0b2c6501a65afdefb95c3066e8802` | `1206150b1b2377993d7de65883c0f7b6b358f8f99d8443e81e6e628ce43ce5c6` | 2025 | 2018 | question_explicit_target_year | explicit_target_clause | [[3, 8]] |
| MingLi-Bench | `932ea6dedada9ef6f9f7667cccb3bcbe5999c25a184fa190b2b32572e7da8e84` | `91a9bc61ca24e21df6b01456d44f620c21ecea0f6bf1e047943e0d2055ee26e0` | 2025 | 2022 | question_explicit_target_year | explicit_target_clause | [[0, 5]] |
| MingLi-Bench | `e00fb8971fe3ee0a1f413c935a32fd94e6cf9f2f4d62dfd070c0dd4f3dc370e9` | `e55891995e64bd6c2d19d6e4b6d777441453e14b34a3dcfaa7d21361c41b1807` | 2025 | 2001 | question_explicit_target_year | explicit_target_clause | [[3, 8]] |
| MingLi-Bench | `88a714d6e3d758ba5742c9f10696dc9428b9ca3ddf2a462157b4605256e3c5dc` | `e55891995e64bd6c2d19d6e4b6d777441453e14b34a3dcfaa7d21361c41b1807` | 2025 | 2022 | question_explicit_target_year | explicit_target_clause | [[2, 7]] |
| MingLi-Bench | `873c148bf90b5f266c084a835cd6b757dbb051fd735cc19633c5b3ea02f7da02` | `75aac7684729050a22897323aaa8f1583a205338625d9274b6ef894699ba2caa` | 2025 | 2004 | question_explicit_target_year | explicit_target_clause | [[3, 8]] |
| MingLi-Bench | `a42fd86ad870e25aa29f999b278fd48c8c2c8f46f0cc6c95ae5b567d72fe2b2f` | `cc78f4d88cabefbcb99a2ed3f62d87edf065db9c80a50fa652b5b3662e68f335` | 2025 | 2021 | question_explicit_target_year | explicit_target_clause | [[3, 8]] |
| MingLi-Bench | `e6fbf53ed8d60c52f02e08cf5005a946585be5eaa7e67fdd83510ba26b4d4a26` | `cc78f4d88cabefbcb99a2ed3f62d87edf065db9c80a50fa652b5b3662e68f335` | 2025 | 2024 | question_explicit_target_year | explicit_target_clause | [[3, 8]] |
| BaziQA | `484cb80021ddf63974c796ebb4199403d33533ac4aac0c151bf629f9f7cbe1e9` | `72f868f61e1b4ccb0c25bac5ad930c328b2ac84709f2fd39f9373b67dba22cb8` | 2025 | 1980 | question_explicit_target_year | explicit_target_clause | [[0, 5]] |
| BaziQA | `4b2cdd433a85a2c18e6d8c310a626c581f8802dca2c2673a31b26baa25f33351` | `72f868f61e1b4ccb0c25bac5ad930c328b2ac84709f2fd39f9373b67dba22cb8` | 2025 | 1993 | question_explicit_target_year | explicit_target_clause | [[0, 5]] |
| BaziQA | `bee32fa733e414f9cfc1ef87a291d77dcc27880cb9e5f7e7d7bec1850d1e472a` | `6709015614cc88b6af03be209eccbfd608098a64cdd6709abf66990b97cee0d1` | 2025 | 2001 | question_explicit_target_year | explicit_target_clause | [[3, 8]] |
| BaziQA | `3c2fc947abf8824b03df76cda08cc6ea769603d115faa16cd347b80881b22aa0` | `6709015614cc88b6af03be209eccbfd608098a64cdd6709abf66990b97cee0d1` | 2025 | 2022 | question_explicit_target_year | explicit_target_clause | [[3, 8]] |
| BaziQA | `35750486bd46040f2de0b1f25ecb166d871a3888fd1e1fb7279e0914807003bf` | `b936a8a347f4741c8bdd102164662dfecc8bdeb2d00dd1e6f8de44219a86e86c` | 2025 | 2024 | question_explicit_target_year | explicit_target_clause | [[3, 8]] |

字符区间为原题Unicode字符串的零基、左闭右开索引，只定位明确目标年，不包含任何原题片段。
目标年份集合：[1980, 1993, 2001, 2004, 2018, 2021, 2022, 2024]；目标年等于比赛年2025的题数：0。
year_basis固定为question_explicit_target_year，不回退到出生年、比赛年、当前年；有歧义的题保守排除。

## 排除理由与逐题记录

| 原因 | 本2025子集排除题数 |
| --- | ---: |
| explicit_year_target_unresolved | 5 |
| no_explicit_target_year | 61 |

本2025子集缺标签排除0题；其他赛季的缺标签不进入本分母。缺标签只排除对应问题，不补造标签、答案或整人整文件连坐。
下表共66行，每行代表一条排除记录；原因统计不含其他比赛年份。

| 来源 | 题身份SHA256 | 排除原因 | year_basis | 年份字符区间 |
| --- | --- | --- | --- | --- |
| MingLi-Bench | `0a8378d2f97a35f5831702dc2d405d8916f41ab4c52b5246e3ad0c228b732c6b` | no_explicit_target_year | null | [] |
| MingLi-Bench | `2a23da2364ef87232f6b9022e3c51435556c44b9883bcff2614044b1cf7b91fa` | no_explicit_target_year | null | [] |
| MingLi-Bench | `a4b28f557127e0e64bffa1261002685a10f6422b90985442559ef20c4eefced9` | no_explicit_target_year | null | [] |
| MingLi-Bench | `ffcaba9ab2a0d8fb8a24231f69a1860b51c192d499b6074ba2cbfcef52d0ad6d` | explicit_year_target_unresolved | null | [] |
| MingLi-Bench | `811aed1f537cd5a164c3df60e529c28dd7c9cac774230a990887b2dd9722e6fd` | no_explicit_target_year | null | [] |
| MingLi-Bench | `9a9b9add2f3ac69d403f7a7b82f744b91f8a662647604f2b59b3fcb11898f4a7` | no_explicit_target_year | null | [] |
| MingLi-Bench | `34cdc3597e81a420a27d898526f1c7fcb8e11a33abfd093d622f85140b644315` | no_explicit_target_year | null | [] |
| MingLi-Bench | `f96fe04ab6ab82d8d9c90bd4d647dd267a8d172bbd7bf75bb524bb05b4dfab07` | no_explicit_target_year | null | [] |
| MingLi-Bench | `09b0a799e5a16c677bb25d87aebbf341fe9a3b87cacfc8876e3bd36e813bb36e` | no_explicit_target_year | null | [] |
| MingLi-Bench | `3ee63ceb61d576ce3c3ad594575eab0c301c757f4760d9f3314d0c5b0c6e10b6` | no_explicit_target_year | null | [] |
| MingLi-Bench | `ecf3683279756f83f18411dd9bebd9aa589343a1ef6881704119a9ab57df950a` | no_explicit_target_year | null | [] |
| MingLi-Bench | `93a73f0031a1962073c14805c931110f7eb1e1e02a13096bea3bcd1c1ffd8444` | no_explicit_target_year | null | [] |
| MingLi-Bench | `0c68f5a6edf7d80823fa09cb6a4cf9f3e69ff01df725f7ea7dc3594e91ea0d1d` | no_explicit_target_year | null | [] |
| MingLi-Bench | `e9bda49cd08b89cbea0ba61cc7fd1babe0760a423350e6b15d25564cab4e5608` | no_explicit_target_year | null | [] |
| MingLi-Bench | `c1ffd0d8e7ccc4d29325c1527cc2c8e9cb5c53aa35f3edf2bd2167c8d499bfa0` | no_explicit_target_year | null | [] |
| MingLi-Bench | `f18d661336147b1c4d16345b0dddecb69a20a71851a75273ff0f09d382d95dc8` | no_explicit_target_year | null | [] |
| MingLi-Bench | `244816b4eee4388eace9e5a93ba49cf0b757a83c74fc8fe508f8862a27136da1` | no_explicit_target_year | null | [] |
| MingLi-Bench | `17d5b3ff257b2a1791710d1fade537b3c9fdfa630797eb58408f042f4270b385` | no_explicit_target_year | null | [] |
| MingLi-Bench | `d9ff266b496e5bb36b7d2b5cfd2a67f2e866ffd37d8f4b93868d6155fed9349a` | no_explicit_target_year | null | [] |
| MingLi-Bench | `cf8c028b50dd96e79cd95ddd6a9af04f7db5c06878b5be57efdefeee4775b9f1` | no_explicit_target_year | null | [] |
| MingLi-Bench | `d2e1ed5a9a981a1b2f42e9c4938afd3c1940f7cc7ffa65a0d7559c2c2bc08f1f` | no_explicit_target_year | null | [] |
| MingLi-Bench | `35efc70385a1d30802e16a4ddf8acbcdc709cd3f1b17428cae72a181af40d166` | no_explicit_target_year | null | [] |
| MingLi-Bench | `0bab098a945079183266ef8167090ea9cf68e5124612213e276180d47b8055cb` | no_explicit_target_year | null | [] |
| MingLi-Bench | `7e409cf07c06191bbf1f0b7bea0f50e7f7c395697bf5bf333c5908296d3b143e` | no_explicit_target_year | null | [] |
| MingLi-Bench | `d615acd5da4ceff7bebd08c4158175f252ad402d14967ce3de6bc6dd7fff378c` | no_explicit_target_year | null | [] |
| MingLi-Bench | `aad312af3f431b63a707bd72ace725fe9fa8ce2441b8e38a30f2d30a4ba9731a` | no_explicit_target_year | null | [] |
| MingLi-Bench | `884a6dc8c96c8dff12f0926e5d7367555e7a7829627bf229c26a8380c7204cf4` | no_explicit_target_year | null | [] |
| MingLi-Bench | `a64d07f9b8932f9165b2b47584ec2f63c3011d49a9f40ff6f126735a1a43cc97` | no_explicit_target_year | null | [] |
| MingLi-Bench | `29b302dfbd115a5cb9d6c04a60f056cda81115bf48c816459ec96c588fb139ea` | no_explicit_target_year | null | [] |
| MingLi-Bench | `a833be4158eacf76dee4ab58a54144591700c01d97c6eddf2faa4d40574feee1` | no_explicit_target_year | null | [] |
| MingLi-Bench | `0a56dc135c3749be91f87d3413aed0c34053bfd23daf44ca2d214bb13fef2894` | no_explicit_target_year | null | [] |
| BaziQA | `ac5175660bcd0e9cf15514e494a3f6e99b29b58c3a3ea9da8f230487cd79ce5c` | no_explicit_target_year | null | [] |
| BaziQA | `5280c138385561c866424985685951105f6e648cd0621d4eb7d75e37b63db710` | no_explicit_target_year | null | [] |
| BaziQA | `dac430faa43dd105f14b73745e4982bf9f5d5d7eba5eb97074c5bbb9f7ff4435` | no_explicit_target_year | null | [] |
| BaziQA | `d4fee89d42f48578fb49c1401cf895eed53b5d086454e2720fe7b1a3e7f12ea0` | explicit_year_target_unresolved | null | [] |
| BaziQA | `996a302afb5447afd9cf74f12ea7ef4cb72d56d7aa5e6f81901c7a74c564ea42` | no_explicit_target_year | null | [] |
| BaziQA | `f83d7b9323768877060039c704de630896ca4febdc6e9672fac21573c7ec774a` | explicit_year_target_unresolved | null | [] |
| BaziQA | `343263f5e83a1f3ea611dcfceddb9e8ab589c5b02ede28235df807669694ccd4` | no_explicit_target_year | null | [] |
| BaziQA | `70140b2b4bd61074c142a184ff157a44e0cddf413b65654ad7d62a1300be27e2` | no_explicit_target_year | null | [] |
| BaziQA | `a708a3372856d1d7cc309a0dd04c4cf864d414be7b1aa1f2fc966166a72b2375` | no_explicit_target_year | null | [] |
| BaziQA | `5c189c36fe34f3f670c80ad47e4990d52aa02f1bf1f1c34594b7ae2ac7255e97` | no_explicit_target_year | null | [] |
| BaziQA | `557e1e694495b482aa1c2aafd0cc659e32c640b6138fd9947138cf3696c7245e` | no_explicit_target_year | null | [] |
| BaziQA | `940900599ee9c72405126987079612eb1171f582f5f4019d380fb4e87dbc4e61` | no_explicit_target_year | null | [] |
| BaziQA | `eb860436019d22346e706f9ac463acd410c6a664a6ef683d5ab2e5b67a3afdf6` | explicit_year_target_unresolved | null | [] |
| BaziQA | `b9ecb037de452e9c6f6e05d60537f2c016ebb405cce4ca2e540382ceb597db78` | no_explicit_target_year | null | [] |
| BaziQA | `e91f0aabbf12dcdbc0931555bb59eef99ac862771980b5e1808a8eecc1f0ee8e` | no_explicit_target_year | null | [] |
| BaziQA | `b84d7ddacb0a890306a4d28364f142c9ddeefc3620243f1d983182d150e708b7` | no_explicit_target_year | null | [] |
| BaziQA | `f598d0930d7f001fb3aa4a60d6e5d43df803cfd77f316606787bf65e1df1fae9` | no_explicit_target_year | null | [] |
| BaziQA | `98abfe8537b85c31b193e4da59660a3cff23acc0677f6e2e4e5b8a3ff3c6fe86` | no_explicit_target_year | null | [] |
| BaziQA | `d0f983087b5cb2e395eddcb527e81476b8b18de524e6f60abc22c7f6159e7835` | no_explicit_target_year | null | [] |
| BaziQA | `bced8f6b7de85a6f3070f2159a31b60fc014029288553b21d86ae3d213f5344c` | no_explicit_target_year | null | [] |
| BaziQA | `fc59524809caa2c376fc47a865cd9e5be03674fcfa1e1c0b7f759e2bdf92cce4` | no_explicit_target_year | null | [] |
| BaziQA | `70c6c1c0e57cd104b1ac7ee31d42f544ded365eb65c4a1b0a76b161be08f959c` | no_explicit_target_year | null | [] |
| BaziQA | `4dd982af112cb3efa27f6f15f72b61cc2cc7d6178ba7f0c4bf92fa6566354249` | no_explicit_target_year | null | [] |
| BaziQA | `e2a8d76aee3349c62068ebc7a3a9677bce9971a6b11694e5d4bdeb83847f60a5` | no_explicit_target_year | null | [] |
| BaziQA | `23fc8fb183e4184771dd46e6e91ffde58ed7eec28e4656e9a442c9be60194792` | explicit_year_target_unresolved | null | [] |
| BaziQA | `4667113979dd8941ad968100226e2990597cd3fb8cf8dd38f6e6ae46eabcb5fe` | no_explicit_target_year | null | [] |
| BaziQA | `34cecd37603b63fe0b762083d7fbbd86285c49ea5fa59399d921b8eb98461562` | no_explicit_target_year | null | [] |
| BaziQA | `9f8a9639e9ab69c232400003ed1c8a2ed91cbf4b594e46cf4ac80c6c252599b0` | no_explicit_target_year | null | [] |
| BaziQA | `09e410a6f011ec665544b0871376cd161f8832567b44ae9837bf8977a85a7c35` | no_explicit_target_year | null | [] |
| BaziQA | `8237adc3d43b4bb47dcf2611fe1e810a7353ee52e733a931db8ef1f4062db8d7` | no_explicit_target_year | null | [] |
| BaziQA | `4f514f05c4a1f6d9dd4260c344d945f5bba3eed2dd30522bb7bddc42e71c3611` | no_explicit_target_year | null | [] |
| BaziQA | `072a4f22bb2dd07dd9e879e32fb69402ea0ad35cb2414e38c281905a62138d19` | no_explicit_target_year | null | [] |
| BaziQA | `c43aeb30195a49bb25cf6865c9832d801b63656d2760decd3cf523980f1a3e75` | no_explicit_target_year | null | [] |
| BaziQA | `ee92017fd64e4e05abda55f6ba38fc7eb8dc3b6e1987b8af1580786a1b81d04b` | no_explicit_target_year | null | [] |
| BaziQA | `b971bc8dbc58a8dc3522f30a28f8b709c3436272b15092fae79cd6bacb292833` | no_explicit_target_year | null | [] |

## 当前控制：宽松安慰剂（同源跨案例）与无盘对照

按28号M2，固定seed=20261020；捐赠池是本轮2025赛季纳入题所对应的同源案例。
以案例为单位做一对一错配，不同案例且出生不同；同案例的多题、多目标年共享同一捐赠者。
允许捐赠案例原题的目标年不同，原题文字、选项、答案映射与题目目标年保持原样；不跨来源。
实际构建两种对照的输入并检查结构，未送往模型/Agent，未排盘，未评分。结构通过不代表命理能力。
无盘对照仅提供原题与同样重排的选项，不提供源ID、结构化出生资料、盘、技能或规则。
原题文字本身如含出生提示，按裁定保持原题，因此无盘不等于清除了题面所有出生线索。

当前状态：available；安慰剂构建14题；无盘构建14题；推理调用0。

| 来源 | 题身份SHA256 | 原案例SHA256 | 捐赠案例SHA256 | 原题目标年 | 捐赠案例原题目标年 |
| --- | --- | --- | --- | ---: | --- |
| MingLi-Bench | `28c69bf996835433f4c11ee9173c48ca4810907c6465c30dca1522735edf4128` | `adcc402d9b36ac9eb01c622a67d52b8584d0aa3ca41999f1f74fafd54487f362` | `e55891995e64bd6c2d19d6e4b6d777441453e14b34a3dcfaa7d21361c41b1807` | 1980 | [2001, 2022] |
| MingLi-Bench | `a34184f22b3ff78d9aa8e117cc11906cfb8cd10b63839cd6186eced06bab9f5f` | `adcc402d9b36ac9eb01c622a67d52b8584d0aa3ca41999f1f74fafd54487f362` | `e55891995e64bd6c2d19d6e4b6d777441453e14b34a3dcfaa7d21361c41b1807` | 1993 | [2001, 2022] |
| MingLi-Bench | `c4b29fb216468c80854c776c663a72cbf6d0b2c6501a65afdefb95c3066e8802` | `1206150b1b2377993d7de65883c0f7b6b358f8f99d8443e81e6e628ce43ce5c6` | `adcc402d9b36ac9eb01c622a67d52b8584d0aa3ca41999f1f74fafd54487f362` | 2018 | [1980, 1993] |
| MingLi-Bench | `932ea6dedada9ef6f9f7667cccb3bcbe5999c25a184fa190b2b32572e7da8e84` | `91a9bc61ca24e21df6b01456d44f620c21ecea0f6bf1e047943e0d2055ee26e0` | `cc78f4d88cabefbcb99a2ed3f62d87edf065db9c80a50fa652b5b3662e68f335` | 2022 | [2021, 2024] |
| MingLi-Bench | `e00fb8971fe3ee0a1f413c935a32fd94e6cf9f2f4d62dfd070c0dd4f3dc370e9` | `e55891995e64bd6c2d19d6e4b6d777441453e14b34a3dcfaa7d21361c41b1807` | `1206150b1b2377993d7de65883c0f7b6b358f8f99d8443e81e6e628ce43ce5c6` | 2001 | [2018] |
| MingLi-Bench | `88a714d6e3d758ba5742c9f10696dc9428b9ca3ddf2a462157b4605256e3c5dc` | `e55891995e64bd6c2d19d6e4b6d777441453e14b34a3dcfaa7d21361c41b1807` | `1206150b1b2377993d7de65883c0f7b6b358f8f99d8443e81e6e628ce43ce5c6` | 2022 | [2018] |
| MingLi-Bench | `873c148bf90b5f266c084a835cd6b757dbb051fd735cc19633c5b3ea02f7da02` | `75aac7684729050a22897323aaa8f1583a205338625d9274b6ef894699ba2caa` | `91a9bc61ca24e21df6b01456d44f620c21ecea0f6bf1e047943e0d2055ee26e0` | 2004 | [2022] |
| MingLi-Bench | `a42fd86ad870e25aa29f999b278fd48c8c2c8f46f0cc6c95ae5b567d72fe2b2f` | `cc78f4d88cabefbcb99a2ed3f62d87edf065db9c80a50fa652b5b3662e68f335` | `75aac7684729050a22897323aaa8f1583a205338625d9274b6ef894699ba2caa` | 2021 | [2004] |
| MingLi-Bench | `e6fbf53ed8d60c52f02e08cf5005a946585be5eaa7e67fdd83510ba26b4d4a26` | `cc78f4d88cabefbcb99a2ed3f62d87edf065db9c80a50fa652b5b3662e68f335` | `75aac7684729050a22897323aaa8f1583a205338625d9274b6ef894699ba2caa` | 2024 | [2004] |
| BaziQA | `484cb80021ddf63974c796ebb4199403d33533ac4aac0c151bf629f9f7cbe1e9` | `72f868f61e1b4ccb0c25bac5ad930c328b2ac84709f2fd39f9373b67dba22cb8` | `6709015614cc88b6af03be209eccbfd608098a64cdd6709abf66990b97cee0d1` | 1980 | [2001, 2022] |
| BaziQA | `4b2cdd433a85a2c18e6d8c310a626c581f8802dca2c2673a31b26baa25f33351` | `72f868f61e1b4ccb0c25bac5ad930c328b2ac84709f2fd39f9373b67dba22cb8` | `6709015614cc88b6af03be209eccbfd608098a64cdd6709abf66990b97cee0d1` | 1993 | [2001, 2022] |
| BaziQA | `bee32fa733e414f9cfc1ef87a291d77dcc27880cb9e5f7e7d7bec1850d1e472a` | `6709015614cc88b6af03be209eccbfd608098a64cdd6709abf66990b97cee0d1` | `b936a8a347f4741c8bdd102164662dfecc8bdeb2d00dd1e6f8de44219a86e86c` | 2001 | [2024] |
| BaziQA | `3c2fc947abf8824b03df76cda08cc6ea769603d115faa16cd347b80881b22aa0` | `6709015614cc88b6af03be209eccbfd608098a64cdd6709abf66990b97cee0d1` | `b936a8a347f4741c8bdd102164662dfecc8bdeb2d00dd1e6f8de44219a86e86c` | 2022 | [2024] |
| BaziQA | `35750486bd46040f2de0b1f25ecb166d871a3888fd1e1fb7279e0914807003bf` | `b936a8a347f4741c8bdd102164662dfecc8bdeb2d00dd1e6f8de44219a86e86c` | `72f868f61e1b4ccb0c25bac5ad930c328b2ac84709f2fd39f9373b67dba22cb8` | 2024 | [1980, 1993] |

```json
{
  "control_name": "宽松安慰剂（同源跨案例）",
  "status": "available",
  "status_scope": "input_structure_only_not_chart_calculability",
  "seed": 20261020,
  "year_basis": "question_explicit_target_year_unchanged",
  "donor_pool": "eligible_2025_competition_subset_same_source_cases",
  "cross_target_year_allowed": true,
  "cross_source_allowed": false,
  "same_case_donor_consistent": true,
  "distinct_birth_required": true,
  "matching": "seeded_one_to_one_case_derangement",
  "questions": 14,
  "placebo_inputs_built": 14,
  "no_chart_inputs_built": 14,
  "checks_passed": {
    "birth_changed": 14,
    "question_unchanged": 14,
    "target_year_unchanged": 14,
    "same_displayed_question": 14,
    "no_chart_allowlist": 14,
    "answer_key_external": 14
  },
  "all_structural_checks_passed": true,
  "professional_corpus_scores": null,
  "real_model_requests": 0,
  "chart_calculations": 0,
  "inference_calls": 0
}
```


## 可计算性限制：结构可构建，不等于完整对照可排盘

时间先后元数据检查状态：metadata_temporal_order_checked。
捐赠出生年晚于保留题目目标年的题数：2。
按既有年度视图07-01北京时间正午采样，以全部允许[-14,+14]小时偏移判界，不选造时区。
确定出生晚于采样的配对不能当作有效年度排盘；本次仍保留全部14题，不隐性排题，不改seed或题目年份。
没有真正启动排盘preflight，也没有验证坐标、历法和分钟精度，不能把其余配对说成已可排盘。
待大脑决定是否显式增加donor出生不得晚于原题目标年的匹配约束，再在同一seed下重新生成一次；
未获指令板裁定前维持原匹配，不重抽、不改规则；若新约束不可行应明确拒绝。

```json
{
  "status": "metadata_temporal_order_checked",
  "contract": "e2-night28-fixed-donor-temporal-preflight-v1",
  "seed": 20261020,
  "sampling_basis": "annual_basis_question_year_July01_noon_UTC+08:00",
  "questions": 14,
  "donor_birth_year_after_target_year_count": 2,
  "donor_temporal_order_counts": {
    "birth_definitely_after_annual_snapshot": 2,
    "birth_definitely_not_after_annual_snapshot": 12
  },
  "original_temporal_order_counts": {
    "birth_definitely_not_after_annual_snapshot": 14
  },
  "pair_assignment_sha256": "d2e93d7f66756fd73c33338ae4a53bd099ee3168eff2643f53c93302c0603538",
  "pair_audit": [
    {
      "question_identity_sha256": "28c69bf996835433f4c11ee9173c48ca4810907c6465c30dca1522735edf4128",
      "case_identity_sha256": "adcc402d9b36ac9eb01c622a67d52b8584d0aa3ca41999f1f74fafd54487f362",
      "donor_case_identity_sha256": "e55891995e64bd6c2d19d6e4b6d777441453e14b34a3dcfaa7d21361c41b1807",
      "donor_birth_year_after_target_year": true,
      "donor_temporal_order": "birth_definitely_after_annual_snapshot",
      "original_temporal_order": "birth_definitely_not_after_annual_snapshot"
    },
    {
      "question_identity_sha256": "a34184f22b3ff78d9aa8e117cc11906cfb8cd10b63839cd6186eced06bab9f5f",
      "case_identity_sha256": "adcc402d9b36ac9eb01c622a67d52b8584d0aa3ca41999f1f74fafd54487f362",
      "donor_case_identity_sha256": "e55891995e64bd6c2d19d6e4b6d777441453e14b34a3dcfaa7d21361c41b1807",
      "donor_birth_year_after_target_year": false,
      "donor_temporal_order": "birth_definitely_not_after_annual_snapshot",
      "original_temporal_order": "birth_definitely_not_after_annual_snapshot"
    },
    {
      "question_identity_sha256": "c4b29fb216468c80854c776c663a72cbf6d0b2c6501a65afdefb95c3066e8802",
      "case_identity_sha256": "1206150b1b2377993d7de65883c0f7b6b358f8f99d8443e81e6e628ce43ce5c6",
      "donor_case_identity_sha256": "adcc402d9b36ac9eb01c622a67d52b8584d0aa3ca41999f1f74fafd54487f362",
      "donor_birth_year_after_target_year": false,
      "donor_temporal_order": "birth_definitely_not_after_annual_snapshot",
      "original_temporal_order": "birth_definitely_not_after_annual_snapshot"
    },
    {
      "question_identity_sha256": "932ea6dedada9ef6f9f7667cccb3bcbe5999c25a184fa190b2b32572e7da8e84",
      "case_identity_sha256": "91a9bc61ca24e21df6b01456d44f620c21ecea0f6bf1e047943e0d2055ee26e0",
      "donor_case_identity_sha256": "cc78f4d88cabefbcb99a2ed3f62d87edf065db9c80a50fa652b5b3662e68f335",
      "donor_birth_year_after_target_year": false,
      "donor_temporal_order": "birth_definitely_not_after_annual_snapshot",
      "original_temporal_order": "birth_definitely_not_after_annual_snapshot"
    },
    {
      "question_identity_sha256": "e00fb8971fe3ee0a1f413c935a32fd94e6cf9f2f4d62dfd070c0dd4f3dc370e9",
      "case_identity_sha256": "e55891995e64bd6c2d19d6e4b6d777441453e14b34a3dcfaa7d21361c41b1807",
      "donor_case_identity_sha256": "1206150b1b2377993d7de65883c0f7b6b358f8f99d8443e81e6e628ce43ce5c6",
      "donor_birth_year_after_target_year": false,
      "donor_temporal_order": "birth_definitely_not_after_annual_snapshot",
      "original_temporal_order": "birth_definitely_not_after_annual_snapshot"
    },
    {
      "question_identity_sha256": "88a714d6e3d758ba5742c9f10696dc9428b9ca3ddf2a462157b4605256e3c5dc",
      "case_identity_sha256": "e55891995e64bd6c2d19d6e4b6d777441453e14b34a3dcfaa7d21361c41b1807",
      "donor_case_identity_sha256": "1206150b1b2377993d7de65883c0f7b6b358f8f99d8443e81e6e628ce43ce5c6",
      "donor_birth_year_after_target_year": false,
      "donor_temporal_order": "birth_definitely_not_after_annual_snapshot",
      "original_temporal_order": "birth_definitely_not_after_annual_snapshot"
    },
    {
      "question_identity_sha256": "873c148bf90b5f266c084a835cd6b757dbb051fd735cc19633c5b3ea02f7da02",
      "case_identity_sha256": "75aac7684729050a22897323aaa8f1583a205338625d9274b6ef894699ba2caa",
      "donor_case_identity_sha256": "91a9bc61ca24e21df6b01456d44f620c21ecea0f6bf1e047943e0d2055ee26e0",
      "donor_birth_year_after_target_year": false,
      "donor_temporal_order": "birth_definitely_not_after_annual_snapshot",
      "original_temporal_order": "birth_definitely_not_after_annual_snapshot"
    },
    {
      "question_identity_sha256": "a42fd86ad870e25aa29f999b278fd48c8c2c8f46f0cc6c95ae5b567d72fe2b2f",
      "case_identity_sha256": "cc78f4d88cabefbcb99a2ed3f62d87edf065db9c80a50fa652b5b3662e68f335",
      "donor_case_identity_sha256": "75aac7684729050a22897323aaa8f1583a205338625d9274b6ef894699ba2caa",
      "donor_birth_year_after_target_year": false,
      "donor_temporal_order": "birth_definitely_not_after_annual_snapshot",
      "original_temporal_order": "birth_definitely_not_after_annual_snapshot"
    },
    {
      "question_identity_sha256": "e6fbf53ed8d60c52f02e08cf5005a946585be5eaa7e67fdd83510ba26b4d4a26",
      "case_identity_sha256": "cc78f4d88cabefbcb99a2ed3f62d87edf065db9c80a50fa652b5b3662e68f335",
      "donor_case_identity_sha256": "75aac7684729050a22897323aaa8f1583a205338625d9274b6ef894699ba2caa",
      "donor_birth_year_after_target_year": false,
      "donor_temporal_order": "birth_definitely_not_after_annual_snapshot",
      "original_temporal_order": "birth_definitely_not_after_annual_snapshot"
    },
    {
      "question_identity_sha256": "484cb80021ddf63974c796ebb4199403d33533ac4aac0c151bf629f9f7cbe1e9",
      "case_identity_sha256": "72f868f61e1b4ccb0c25bac5ad930c328b2ac84709f2fd39f9373b67dba22cb8",
      "donor_case_identity_sha256": "6709015614cc88b6af03be209eccbfd608098a64cdd6709abf66990b97cee0d1",
      "donor_birth_year_after_target_year": true,
      "donor_temporal_order": "birth_definitely_after_annual_snapshot",
      "original_temporal_order": "birth_definitely_not_after_annual_snapshot"
    },
    {
      "question_identity_sha256": "4b2cdd433a85a2c18e6d8c310a626c581f8802dca2c2673a31b26baa25f33351",
      "case_identity_sha256": "72f868f61e1b4ccb0c25bac5ad930c328b2ac84709f2fd39f9373b67dba22cb8",
      "donor_case_identity_sha256": "6709015614cc88b6af03be209eccbfd608098a64cdd6709abf66990b97cee0d1",
      "donor_birth_year_after_target_year": false,
      "donor_temporal_order": "birth_definitely_not_after_annual_snapshot",
      "original_temporal_order": "birth_definitely_not_after_annual_snapshot"
    },
    {
      "question_identity_sha256": "bee32fa733e414f9cfc1ef87a291d77dcc27880cb9e5f7e7d7bec1850d1e472a",
      "case_identity_sha256": "6709015614cc88b6af03be209eccbfd608098a64cdd6709abf66990b97cee0d1",
      "donor_case_identity_sha256": "b936a8a347f4741c8bdd102164662dfecc8bdeb2d00dd1e6f8de44219a86e86c",
      "donor_birth_year_after_target_year": false,
      "donor_temporal_order": "birth_definitely_not_after_annual_snapshot",
      "original_temporal_order": "birth_definitely_not_after_annual_snapshot"
    },
    {
      "question_identity_sha256": "3c2fc947abf8824b03df76cda08cc6ea769603d115faa16cd347b80881b22aa0",
      "case_identity_sha256": "6709015614cc88b6af03be209eccbfd608098a64cdd6709abf66990b97cee0d1",
      "donor_case_identity_sha256": "b936a8a347f4741c8bdd102164662dfecc8bdeb2d00dd1e6f8de44219a86e86c",
      "donor_birth_year_after_target_year": false,
      "donor_temporal_order": "birth_definitely_not_after_annual_snapshot",
      "original_temporal_order": "birth_definitely_not_after_annual_snapshot"
    },
    {
      "question_identity_sha256": "35750486bd46040f2de0b1f25ecb166d871a3888fd1e1fb7279e0914807003bf",
      "case_identity_sha256": "b936a8a347f4741c8bdd102164662dfecc8bdeb2d00dd1e6f8de44219a86e86c",
      "donor_case_identity_sha256": "72f868f61e1b4ccb0c25bac5ad930c328b2ac84709f2fd39f9373b67dba22cb8",
      "donor_birth_year_after_target_year": false,
      "donor_temporal_order": "birth_definitely_not_after_annual_snapshot",
      "original_temporal_order": "birth_definitely_not_after_annual_snapshot"
    }
  ],
  "matching_changed": false,
  "seed_changed": false,
  "retries": 0,
  "chart_calculations": 0,
  "real_model_requests": 0,
  "chart_preflight_executed": false,
  "complete_chart_calculability_established": false,
  "limits": [
    "宽松对照的输入结构可构建，不等于每题可排盘；不为修复时间先后关系而重抽、改年份或删题。",
    "仅按源出生元数据与既有07-01正午年度采样检查先后，不推造未确认地理、时区或缺失分钟。",
    "非阳历或缺字段题保持未判；没有输出任何出生数值、出生哈希、题面或答案。"
  ]
}
```

## 历史严格控制与当前界限

night24原文件不改写。此次另行重跑严格预检仅作历史对照，失败事实仍保留；M2明确授权跨目标年。
```json
{
  "seed": 20261019,
  "year_basis": "question_year",
  "actual_call_count": 1,
  "complete_batch_only": true,
  "retries": 0,
  "cross_source_fallback": false,
  "cross_year_fallback": false,
  "input_questions": 14,
  "eligible_questions": 14,
  "multi_year_case_count": 5,
  "multi_year_cases": [
    {
      "source": "BaziQA",
      "case_identity_sha256": "72f868f61e1b4ccb0c25bac5ad930c328b2ac84709f2fd39f9373b67dba22cb8",
      "target_years": [
        1980,
        1993
      ]
    },
    {
      "source": "BaziQA",
      "case_identity_sha256": "6709015614cc88b6af03be209eccbfd608098a64cdd6709abf66990b97cee0d1",
      "target_years": [
        2001,
        2022
      ]
    },
    {
      "source": "MingLi-Bench",
      "case_identity_sha256": "adcc402d9b36ac9eb01c622a67d52b8584d0aa3ca41999f1f74fafd54487f362",
      "target_years": [
        1980,
        1993
      ]
    },
    {
      "source": "MingLi-Bench",
      "case_identity_sha256": "e55891995e64bd6c2d19d6e4b6d777441453e14b34a3dcfaa7d21361c41b1807",
      "target_years": [
        2001,
        2022
      ]
    },
    {
      "source": "MingLi-Bench",
      "case_identity_sha256": "cc78f4d88cabefbcb99a2ed3f62d87edf065db9c80a50fa652b5b3662e68f335",
      "target_years": [
        2021,
        2024
      ]
    }
  ],
  "group_count": 13,
  "singleton_group_count": 12,
  "groups": [
    {
      "source": "BaziQA",
      "target_year": 1980,
      "case_count": 1,
      "distinct_birth_count": 1,
      "structurally_unmatchable": true
    },
    {
      "source": "BaziQA",
      "target_year": 1993,
      "case_count": 1,
      "distinct_birth_count": 1,
      "structurally_unmatchable": true
    },
    {
      "source": "BaziQA",
      "target_year": 2001,
      "case_count": 1,
      "distinct_birth_count": 1,
      "structurally_unmatchable": true
    },
    {
      "source": "BaziQA",
      "target_year": 2022,
      "case_count": 1,
      "distinct_birth_count": 1,
      "structurally_unmatchable": true
    },
    {
      "source": "BaziQA",
      "target_year": 2024,
      "case_count": 1,
      "distinct_birth_count": 1,
      "structurally_unmatchable": true
    },
    {
      "source": "MingLi-Bench",
      "target_year": 1980,
      "case_count": 1,
      "distinct_birth_count": 1,
      "structurally_unmatchable": true
    },
    {
      "source": "MingLi-Bench",
      "target_year": 1993,
      "case_count": 1,
      "distinct_birth_count": 1,
      "structurally_unmatchable": true
    },
    {
      "source": "MingLi-Bench",
      "target_year": 2001,
      "case_count": 1,
      "distinct_birth_count": 1,
      "structurally_unmatchable": true
    },
    {
      "source": "MingLi-Bench",
      "target_year": 2004,
      "case_count": 1,
      "distinct_birth_count": 1,
      "structurally_unmatchable": true
    },
    {
      "source": "MingLi-Bench",
      "target_year": 2018,
      "case_count": 1,
      "distinct_birth_count": 1,
      "structurally_unmatchable": true
    },
    {
      "source": "MingLi-Bench",
      "target_year": 2021,
      "case_count": 1,
      "distinct_birth_count": 1,
      "structurally_unmatchable": true
    },
    {
      "source": "MingLi-Bench",
      "target_year": 2022,
      "case_count": 2,
      "distinct_birth_count": 2,
      "structurally_unmatchable": false
    },
    {
      "source": "MingLi-Bench",
      "target_year": 2024,
      "case_count": 1,
      "distinct_birth_count": 1,
      "structurally_unmatchable": true
    }
  ],
  "status": "unavailable",
  "error_code": "placebo_case_spans_question_years_cannot_preserve_one_donor",
  "placebo_questions": 0,
  "changed_births_count": 0
}
```

复跑：`python -m mingjing_core.adapters.charts.benchmarks.night28_audit --mode scripted --mingli-root private/e2-sources/mingli --baziqa-root private/e2-sources/baziqa --output docs/v4/evidence/P8/e2-night28-controls-2026-10-20.json`。

待核：经纬度、历史时区与分钟精度仍需输入预检；本演练不构造未知资料，不证明排盘正确或预测有效。
真实专业题库评分留给主线经用户/大脑另行授权，本分支无真实运行入口。
新下载、服务器请求、模型请求、排盘、专业评分均为0；原文、答案及出生不进入证据。
