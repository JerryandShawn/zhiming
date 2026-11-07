# 首发生产分步脚本（R51）

由 `first_release_prod_steps_gen.py` 从执行单（sha256 `afe54b29d8737ad574f05291836982bf6e02f03fda9cfc1bb8f43649e7bc996f`）生成，脚本在 `private/fr-prod-c24caad7ae184faf/`。19 个 bash 块逐字节拼回与执行单一致，顺序不变；pip 和 D2–D4 用 start_step/check_step 后台跑（Python 正文逐字不变，只从 stdin 改为落盘后执行）。

| 步骤 | 执行单块 | 对照 | sha256 前 12 位 |
| --- | --- | --- | --- |
| p01-readonly | 1 | 一致 | `d2f5f2066d5e` |
| p02-admin | 2 | 一致 | `2c33dc510ae9` |
| p03a-extract | 3 | 一致 | `a84e7de03231` |
| p03b-install-start | 3 | 一致 | `54d5bd524982` |
| p03c-install-status | — | 后台状态查询 | `f6c57eefcf0d` |
| p03d-tokenizer | 3 | 一致 | `2ceaa37b1a9b` |
| p04a-precheck | — | 只读：确认线上仍是 7dbc951（v72）、旧 wrapper 符合 D1 前提 | `a5c18d2b9b5e` |
| p04b-d1-maintenance | 4 | 一致 | `1998f689ea21` |
| p04c-gate-503 | — | 只读：D1 的公网维护 503、遗留进程数 | `cf82758b3765` |
| p05-context | 5 | 一致 | `cdae0c63d3bd` |
| p06a-d2-start | 6 | 一致 | `74cc302b10da` |
| p06b-d2-status | — | 后台状态查询 | `d37dd0d0076f` |
| p07a-d3-start | 7 | 一致 | `2598fa054f56` |
| p07b-d3-status | — | 后台状态查询 | `c43fa43d4cb4` |
| p08a-d4-start | 8 | 一致 | `4efdc9edaa75` |
| p08b-d4-status | — | 后台状态查询 | `c5e79f7853d8` |
| p09-d5-exchange | 9 | 一致 | `f04c280ebe64` |
| p09c-writer-harden | 10 | 一致 | `e65464afc66c` |
| p10-d5-assets | 11 | 一致 | `cf7ec384fa2f` |
| p11-d6-preopen | 12 | 一致 | `5f3181e85536` |
| p12-d6-writer | 13 | 一致 | `f66f098d0d95` |
| p13-d7-open | 14 | 一致 | `59ba37e6beaa` |
| p14-d7-timer-state | 15 | 一致 | `f4cd399af14d` |
| p15-final-readonly | — | 只读：D8 最终核对 | `663cfeb4e6a4` |
| r01-rollback-database | 16 | 一致 | `96142b79f9ad` |
| r02-rollback-files | 17 | 一致 | `e3e27c43b717` |
| r02b-writer-restore | 18 | 一致 | `ec9d0c65a9b4` |
| r03-rollback-verify | 19 | 一致 | `f84e55f1b2ff` |

## 附录：回滚后重新开门（R59，不在默认流程）

`r04-reopen-after-rollback.sh`，sha256 `1f2b9b85e97eb65f06276cb5e2c9fb7a4d395dd40766139114eb0a0210c36bdb`。不改执行单。只有用户或大脑当次明确下令才执行：发送脚本另外要求 `reopen-order.json`，默认流程不会带上它。顺序：r03 通过 → 开库连接 → 启动 7dbc951 Web → 门内健康检查 → 读 timer 原状态 → 去维护标记 → 启动飞书并确认 active → timer 按原状态恢复。飞书走外连长连接，不经过 nginx，维护门挡不住，所以和 D7 一样在去维护标记之后才启动。下这个令同时表示接受到期报告恢复投递；不接受就改用 `r04-reopen-timer-held.sh`（sha256 `a80b01f8f6b6ca34c188db4ae0b6b7478cfee70de3ca6bcb057b2120ef046c21`），它只少恢复 timer 这一行。任何一步失败即停；健康检查失败时维护页保持，只有 Web 在门内运行，不自动停，等指令。不删除任何发布、备份或库。

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
| `c-wait-zero` | `5e665f7caeaa8db5f38e5fa336547229c445cfbc874deb040088d37156866504` |
| `c-d2-rerun-prep` | `ef090580a17f930317d330184e3167185326b8d6c193d660d21362e5e7f37f74` |
| `c-d3-rerun-prep` | `9eb5bfbf71ad8039d4ede8eb91f5b118d54d68ecee81d4db0ec934dc93e23890` |
| `c-d4-rerun-prep` | `c81bf15279d821e8d0f385c2ed533d1fc707dfdd90d5bbeb53ddcc9b59d49a36` |
| `c-d2-mid-start` | `7e9919a6dc78247ef0c03468c00a51d354c199a362a783e747684716d4d4fef0` |
| `c-d2-mid-status` | `afddc826288702793b71030358a259e553155599c175b445f5626ac223fdf914` |
| `c-d2-tail-start` | `494c05df2d1c871f17c4928be7963cf47175fe02a75f23855ad327b8bb02cc86` |
| `c-d2-tail-status` | `55e11a373902bee10441c8acf73a9cb11f7eb5f9364933617b72ac5bb312734f` |
| `c-d3-tail-start` | `6b133c2e1e153acc65a548d6a917db37bf479191a49bae4e6d2b4acaa0d0e646` |
| `c-d3-tail-status` | `b1026592f81b3580e589f7a9d539d86e1622909420cc88ea6bf9bc49dfbd49fe` |
| `c-d5-tail-start` | `1dfa75e58507f2dd41358a729490127db33ada60fc65d5d84424e8151af4b073` |
| `c-d5-tail-status` | `c7b26c394f008a8f5f1d76e47a973c371aec2f9fbfe086625697a8cd7b9fb9dd` |
| `c-r1-after-restore-start` | `9d4f4c204d44c44ead859fdb523dc080eb13d21b8e1a84554e3e11799b03007f` |
| `c-r1-after-restore-status` | `6b38890e3e6762418db40078c0bc0ef043e59b49f1ff273ef6427a23ccbfa51b` |
| `p04a-readonly` | `b6c9cd45e4263831dba825d81951dddfae18997e4fa63bebdae9b51f7b618c02` |
