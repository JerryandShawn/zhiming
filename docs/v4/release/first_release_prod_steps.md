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
