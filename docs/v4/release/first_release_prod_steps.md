# 首发生产分步脚本（R51）

由 `first_release_prod_steps_gen.py` 从执行单（sha256 `17ef7a87b44493801ee8f45308ef368a2bf6d0cf8956e4fd1166028786bb6f3c`）生成，脚本在 `private/fr-prod-1a131275da9dc8d6/`。17 个 bash 块逐字节拼回与执行单一致，顺序不变；pip 和 D2–D4 用 start_step/check_step 后台跑（Python 正文逐字不变，只从 stdin 改为落盘后执行）。

| 步骤 | 执行单块 | 对照 | sha256 前 12 位 |
| --- | --- | --- | --- |
| p01-readonly | 1 | 一致 | `f77e89594287` |
| p02-admin | 2 | 一致 | `decc9aa0c183` |
| p03a-extract | 3 | 一致 | `3b743be3f350` |
| p03b-install-start | 3 | 一致 | `470ec0a8ad50` |
| p03c-install-status | — | 后台状态查询 | `877b75f195b0` |
| p03d-tokenizer | 3 | 一致 | `2daf544efd4b` |
| p04a-precheck | — | 只读：确认线上仍是 7dbc951（v72）、旧 wrapper 符合 D1 前提 | `7b2890ce3d51` |
| p04b-d1-maintenance | 4 | 一致 | `c962964528e9` |
| p04c-gate-503 | — | 只读：D1 的公网维护 503、遗留进程数 | `abe4efd80f89` |
| p05-context | 5 | 一致 | `d0886381bf49` |
| p06a-d2-start | 6 | 一致 | `e1c83fb18031` |
| p06b-d2-status | — | 后台状态查询 | `80757d0c3918` |
| p07a-d3-start | 7 | 一致 | `ae58a241c843` |
| p07b-d3-status | — | 后台状态查询 | `8952e5c3cf0c` |
| p08a-d4-start | 8 | 一致 | `9be66d4336de` |
| p08b-d4-status | — | 后台状态查询 | `593ddd4f378e` |
| p09-d5-exchange | 9 | 一致 | `8c1f781e3669` |
| p10-d5-assets | 10 | 一致 | `9721d4afbbe7` |
| p11-d6-preopen | 11 | 一致 | `ddd685e41889` |
| p12-d6-writer | 12 | 一致 | `ee5c73a91d61` |
| p13-d7-open | 13 | 一致 | `b9c5e646c930` |
| p14-d7-timer-state | 14 | 一致 | `79ac1d3683fb` |
| p15-final-readonly | — | 只读：D8 最终核对 | `5f576aaf5073` |
| r01-rollback-database | 15 | 一致 | `98b9b0d301a8` |
| r02-rollback-files | 16 | 一致 | `27bdf33202eb` |
| r03-rollback-verify | 17 | 一致 | `606c7ecac82c` |

## 附录：回滚后重新开门（R59，不在默认流程）

`r04-reopen-after-rollback.sh`，sha256 `2d72038f6c4152c2fb159acc0637cde75581d150d704900db7ebec76b5b777eb`。不改执行单。只有用户或大脑当次明确下令才执行：发送脚本另外要求 `reopen-order.json`，默认流程不会带上它。顺序：r03 通过 → 开库连接 → 启动 7dbc951 Web → 门内健康检查 → 读 timer 原状态 → 去维护标记 → 启动飞书并确认 active → timer 按原状态恢复。飞书走外连长连接，不经过 nginx，维护门挡不住，所以和 D7 一样在去维护标记之后才启动。下这个令同时表示接受到期报告恢复投递；不接受就改用 `r04-reopen-timer-held.sh`（sha256 `5836b0427176ae3f7299647549e24ef82860e6963743e343b7b4fa50f7557761`），它只少恢复 timer 这一行。任何一步失败即停；健康检查失败时维护页保持，只有 Web 在门内运行，不自动停，等指令。不删除任何发布、备份或库。

```bash
test ! -e "$FR_OP/opened.json"
test -f "$FR_OP/rollback-old-runtime.json"
test -f /www/wwwroot/p-acme/core-maintenance.flag
"$FR_PY" -I - "$FR_OP" <<'PY'
import sys
sys.path.insert(0,sys.argv[1]);from context import *
v=read('rollback-old-runtime.json')
assert v['old_sha']=='7dbc951eaffebd3d812169865eaefcde16a00ed9' and v['schema_readonly_verified'] and v['closed']
with admin() as c:
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
| R3 646 | 库未开 | `c-wait-zero` → `r03-rollback-verify 2` |
| R3 652 | 库已关，无回执 | `c-wait-zero` → `r03-rollback-verify 2` |
| r04 第一段 | 库未开 | `c-wait-zero` → `r04-reopen-after-rollback 2`（或 `r04-reopen-timer-held 2`），`reopen-order.json` 仍要 |

D5 尾没有补回执时不能进 R1：R1 要求 `exchange-receipt.json`，先跑 `c-d5-tail`。`c-wait-zero` 要求库已关闭，只用于 D2 关库之后。

| 脚本 | sha256 |
| --- | --- |
| `c-wait-zero` | `c75d024b7a9da0ec38b3eec707ca74fcd9a8c16c5ea15fde6778b9538051f9a3` |
| `c-d2-rerun-prep` | `81ce18249cb5846e799b6873ee8e3826d561fe095141f0432483d3bce3b275c8` |
| `c-d3-rerun-prep` | `73624151e44efd3fa3c096e8f888832e28541d8f7a2e2d434db11e840d462727` |
| `c-d4-rerun-prep` | `08c3acf4c3c46992b3d0396084ad51bd6827973bc891e9d6ddd6b08bffa3c0ff` |
| `c-d2-mid-start` | `904b044f5e587e4ac9d6b290932b8facb277bdad9021ee50db0ff4bbc07da963` |
| `c-d2-mid-status` | `d28362f1f21ad2d0a376ef9789d206649144b6afc5fa7e201fd9509aad1b1a85` |
| `c-d2-tail-start` | `f2d548d1d8d21ea2d6ea57650af2a48957f3ff3b82a9a9aaa87707022bb32eab` |
| `c-d2-tail-status` | `3e2177b58036d4c0a85c50196349c0f7f27fd31b3b8b0015865628180363314f` |
| `c-d3-tail-start` | `92f69cc31a7d8659525be44f10de0ed90424c141a059c59f62d913bbe1114324` |
| `c-d3-tail-status` | `b8ac9d979b6b3a90e122863d93ceb4aa9e4b049e0167c8c4d2ea2f08970ec532` |
| `c-d5-tail-start` | `7b2db57d40ad5c97dd84f488526f6a5451b1c600d4d5cd3631e56f0f8dcc5b50` |
| `c-d5-tail-status` | `97941e0db8f5289ca70ec4d868bdf1970cd64f85db38ac8e61dbcab72e2cb626` |
| `c-r1-after-restore-start` | `07cfced484b19ef9a8ad1c9bdbd5b2a84887dd329afbcdfbae17eae2b3d0d868` |
| `c-r1-after-restore-status` | `d624e9a70c6ae5271b960c555795afc8d124593b3975ed47646967321ee3d07b` |
