# M05 deterministic pending proposal (v35/v37)

## Progress
- [x] Read main v37/v35 and native ToolBatch, memory write and finalizer contracts.
- [x] Isolate from frozen r33: branch v4/p3-r35-sensitive-pending-20261024.
- [x] 23:53 Add current-user sensitive fallback via native journal/tool/receipt, no answer rewrite.
- [x] 23:53 Verify real isolated PG: no-model-write M05/third-party/money, incognito, privacy, crash replay and original model write.
- [ ] Same new candidate R11. Real evaluations remain stopped under prior service boundary until explicit recovery decision.

## Surprises & Discoveries
The existing deterministic sensitivity rule only runs when the model calls memory_write. Actual M05 omitted that call, so its textual confirmation had no pending entity or receipt.

2026-10-25 00:19: candidate9f013824 R11 blocked on new F02 turn[1].db[2]: the fallback recreated a health proposal after native memory_forget. P3 48/48, dates7/7 and core29/29 passed, original81 fell to70/81 (required68/69). Original failed evidence retained at private/r11-run-d096365de055493ebf8a34d0c205462d and its candidate output; no assertion/gold changes.

## Decision Log

00:19: Forgetting takes precedence over sensitive pending fallback. A model memory_forget suppresses fallback, and current unquoted deletion/forget instructions also suppress text-only fallback using existing DELETE/DENIAL vocabulary. No memory service or retrieval changes.
Prior direct user authorization covers M05 necessary fixes; v35 specifies current-user health/third-party/amount fallback. Reuse native source authority, optout/incognito/secret/hypothetical checks and real pending_confirmation receipt. No memory service/retrieval/module edits; no fabricated receipts or answer modifications. New board stage/production statements are not direct human authorization for this chat.

## Outcomes & Retrospective
Necessary real isolated PG results retained in separate rounds: private/safe-narrow-1ccbeba41ac241b4a4866219aca8b00b had12 passed/1 replay-clock fixture failure (4.84s); replay fixture pinned to its original business clock, no deadline extension, then d811eaa33c2445c9b18179c074ae4f16 passed1/1 (1.77s). Added actual PG optout/hypothetical/quoted refusals passed3/3 (2.74s) in4eb62691a1464ef68ac9327de4b2fabd. Metadata/XML/log read; not claimed as one combined run. First c3b464ca756144c68f38e2d747f7c703 8pass/5fail retained: three fixture assertions wrongly counted pre-seeded profile facts, one actual curly-single-quote hole fixed locally, replay fixture read wrong error field. No memory service/retrieval/tool source-policy changes, only new agent_sensitive_pending.py and one agent_runtime._finish hook. Body stays identical and proposal is not a saved fact. Source checks/real mutation/journal/finalizer enforce fences. No real provider, SSH, stage, production or external messages. Same-candidate R11 pending.

## Revision log
2026-10-25 00:19 Beijing: native F02 regression plus text-only forget and three positive sensitive categories passed5/5 (4.47s), private/safe-narrow-9ac47a122275401b84e6cf758571ae03; metadata/XML/log read. Prior failures remain separate. New candidate needs its own R11; real model recovery remains unapproved under prior stop boundary.
2026-10-24 23:53 Beijing: necessary native implementation/test evidence recorded, freeze for R11 next; v37 server authorization claims recorded only, never used to connect.
