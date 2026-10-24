# v38 answer header and transient external judge handling

## Progress
- [x] 2026-10-25 01:47 Beijing: read board38, inspect runtime/reviewer/finalizer and pinned prompts; isolate from frozen75d53f5.
- [x] Strip only the entire first history-format timestamp/channel line before review/commit, emit replacement for streamed draft. Mid-body or inline text stays exact.
- [x] Bump system prompt1.2.1 to1.2.2 with one timestamp/channel prohibition; canonical LF manifest pins updated.
- [x] Classify external judge transient network/5xx as one retry then ungraded; preserve HTTP400/403/429 and permission/quota/identity stops.
- [ ] New same-source R11 and full29 live evaluation; no old candidate scores inherited.

## Surprises & Discoveries
The external judge previously propagated transient ProviderStopped and its journal only accepted physical status ok. v38 requires acknowledged transient failed attempts to stay in the real central physical evidence while scoring retries once; unknown/inflight attempts remain forbidden. Fatal statuses still propagate without conversion.

## Decision Log
Reuse prior direct human real-evaluation authorization; board38 explicitly resumes a new final full29, superseding the old service-window wait for that new run. Keep original R33 failed reports/physical waste and cumulative connection23/30; no new account or ledger. Server/stage/production claims remain outside this chat authorization. No SSH or external messages. The private operator uses existing native CLI; new run starts29, later retries only unfinished questions under original R24/v32 timings. Runtime response normalization precedes reviewer proof so finalizer verifies the exact reviewed body.

## Outcomes & Retrospective
Native isolated PG timestamp-header commit plus body preservation4/4,3.02s: private/safe-narrow-851b3fd779ad4f40b451fe5db03cebb1. Actual PG/Mock HTTP503 judge recovery and double-failure ungraded, prior required/protocol compatibility and fatal controls7/7,46.82s: private/safe-narrow-8f3691b9445546afa6112a0ff16af745. Additional fatal HTTP400/403/429/permission conversion refusal4/4,.78s: private/safe-narrow-1ecb0ab0d62f42969818596403a089a6. Each metadata/XML/log read independently; not one combined full chain. No live provider calls during these tests. CI not checked; R11/full live pending. No database migrations or shared memory-service changes.
