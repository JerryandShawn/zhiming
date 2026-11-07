# 首发生产分步脚本（R51）

由 `first_release_prod_steps_gen.py` 从执行单（sha256 `3ce073b27fff458695b64e11f9927e4ad92924235b9f6cfe1ba7acfa2d64a316`）生成，脚本在 `private/fr-prod-501d95670be144a3/`。19 个 bash 块逐字节拼回与执行单一致，顺序不变；pip 和 D2–D4 用 start_step/check_step 后台跑（Python 正文逐字不变，只从 stdin 改为落盘后执行）。

| 步骤 | 执行单块 | 对照 | sha256 前 12 位 |
| --- | --- | --- | --- |
| p01-readonly | 1 | 一致 | `7b763aec47a3` |
| p02-admin | 2 | 一致 | `22566e8b32cb` |
| p03a-extract | 3 | 一致 | `60e43ec747a7` |
| p03b-install-start | 3 | 一致 | `cbb36319d79c` |
| p03c-install-status | — | 后台状态查询 | `1bbe71d70b23` |
| p03d-tokenizer | 3 | 一致 | `40979347d6b5` |
| p04a-precheck | — | 只读：确认线上仍是 7dbc951（v72）、旧 wrapper 符合 D1 前提 | `88301724b651` |
| p04b-d1-maintenance | 4 | 一致 | `faad7cf3aaf2` |
| p04c-gate-503 | — | 只读：D1 的公网维护 503、遗留进程数 | `7977d66bb1a1` |
| p05-context | 5 | 一致 | `abae7a0982cf` |
| p06a-d2-start | 6 | 一致 | `dd730e36c468` |
| p06b-d2-status | — | 后台状态查询 | `e35be5ac1215` |
| p07a-d3-start | 7 | 一致 | `852a34a3b1ed` |
| p07b-d3-status | — | 后台状态查询 | `679a6423226e` |
| p08a-d4-start | 8 | 一致 | `262358085d64` |
| p08b-d4-status | — | 后台状态查询 | `e523d49479a0` |
| p09-d5-exchange | 9 | 一致 | `c7a32826e17e` |
| p09c-writer-harden | 10 | 一致 | `da0ac4a9eab8` |
| p10-d5-assets | 11 | 一致 | `e4decc0ef266` |
| p11-d6-preopen | 12 | 一致 | `a411d06d2cdd` |
| p12-d6-writer | 13 | 一致 | `d49594792d87` |
| p13-d7-open | 14 | 一致 | `b7428a89f17b` |
| p14-d7-timer-state | 15 | 一致 | `3a31c3b2f55c` |
| p15-final-readonly | — | 只读：D8 最终核对 | `5d32b88e4c4c` |
| r01-rollback-database | 16 | 一致 | `612d061ad4ca` |
| r02-rollback-files | 17 | 一致 | `d105eeea821c` |
| r02b-writer-restore | 18 | 一致 | `2f2380c5098c` |
| r03-rollback-verify | 19 | 一致 | `d1ab7063bc3b` |

## 附录：回滚后重新开门（R59，不在默认流程）

`r04-reopen-after-rollback.sh`，sha256 `57ad0f09dabf6da8e856426546f51feb7b27f47748670d02d8b2027200fae8c9`。不改执行单。只有用户或大脑当次明确下令才执行：发送脚本另外要求 `reopen-order.json`，默认流程不会带上它。顺序：r03 通过 → 开库连接 → 启动 7dbc951 Web → 门内健康检查 → 读 timer 原状态 → 去维护标记 → 启动飞书并确认 active → timer 按原状态恢复。飞书走外连长连接，不经过 nginx，维护门挡不住，所以和 D7 一样在去维护标记之后才启动。下这个令同时表示接受到期报告恢复投递；不接受就改用 `r04-reopen-timer-held.sh`（sha256 `b4307ae33c56e58ca4b929383af74b8358b2f20344a33613fa7fb80397322797`），它只少恢复 timer 这一行。任何一步失败即停；健康检查失败时维护页保持，只有 Web 在门内运行，不自动停，等指令。不删除任何发布、备份或库。

