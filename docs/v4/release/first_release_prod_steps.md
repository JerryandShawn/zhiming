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

`r04-reopen-after-rollback.sh`，sha256 `6465d08d1e3528e054595db91c4472150ee785c2ecf230e05364cee05bb2d395`。不改执行单。只有用户或大脑当次明确下令才执行：发送脚本另外要求 `reopen-order.json`，默认流程不会带上它。顺序：r03 通过 → 开库连接 → 启动 7dbc951 旧服务 → 门内健康检查 → 去维护标记 → timer 按 D1 原状态恢复。任何一步失败即停，维护页保持；健康检查失败时已启动的旧服务不自动停，等指令。不删除任何发布、备份或库。

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
systemctl start zhiming-core-feishu.service
systemctl is-active --quiet zhiming-core-feishu.service
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
rm /www/wwwroot/p-acme/core-maintenance.flag
"$FR_PY" -I - "$FR_OP/units-before.json" > "$FR_OP/r04-timer-state.txt" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))['zhiming-core-reports.timer']['ActiveState'])
PY
if test "$(cat "$FR_OP/r04-timer-state.txt")" = active; then systemctl start zhiming-core-reports.timer; fi
echo "R59: maintenance removed; report timer restored to $(cat "$FR_OP/r04-timer-state.txt")"
```
