# Core v3 continuation plan

This document records the accepted direction for the next refactor. It is a plan, not a claim of an implemented or deployed runtime. The current website on main still calls ChatAgent and v6_agent. Development components are preserved on work/core-v3.

## Required outcome

Replace the old agent controller with a modular domain core. Use Pydantic for contracts, LangGraph as the sole execution runtime, PostgreSQL for authoritative state, and a single ConsultationService for website chat, tarot, Hermes/Feishu and scheduled reports. Do not wrap or call the old ChatAgent as the new controller. Keep verified calculators, the frontend, scoped memory/case rules, tarot draws and history as migration assets.

An execution should route the current intent, read a scoped/versioned snapshot, create a typed plan, compute only relevant systems, select actual rules and sources, run isolated specialists, synthesize where meaningful, validate claims, and review deep/multi-system/important answers before committing. Persist checkpoint identifiers and revisions rather than private message bodies. Budget model calls globally: fast 2, standard 6, deep 10, with one shared repair allowance. Make effects idempotent using stable operation identifiers.

Claims must link verified original user facts or real calculation fields to allowed interpretation rules. A real JSON field alone does not prove an interpretation or life outcome. Keep sources, rules, prerequisites, negative examples, school/method versions and time scales explicit. Missing rules produce RULE_GAP. Distinguish exact, approximate, interval and unknown birth times; never save a sampled noon as a known time.

Cross-system synthesis is a topic matrix of support, tension, not relevant, missing, not used and uncertain. Do not force agreement, vote on outcomes or turn similar symbolism into event probabilities. Reality and stated constraints drive decision advice. Supportive conversation should help the user separate worries from observed facts and choose controllable next steps, without diagnosis or guarantees.

The user-facing answer starts with ordinary language: direct answer, why, realistic alternatives when needed, small actions and a useful review point. Professional chart/card derivation and method limits remain in a final expandable appendix. Hermes is a thin identity/source/delivery adapter and must not reinterpret validated output with a second model.

## Preserved development components

| Location on work/core-v3 | Current role |
| --- | --- |
| mingjing_core/knowledge/ | Versioned rule/source registry and evidence checks for four symbolic systems. |
| mingjing_core/domain/calculation.py | Calculation contracts, profiles and uncertainty branches. |
| mingjing_core/adapters/charts/ | Adapter around existing pure calculators with provenance and scoped artifacts. |
| mingjing_core/adapters/channels/ | Hermes/report and delivery adapters expecting the future service. |
| hermes/core_consultation.py, hermes/SKILL.md | Future thin channel entrypoint and instructions. |
| tests/test_core_*.py | Component tests; not a completed runtime acceptance suite. |

These files have not been accepted as an integrated production implementation. In particular, the unified service/runtime, PostgreSQL repository, migrations and persistent checkpoints are not yet present. New channel instructions must not be deployed before the service they require exists.

## Next implementation steps

1. Add domain contracts, repository ports, a model port and authoritative PostgreSQL implementations. Keep domain dependencies independent of UI, Hermes runtime and legacy controller imports.
2. Implement the LangGraph execution and ConsultationService. Use stable run IDs, scoped revisions, isolated specialists and a global call/repair budget. Match the existing frontend result shape through a presentation adapter.
3. Wire all entrypoints to the same service and fact writer. Prevent concurrent SQLite/PostgreSQL fact authorities and independent Hermes memory writes. Reports need a fresh revision check immediately before delivery; uncertain delivery must reconcile before retrying.
4. Implement explicit migration, read-only replay, correction/deletion propagation and checkpoint cleanup. Preserve source revocations across backup restoration. Validate on disposable PostgreSQL data before any production cutover.
5. Add architectural import checks, budget/effect/revision tests, four-system source/rule negative cases and one real-model end-to-end run in an isolated environment. Document missing inputs, method fallbacks and untested behavior honestly.
6. Retire the old orchestration after verified cutover. Production deployment and real channel delivery remain separate release actions.

Standard errors include AUTH_SCOPE_ERROR, STALE_INPUT, MISSING_INPUT, CALCULATION_ERROR, RULE_GAP, REFERENCE_ERROR, SCOPE_MISMATCH, UNSUPPORTED_INFERENCE, DRAW_MISMATCH and DELIVERY_UNCERTAIN.

The detailed user attachment supplied for this direction was document 02. Its referenced companion research files 01/03/04/05/06 were not available in the local handover. Do not invent their contents. No server password, API key, personal birth record or real message database is included in this repository.