```bash
test ! -e "$FR_OP/opened.json"
test -f "$FR_OP/rollback-old-runtime.json"
test -f /www/wwwroot/p-acme/core-maintenance.flag
"$FR_PY" -I - "$FR_OP" <<'PY'
import sys
sys.path.insert(0,sys.argv[1]);from context import *
v=read('rollback-old-runtime.json')
assert v['old_sha']=='7dbc951eaffebd3d812169865eaefcde16a00ed9' and v['schema_readonly_verified'] and v['closed']
assert read('role-restored.json')['verified'] is True
with admin() as c:
 if (OP/'role-before.json').is_file():
  before=read('role-before.json')
  assert c.execute('SELECT rolinherit FROM pg_roles WHERE rolname=%s',(before['writer'],)).fetchone()['rolinherit'] is before['rolinherit']
 assert semantic(capture(c,LIVE))==semantic(read('database-before.json'))
 zero(c,LIVE);allow(c,LIVE,True)
print('R59: live database admission opened behind the public maintenance gate')
PY
systemctl start mingjingtai.service
systemctl is-active --quiet mingjingtai.service
"$FR_PY" -I - "$FR_OP" <<'PY'
import sys,time,urllib.error,urllib.request
sys.path.insert(0,sys.argv[1]);from context import *
env={}
for path in ('/root/.hermes/.env','/root/zhiming-core-secrets/live-runtime.env'):
 env.update(private_env(path))
request=urllib.request.Request('http://127.0.0.1:8787/api/health',headers={'X-Token':env['MINGJING_TOKEN']})
env=None;body=None
for _ in range(30):
 try:
  with urllib.request.urlopen(request,timeout=5) as response:
   assert response.status==200;body=json.load(response);break
 except (urllib.error.URLError,ConnectionError):
  time.sleep(2)
assert body and body['ok'] is True and body['database']=='postgresql' and body['context_version']=='core3.0','R59 health failed; maintenance retained'
print('R59: old web healthy behind the public maintenance gate; token output=0')
PY
"$FR_PY" -I - "$FR_OP/units-before.json" > "$FR_OP/r04-timer-state.txt" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))['zhiming-core-reports.timer']['ActiveState'])
PY
rm /www/wwwroot/p-acme/core-maintenance.flag
systemctl start zhiming-core-feishu.service
systemctl is-active --quiet zhiming-core-feishu.service
if test "$(cat "$FR_OP/r04-timer-state.txt")" = active; then systemctl start zhiming-core-reports.timer; fi
echo "R59: maintenance removed; report timer restored to $(cat "$FR_OP/r04-timer-state.txt")"
```

## 附录：撞上 autovacuum 后的续跑（R67，不在默认流程）

`c-` 开头的脚本默认发不出去：除 `window-go.json` 外，还要当次的 `continue-order.json`，内容 `{"script": "<下表脚本名>"}`；发送脚本在连接前把它改名为 `continue-order.used-*`，一份令只用一次。判定仍是 n==0：每次等待最多 5 分钟，发现 autovacuum worker 以外的后端立刻停，到时限也停，维护页保持。回执字段和原 D 块相同，仍是独占写；重复执行不会覆盖已有回执。文件只移开不删除。不重新改名、不重新 apply；`c-r1-after-restore` 里的对调是 R1 原块还没执行的那一步。

发送命令都是 `python docs/v4/release/first_release_prod_send.py <步骤> <attempt>`，下表 attempt 写 2，再次重发递增。

