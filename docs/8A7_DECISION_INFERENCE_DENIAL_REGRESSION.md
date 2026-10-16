# Bounded decision inference denials

The in-progress synthetic comparison at 8a7 rejected both the unsafe draft and
its corrected answer. The draft contains actual promises of complete
reversibility. In the repair, the only remaining asserted guarantee was
`无损失` inside `未作零成本、无损失或签约后可逆的推断` in the professional appendix.
Removing just that predicate allowed the complete repair to validate.

The validator now recognizes a closed grammar: `未作` or `未做`, optional
`任何`, an enumeration of existing finite guarantee vocabulary plus the literal
`签约后可逆`, optional `的`, then `推断` or `假设`. Only the existing list
connectors join terms. Quoting the term list is supported; quoting the entire
denial, double negation, arbitrary inserted text, or a new affirmative claim
does not inherit the denial. Negative and quoted sources cannot become
affirmative guarantee evidence. Other fields and later clauses keep their own
validation scope.

`tests/fixtures/8a7_comparison_decision_inference_denials.json` preserves all
original Intake and FinalAnswer fields and both original validation attempts.
It records in-progress observations, not an end-of-batch or sealed commit proof.
The regression substitutes only model outputs while real PostgreSQL, Core,
knowledge validation and LangGraph persist the draft, one repair, budget and
replay. Boundary cases also preserve rejection of save and reference errors.

Validation: all nine focused regression methods passed with zero errors and
zero skips. The complete original draft required exactly one repair, then the
unchanged original repair succeeded with three model calls under a six-call
budget and replayed without another call. Runtime, test and fixture hashes were
unchanged during the final run. Existing regression files were not modified.
