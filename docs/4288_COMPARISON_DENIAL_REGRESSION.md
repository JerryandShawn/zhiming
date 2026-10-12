# 4288 comparison denial regression

The recorded `new_single_specialist` decision draft correctly failed because it
asserted that the first step was completely reversible. Its full repair instead
denied three finite promises and left one conditional exit question unverified.
These predicates now retain their local negative/question scope. A new object,
verb, affirmative promise, double denial, quoted report (including quotes across
sentence/semicolon boundaries), or another field cannot inherit that scope.

`tests/fixtures/4288_comparison_decision_denials.json` preserves the complete
synthetic intake, synthesis and repair contracts, original validation attempts,
source commit and source SHA256. Existing recorded fixtures and model helpers
are unchanged. Only the model is substituted in the regression tests.

Validation: `tests.test_core_4288_comparison_decision_denials` passed all five
tests with real PostgreSQL and LangGraph, without skips. Its 60 service runs
include the original draft → one repair → persistent success, four finite
negative/question successes without repair, and 55 rejected counterexamples.
Repeated submit/execute of the completed original request returns its persisted
answer without additional model calls. The original unmodified service failure
and raw source remain preserved outside the repository for diagnosis.
