# Independent briefing acceptance

- Frozen semantic matrix: 82 rows in `acceptance_expected_mod.json`.
- Matrix SHA256: `8835190dfbfc55b27cea027eb6dedd55fef1b3e60e24c021bf0fb466c8ea763c`.
- Declared synthetic P8 snapshot SHA256:
  `0b0984e1a6cf9c48f060071e861da1438d9ee2122a7635095d7f71933a589205`.
- Both JSON inputs are unchanged after freezing. No Q5/B material is used.
- Source P8 README declares the sample synthetic. It is read as JSON; no chart,
  model, database, server, scheduler or notification call is made.

## Oracle-expression correction before publication

The first independent run passed 108 cases and failed two tests that required a
foreign item basis to raise an exception. The frozen matrix requires isolation,
not an exception-specific API. The root's current-source contract also permits
safe omission when no matching authorized source projection exists.

Read-only inspection confirmed that both foreign-owner and foreign-subject
results omit the body and all basis references and record `source_scope_mismatch`.
The root explicitly approved correcting these two new test expressions. They now
accept a controlled error or complete omission, additionally checking that body,
source ID, document ID and claim ID do not leak in output or exception text.
The 82-row JSON, its expected isolation semantics and its SHA256 remain unchanged.

An added current-state boundary initially expected duplicate states to be omitted
by composition. The immutable `BriefItem` contract already rejects duplicates at
construction with a controlled error. The new test now accepts this earlier
fail-closed boundary or complete omission, still requiring error-text privacy.
This changes where rejection may occur, not the frozen isolation requirement.

Current source snapshots are synthetic trusted-host inputs. Hash consistency and
these pure tests do not establish real PG authorization or delivery integration.
