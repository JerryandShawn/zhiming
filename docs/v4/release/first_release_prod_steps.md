# 首发生产分步脚本（R51）

由 `first_release_prod_steps_gen.py` 从执行单（sha256 `83fe161737488b8e756989afa7cfb2e6929661c4efc9f07dcfaaa4cf017a0a8d`）生成，脚本在 `private/fr-prod-next-draft/`。19 个 bash 块逐字节拼回与执行单一致，顺序不变；pip 和 D2–D4 用 start_step/check_step 后台跑（Python 正文逐字不变，只从 stdin 改为落盘后执行）。

| 步骤 | 执行单块 | 对照 | sha256 前 12 位 |
| --- | --- | --- | --- |
| p01-readonly | 1 | 一致 | `97c40a6a823f` |
| p02-admin | 2 | 一致 | `a5dab6462de3` |
| p03a-extract | 3 | 一致 | `4855eae1530f` |
| p03b-install-start | 3 | 一致 | `a0d88eb02529` |
| p03c-install-status | — | 后台状态查询 | `bc4164d78ab6` |
| p03d-tokenizer | 3 | 一致 | `86670b89292c` |
| p04a-precheck | — | 只读：确认线上仍是 7dbc951（v72）、旧 wrapper 符合 D1 前提 | `5e40a2db40bb` |
| p04b-d1-maintenance | 4 | 一致 | `9708a2fb15ac` |
| p04c-gate-503 | — | 只读：D1 的公网维护 503、遗留进程数 | `d32b296a19f0` |
| p05-context | 5 | 一致 | `b37b08b02f23` |
| p06a-d2-start | 6 | 一致 | `160a0395f26d` |
| p06b-d2-status | — | 后台状态查询 | `3df05019d219` |
| p07a-d3-start | 7 | 一致 | `52fa8c6cb75e` |
| p07b-d3-status | — | 后台状态查询 | `85ec4fc2a8fd` |
| p08a-d4-start | 8 | 一致 | `4bbbcf70de71` |
| p08b-d4-status | — | 后台状态查询 | `57eb6d4e7ee3` |
| p09-d5-exchange | 9 | 一致 | `ecd270f876d1` |
| p09c-writer-harden | 10 | 一致 | `b00a54f6bcee` |
| p10-d5-assets | 11 | 一致 | `ad9731977f2a` |
| p11-d6-preopen | 12 | 一致 | `50732d5c173e` |
| p12-d6-writer | 13 | 一致 | `c27b70435e77` |
| p13-d7-open | 14 | 一致 | `a2aac1131d3a` |
| p14-d7-timer-state | 15 | 一致 | `12633af0cf2a` |
| p14b-d7-timer-start | — | D7 报告 timer 按 D1 原 active 状态恢复；发送另需 `timer-order.json` | `5c6961646c61` |
| p15-final-readonly | — | 只读：D8 最终核对 | `0ca8a1ff1ba8` |
| p16-postopen-close | — | 开门后止损：恢复两道维护门、停服务、导出隐私并 pg_dump（输出按 UTC 时间命名，失败可重发）；发送另需 `postopen-close-order.json`，不受窗口限制 | `7665717bb14b` |
| r01-rollback-database | 16 | 一致 | `16f40087c531` |
| r02-rollback-files | 17 | 一致 | `a757022d70a4` |
| r02b-writer-restore | 18 | 一致 | `7469b18dd217` |
| r03-rollback-verify | 19 | 一致 | `4a4fc439b970` |

## 附录：回滚后重新开门（R59，不在默认流程）