| 撞车位置（执行单行） | 状态 | 处置 |
| --- | --- | --- |
| D2 首检 302 | LIVE 开着，只写了 `central-before.json` | `c-d2-rerun-prep` → `p06a-d2-start 2` → `p06b-d2-status 2` |
| D2 关库 312 | 四份 before 已写，LIVE 已关，原块连不上 | `c-d2-mid-start` → `c-d2-mid-status` |
| `c-d2-mid` 在 dump 写完后失败（等待超时或出现别的后端） | dump 已有，无 receipt，`c-d2-tail` 会拒绝 | 停，保持维护，找大脑。不加脚本；还没到 D5，原库没动，放弃这次窗口是安全的 |
| D2 尾 321 | dump 已写，无 receipt | `c-d2-tail-start` → `c-d2-tail-status` |
| D3 首检 335 | 无变化 | `c-d3-rerun-prep` → `p07a-d3-start 2` → `p07b-d3-status 2` |
| D3 尾 349 | NEW 已恢复已关，无 receipt | `c-d3-tail-start` → `c-d3-tail-status` |
| D4 首检 368 | 无变化 | `c-d4-rerun-prep` → `p08a-d4-start 2` → `p08b-d4-status 2` |
| D4 尾 393 | 回执已写，两库已关 | `c-wait-zero` → 继续 `p09-d5-exchange` |
| D5 首检 409 | 未改名 | `c-wait-zero` → `p09-d5-exchange 2` |
| D5 尾 418 | 已对调，无 receipt | `c-d5-tail-start` → `c-d5-tail-status` |
| D5 资产 432 | 无变化 | `c-wait-zero` → `p10-d5-assets 2` |
| D6 497 | 无变化 | `c-wait-zero` → `p11-d6-preopen 2` |
| D6 521 | 无变化 | `c-wait-zero` → `p12-d6-writer 2` |
| D6 尾 530 | 回执已写，LIVE 已关 | `c-wait-zero` → 继续 `p13-d7-open` |
| D7 550 | 无 `opened.json`，标记还在，库未开 | `c-wait-zero` → `p13-d7-open 2` |
| R1 598 | 无状态变化 | `c-wait-zero` → `r01-rollback-database 2` |
| R1 613（LIVE、RB 两处） | RB 已恢复已关，未对调 | `c-r1-after-restore-start` → `c-r1-after-restore-status` |
| p09c 任何失败 | 已对调；role-before 可能已写，角色可能已改 | 不重跑，走 R1：r01 → r02 → r02b → r03 |
| r02b 失败 | 门内，角色可能未恢复 | 撞 autovacuum 用 `c-wait-zero` 后 `r02b-writer-restore 2`；其他失败保持维护，找大脑 |
| R3 646 | 库未开 | `c-wait-zero` → `r03-rollback-verify 2` |
| R3 652 | 库已关，无回执 | `c-wait-zero` → `r03-rollback-verify 2` |
| r04 第一段 | 库未开 | `c-wait-zero` → `r04-reopen-after-rollback 2`（或 `r04-reopen-timer-held 2`），`reopen-order.json` 仍要 |

表中行号是 17ef7a87 版执行单的行号，之后的版本有增删，以块和步骤名为准。D5 尾没有补回执时不能进 R1：R1 要求 `exchange-receipt.json`，先跑 `c-d5-tail`。`c-wait-zero` 要求库已关闭，只用于 D2 关库之后。

`p04a-readonly` 只读，不写库、不写文件、不打印秘密，发送门是 `readonly-order.json`，不看 `window-go.json`。它在 D1 之前核 writer 属性、库和 schema 权限、属主对象、两个 env 文件、writer DSN 的字段形状和环境变量名；`expected_for_p09c` 列 p09c 会修的项，`other_problems` 非空就停，找大脑。

| 脚本 | sha256 |
| --- | --- |
| `c-wait-zero` | `81b52ddcd33098a1e3b416206975aefe2eb78b40acdb8ea10ec96334879880a0` |
| `c-d2-rerun-prep` | `761583698e86d1e45d7b4c45c9e582d317122b7dca86154306ae8fb67bdb2141` |
| `c-d3-rerun-prep` | `681bd4006d63b7fc8de997328faa04e297594a1c777b7ab4fe28c9804abef25f` |
| `c-d4-rerun-prep` | `4213ec1c305743f77495f6e4624b1ecd704fd7d0431321370931b93056679f43` |
| `c-d2-mid-start` | `663a1f927bcebb638e0b8e2dced48b20a9d6f5f68940b997544f3c1efcf8369e` |
| `c-d2-mid-status` | `7cc1837c4824037d5e6caf687546c2a8c993e305e77fba0f9000ac282b600d96` |
| `c-d2-tail-start` | `87b0415a7b189716c393818b31748672f16c1e8a491dd559959cb3efaa48b299` |
| `c-d2-tail-status` | `73d6509030034756470174d580d7ab7586ea81f046595e39c43fbae3d52891d4` |
| `c-d3-tail-start` | `52995a5718ee9c8245a9010c9c119888cb93640d567b506b882fe3b262d29d7b` |
| `c-d3-tail-status` | `77c8f13fda533663afaecce2d9054a7d599331e98ded185b54d756381443e0ab` |
| `c-d5-tail-start` | `d9a4908ba3d7ad60c4fe4646ea44d0a73e3b59c9546f9e4fb90e8643937f81df` |
| `c-d5-tail-status` | `5756c3a9efbc24ec51be97246353589f3039d5e2e35962750cb8eeaf9042bcd7` |
| `c-r1-after-restore-start` | `016e2a6d983d6c5ed46a0f5330619756422812504612927d53baaf24dc6d154a` |
| `c-r1-after-restore-status` | `6afe8ed23d9917faad97fab7a18805978b4075e0906f9ddb68445b3594fe93f2` |
| `p04a-readonly` | `43ecca8fbcaa7202486193dbb7e353e5e2aace6b151ad77de02c07dd20e90d37` |
