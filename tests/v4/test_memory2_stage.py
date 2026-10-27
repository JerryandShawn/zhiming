"""The memory stage can never adopt first-release names or disable formal safety."""

import pytest

from tools.first_release_contracts import RestoreRejected
from tools.first_release_native_exchange import Scope, _original
from tools.first_release_stage_copy import CopyScope
from tools.memory2_stage import DATABASE, ROOT, UNIT, MemoryStageScope, main

OPERATION = "abcdef0123456789"


@pytest.mark.parametrize(
    "changes",
    [
        {"database": "zhiming_core_fr_stage"},
        {"database": "zhiming_core_stage"},
        {"database": "zhiming_core_live"},
        {"root": "/opt/zhiming-core-fr-stage"},
        {"unit": "zhiming-core-fr-stage.service"},
        {"local_drill": True},
        {"operation": "4e680f175ea28cc8"},
        {"operation": "1a131275da9dc8d6"},
    ],
)
def test_memory_entry_rejects_first_release_names_and_bypasses(changes):
    args = {"operation": OPERATION, **changes}
    with pytest.raises(RestoreRejected):
        MemoryStageScope(**args).validate()


def test_both_native_metadata_gates_reject_the_other_stage_before_any_io():
    memory = MemoryStageScope(OPERATION)
    memory.validate()
    assert (memory.target, memory.root, memory.unit) == (DATABASE, ROOT, UNIT)
    assert memory.source == "zhiming_core_stage"
    assert CopyScope(OPERATION).target == Scope(OPERATION).original == "zhiming_core_fr_stage"
    for scope, wrong in [(memory, "zhiming_core_fr_stage"), (Scope(OPERATION), DATABASE)]:
        with pytest.raises(RestoreRejected, match="EXCHANGE_METADATA_DATABASE"):
            _original(None, scope, {"database": wrong})
    assert memory.replacement != Scope(OPERATION).replacement
    assert memory.failed != Scope(OPERATION).failed


def test_cli_is_validation_only_until_explicit_apply_and_rejects_wrong_names(tmp_path, capsys):
    args = ["copy", "--operation", OPERATION, "--output", str(tmp_path / "receipt.json")]
    assert main(args) == 0
    assert '"database_connections": 0' in capsys.readouterr().out
    assert not (tmp_path / "receipt.json").exists()
    assert main(args + ["--database", "zhiming_core_fr_stage"]) == 2
    assert "MEM2_STAGE_DATABASE" in capsys.readouterr().out
