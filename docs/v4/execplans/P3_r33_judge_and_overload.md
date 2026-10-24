# R24/R25 v33 execution plan

## Progress
- [x] Read main v33 under direct human authorization; preserve stopped 2f tree.
- [x] New independent r33 worktree; record scoring contract first.
- [x] Explicit eval_critic required, one validation retry, null judge_unavailable; internal critic has zero tools.
- [x] R24 strict overload classifier and bounded fresh-run wait gate; cumulative connection cap30.
- [ ] Necessary offline tests, same clean candidate R11, new connection, whole29 live.

## Surprises & Discoveries
- PortBackedModel selected auto for external structured scoring; internal critic is text-only and disallows tools.
- Existing judge journal assumed exactly one physical critic attempt; R25 needs one or two acknowledged attempts.
- HTTP429 overloaded is not a quota signal under R24; explicit rate/quota/permission/concurrency/Access still stops.

## Decision Log
- Direct v33 supersedes former unconditional429 stop and cumulative20 cap.
- Judge errors are ungraded, not capability failures; original older results remain unchanged.
- No primary auto policy or production/v3 endpoint changes; stage/production untouched.

## Outcomes & Retrospective
Pending necessary verification. No new real requests yet.

21:57 Discovery: new Git checkout has canonical LF, while prior prompt manifest bound CRLF disk bytes. Corrected manifest/hash to canonical tracked artifacts without changing prompt prose/version; first PG tests blocked before POST, not judge-wire failures. Collection fixture import errors and original failed runs retained in private safe-narrow outputs.

21:59 Verification: 14/14 passed in32.25s, private/safe-narrow-4d7d4ecb25c6450e9f9a7fca07848541 metadata/XML/log read. Includes actual PG+official tokenizer+Mock native primary/critic HTTP: required on critic, one failed protocol then success, twice invalid => null judge_unavailable, fatal signals not retried. Compatibility16 passed/1 old30-count failed in015b0a8999294621803d3ea6e9bebe36; changed stale fixture counts to len(CORE30_IDS), as required v29, and old critic error expectations to null/ungraded/2 attempts perR25.

22:01 Necessary compatibility corrected32/32 (0.75s), private/safe-narrow-6014f3f22f3146ca8575a3ae6ac51b7d; extra timeout/quota gate1/1 (0.83s), private/safe-narrow-51bd6f00c585438ab4e941288c168425. Metadata/XML/log read; distinct rounds, not one combined chain. Ruff/format checked. Candidate now ready for same-source R11 then connection/core. No real requests yet.
