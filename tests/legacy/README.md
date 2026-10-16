# Retired controller regression references

These eleven original v6 files contain the 102 historical methods enumerated in `docs/CORE_V3_BEHAVIOR_COVERAGE.json`. They are retained unchanged as requirements evidence. They import the retired controller globals and old SQLite APIs; execute them only in their matching historical checkout.

Current acceptance runs `test_core*.py` through the real Core service, PostgreSQL and LangGraph. `tools/replay_core_synthetic.py` runs 300 seeded target rounds with a provider fixture. `tools/compare_core_providers.py` separately compares two synthetic questions through real provider calls. Neither treats passing legacy components as proof the new service passes.

This archive intentionally has no `__init__.py` and is excluded from pytest traversal.
