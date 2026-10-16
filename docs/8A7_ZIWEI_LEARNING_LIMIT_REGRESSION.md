# Ziwei learning-result limitation regression

The recorded synthetic-profile ziwei sample from commit
`8a7ca631b793a4d084a3cfc4830f36cb1ecb1f5d` failed `REFERENCE_ERROR` solely
because its synthesis, review and full repair all contained this caveat:

> 命盘与流日象征仅供反思，不构成学习成效保证

This explicitly denies a learning-result guarantee. The existing finite
limitation grammar accepted only `不/不能构成对OBJECT的保证`, with
`学习效果`, `成绩` and `他人动机` as its closed objects.

The change adds only the finite learning-result synonyms
`学习效果/学习成效/学习成果` and makes `对` and `的` optional within that
same object-list grammar. Existing finite list connectors, optional `任何`,
the guarantee-at-clause-end requirement, quote rejection and double-denial
checks remain in place. The same finite-object branch also rejects the
immediate double-denial prefixes `不会/不应/没有/未曾`; this does not alter
other symbolic-limit branches. No arbitrary object or intervening-prose span
is added.

`tests/fixtures/8a7_ziwei_learning_limit_diagnosis.json` preserves the complete
original diagnosis bytes, including all three final outputs and the original
failure issues. Its SHA256 is
`674b13a040f2eef56b5235e90a23c82e3cd6468b64f2b40ccf0ea500742ed357`.
The test substitute rebinds only opaque fact, claim and chart/profile IDs to
the isolated run's actual references; it preserves the original prose.

Validation used actual PostgreSQL, LangGraph and the ziwei calculator, with
only model responses substituted. Core ran under the audit Python 3.12
environment and charts under `work/chart311-venv/Scripts/python.exe` (3.11).
The original validator reproduced one failure with zero errors or skips:
all three original final stages reported only the symbolic-certainty issue,
and execution failed after four calls including its single repair.

The focused regression module `tests.test_core_8a7_ziwei_learning_limits`
passed all six tests, with zero failures, errors or skips. Original standard
execution now succeeds in three of six allowed calls without repair, and
each of the three original final outputs independently validates. A genuine
affirmative guarantee still consumes the one repair and succeeds in four
calls using the exact original full repair. Unknown fact/claim references
still fail after that one repair. Fourteen finite safe clauses, nineteen
positive/quoted/double-denial/contrast/unbounded-object clauses and three
cross-field cases retain their expected outcomes. Repeated execution of a
successful run adds no model calls.

This is local model-substitute regression evidence. It does not establish
real-world prediction accuracy or replace the completed release's evidence.
