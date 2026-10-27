# Board39 narrow followup/decision and evaluation fixes

## Progress
- [x] 2026-10-25 04:46 Beijing: read main39 and review38 section7, isolate from frozen8727d44; contract amendment written before judge/regex changes.
- [x] Reproduce TA01 evaluator KeyError on native auto face-down draw inspection; fix public observer without changing product tarot/deck/draw identity/scoring.
- [x] Native date-only followup default20:00, preserve18:00–22:59, late23:00+ next08:30; reminders and exact datetime events keep prior contracts.
- [x] Prompt1.2.3: evening event followup, A/B one-to-two sentence decision summary before one question.
- [x] Private native due/card/ask evidence and trusted resolved fixture profile/seed memories/prior receipts/effects in external scoring; hashes cover payload. Equivalent regex amendment only core29 overlay, historical scenario files untouched.
- [x] Strict v39 plan selects M01/Q03/Q04/D01/TA01, review17 decisions separately sourced; no automatic raw score overwrite.
- [ ] Same candidate R11; then new real connection/targeted five only after connection budget decision.
- [ ] Bind stage package SHA/hash/R11; actual stage/production still unauthorized and no37/31 Go.

## Surprises & Discoveries
Original TA01 report had one native run and no first-turn assertions, contradicting an assumption that only the second-turn draw label failed. Native PG reproduction: draw_source=pick passes; auto creates a valid face-down selected card with no public card_id, but tools/eval/targets/v4_tarot.py rows indexed card_id unconditionally, raising KeyError during inspect_db. Filter only revealed cards; existing reveal already resolves unique real draw and binds its fixture label. No product tarot change. Original ephemeral schema was unavailable during read-only inspection, so no historical traceback or original draw_source is invented.

Connection cap30 remains explicit. Prior real connection used27, a new clean proof needs minimum4 physical (tools2/input1/long1); remaining3 cannot complete. No paid request is started merely to hit cap. New targeted run is prepared but requires cap/approved proof policy decision, with original account/ledger retained.

## Decision Log
Board39 accepts frozen8727 full29 + only the five affected new-candidate cases; source and two original report hashes plus exact review hash bind retest plan. Current branch diff limited to followup policy, two prompt instructions, tarot evaluation observer, scoring fixture/context/evidence and approved regex/selection contracts, necessary tests and this plan. Schedule due normalization precedes future-time validation so an arbitrary past model time for today's date-only event can become valid today20:00; actual reminders still reject past due. No stage/server access is inferred from files.

## Outcomes & Retrospective
Separate actual isolated PG rounds retained, never combined into one all-green chain: initial pick-path1/1 b429e7812a2b4f5c8f5e31bd1e2868ae; two fixture attribute-access rounds failed2 each (990df6b5dbab4624a764c3a4a0e42825/61095ca4555d407898246ac8c17efdb1), then actual auto-observer failure1/pickpass1 c38a0643464441488257efe4744b105d; fixed pick+auto2/2 3.51s484a40b7270a4a3ba462b11bb7bbe045. Native schedule/card context9/9 8.56s344122ce93e64b49b34867ab5a77e2a4. Stronger full original tarot assertions/both modes, exact retest selection/hash rejection and native persisted judge detach/reuse4/4 32.86sd1b322e79b7546e7ad88a0fa7ad77cfe. Today's date-only event past model time normalization1/1 1.99s62a81f9b7bec4b23b13d09b7b9fec8a4. Metadata/XML/log root-read. No live provider calls, no servers, no external messages. CI not checked; new R11 pending. Review39: historical raw9/29 remains, human review26pass/2failed/TA01unfinished separate.