`r04-reopen-after-rollback.sh`，sha256 `dc3657e2dcb49690de39cfb5a38061ac2dd8baf66fc84319adbbe83b875a49de`。不改执行单。只有用户或大脑当次明确下令才执行：发送脚本另外要求 `reopen-order.json`，默认流程不会带上它。顺序：r03 通过 → 开库连接 → 启动 7dbc951 Web → 门内健康检查 → 读 timer 原状态 → 去维护标记 → 启动飞书并确认 active → timer 按原状态恢复。飞书走外连长连接，不经过 nginx，维护门挡不住，所以和 D7 一样在去维护标记之后才启动。下这个令同时表示接受到期报告恢复投递；不接受就改用 `r04-reopen-timer-held.sh`（sha256 `24fa474e052f73f7d11247a329a62a2d3dd09f0777fad1707e352f67f96193db`），它只少恢复 timer 这一行。任何一步失败即停；健康检查失败时维护页保持，只有 Web 在门内运行，不自动停，等指令。不删除任何发布、备份或库。

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
 except (urllib.error.URLError,OSError):
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
| D3/D4 真实失败、未对调（无 `exchange-receipt.json`、无 `opened.json`；不是上面的 autovacuum 撞车） | 原 LIVE 未动但仍是 D2 留下的 datallowconn=false；三 service/timer 按 D1 停；NEW 保留关闭 | 跳过 r01（它要求 exchange 回执）：`r02-rollback-files` → `r02b-writer-restore`（role-before 不存在，只核 LIVE 元数据）→ `r03-rollback-verify` → 写 `reopen-order.json` → `r04-reopen-after-rollback`（或 `r04-reopen-timer-held`）。r04 是唯一把原 LIVE 恢复为 datallowconn=true 的步骤，且在启动旧 Web 之前；禁止手工启动旧 Web 或另写 preexchange-* 脚本 |
| D5 首检 409 | 未改名 | `c-wait-zero` → `p09-d5-exchange 2` |
| D5 尾 418 | 已对调，无 receipt | `c-d5-tail-start` → `c-d5-tail-status` |
| D5 资产 432 | 无变化 | `c-wait-zero` → `p10-d5-assets 2` |
| D6 497 | 无变化 | `c-wait-zero` → `p11-d6-preopen 2` |
| D6 521 | 无变化 | `c-wait-zero` → `p12-d6-writer 2` |
| D6 尾 530 | 回执已写，LIVE 已关 | `c-wait-zero` → 继续 `p13-d7-open` |
| D7 550 | 无 `opened.json`，标记还在，库未开 | `c-wait-zero` → `p13-d7-open 2` |
| p13 在写 `opened.json` 之后失败（Web 健康或 30 秒稳定、飞书 30 秒稳定） | 已过开门点，禁止 R1；Web 段失败时 nginx 标记仍在、公网仍维护；飞书段失败时公网已开 | 不重发 p13；当次写 `postopen-close-order.json` → `p16-postopen-close`，然后找大脑 |
| `p16-postopen-close` 任何失败 | 恢复门与停服务部分可重复执行；本次 `postopen-<UTC>-*` 文件可能部分写出 | 可直接重发 `p16-postopen-close 2`（attempt 递增）：nginx 与 writer 标记已在则保留，服务已停则只复核，输出换新的 UTC 时间名，旧尝试文件保留不覆盖 |
| R1 598 | 无状态变化 | `c-wait-zero` → `r01-rollback-database 2` |
| R1 613（LIVE、RB 两处） | RB 已恢复已关，未对调 | `c-r1-after-restore-start` → `c-r1-after-restore-status` |
| p09c 任何失败 | 已对调；role-before 可能已写，角色可能已改 | 不重跑，走 R1：r01 → r02 → r02b → r03 |
| r02b 失败 | 门内，角色可能未恢复 | 撞 autovacuum 用 `c-wait-zero` 后 `r02b-writer-restore 2`；其他失败保持维护，找大脑 |
| R3 646 | 库未开 | `c-wait-zero` → `r03-rollback-verify 2` |
| R3 652 | 库已关，无回执 | `c-wait-zero` → `r03-rollback-verify 2` |
| r04 第一段 | 库未开 | `c-wait-zero` → `r04-reopen-after-rollback 2`（或 `r04-reopen-timer-held 2`），`reopen-order.json` 仍要 |

表中行号是 17ef7a87 版执行单的行号，之后的版本有增删，以块和步骤名为准。D5 尾没有补回执时不能进 R1：R1 要求 `exchange-receipt.json`，先跑 `c-d5-tail`。`c-wait-zero` 要求库已关闭，只用于 D2 关库之后。

## 附录：发送门（first_release_prod_send.py）

除 `p04a-readonly` 外，每一步都要 `window-go.json`，且其中 `candidate`、`operation` 必须是本单的 bf6e0bbc… 与 501d95670be144a3；`p*` 步骤还要求当前北京时间在 `not_before`–`latest_end` 内（两者须带 +08:00），`r0*`、`c-*` 和 `p16-postopen-close` 不受时间窗限制；`p14-d7-timer-state`、`p14b-d7-timer-start`、`p15-final-readonly` 在 p13 已有成功回执后也免时间检查（candidate/operation 仍校验）。`p04a-readonly` 作为 p04b 的前置时，除 exit 0 外还要从其最新成功日志解析出 JSON 报告且 `other_problems == []`，取不到报告即拒绝。顺序门：发某步前，其前置步骤须有本地回执 `<步骤>.json` 或 `<步骤>.<attempt>.json`，exit_code=0 且 candidate/operation 相符；`-status` 步骤还要求保存的日志最后一行是 `STEP_OK`（只回 STEP_RUNNING 不算完成）。前置表按 R67 续跑表给出替代：p07a 可由 p06b、`c-d2-mid-status` 或 `c-d2-tail-status` 满足；p08a 可由 p07b 或 `c-d3-tail-status`；p09 要 p08a 已发且（p08b 或 `c-wait-zero`）成功；p09c 可由 p09 或 `c-d5-tail-status`。主要前置：p04b 要 p01、p02、p03a、p03d、p04a-precheck、p04a-readonly；p05 要 p04c；p13 要 p11 且（p12 或 `c-wait-zero`，对应 D6 尾 530 撞车）；p14b 要 p13、p14；回滚链 r02b 要 r02、r03 要 r02b、r04 要 r03（r02 不要求 r01，供未对调的回滚路线使用）。`p14b-d7-timer-start` 另需当次 `timer-order.json`（表示接受到期报告恢复投递），`p16-postopen-close` 另需当次 `postopen-close-order.json`；两份令与 `reopen-order.json` 一样只看是否存在、不自动消耗。

`p04a-readonly` 只读，不写库、不写文件、不打印秘密，发送门是 `readonly-order.json`，不看 `window-go.json`。它在 D1 之前核 writer 属性、库和 schema 权限、属主对象、两个 env 文件、writer DSN 的字段形状和环境变量名；`expected_for_p09c` 列 p09c 会修的项，`other_problems` 非空就停，找大脑。

| 脚本 | sha256 |
| --- | --- |
| `c-wait-zero` | `e15f1d1224e983edc52a56cbbd00461349547d280323cf96960ab50dae02609c` |
| `c-d2-rerun-prep` | `7c73ce1452708b11d155d17004df2e7ea1d0d1b114583a351c648d335330802d` |
| `c-d3-rerun-prep` | `7b664ca0877d752200576a4dc99a510b1af77f55549f6389d38c4f91aa5deb0f` |
| `c-d4-rerun-prep` | `a55943ce007fbd6837457f830c8a4792e3bd8c1ab679fed3b1828427e7d66ed9` |
| `c-d2-mid-start` | `bbaded228f92a116750ff7465e90639749d556bf9108bf9b867a91cd5b0d9f6b` |
| `c-d2-mid-status` | `fc95fefde6956c520c20e75be7aa4c4b3c66aa055da2d89c511c1188549e53a7` |
| `c-d2-tail-start` | `354dabcedcf681e0d85ec8e76e311cbebc00984844ff787641df102daa169b4b` |
| `c-d2-tail-status` | `4f7d4987ee3979eeb22e133ec5fcab0d8c7849ff98b9907a8d5f536ee74a27b4` |
| `c-d3-tail-start` | `90366b814b523a2c2eca01c2aaa724d495c310aed27d8d9ad7b681ce76e7d156` |
| `c-d3-tail-status` | `470cec14bc41fd2ab97876387642192265ebb4036449d74ce81417c1aa44f89b` |
| `c-d5-tail-start` | `ac54bcb47cc3c88ad6f23a0f94bdf53b22c0cc1d9056110e475b7fd1dc3518d7` |
| `c-d5-tail-status` | `e2b2fd2ca388e290d48dd6bf6a9b344831debf1554c7bf16af3f8fb5430feddd` |
| `c-r1-after-restore-start` | `d9d921cc364b1d03353a43819892802664f9c0bdca3c89b9cbd751f55bca6cb0` |
| `c-r1-after-restore-status` | `f0cb9f34232458ca011c4a80388a59d9b1a6b63e147a93468ed4607d9b0130cb` |
| `p04a-readonly` | `d5cbcce04d16fdf4b080a996443db28fda98562b68e26b9f9c293bf1c73eef06` |
