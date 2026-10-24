"""Native read-only views and real empty observers for stored-session regressions."""

from contextlib import closing, contextmanager
from types import SimpleNamespace

from models.test_quota_http_pg import rows as quota_rows
from psycopg import sql

from mingjing_core.repositories.postgres import PostgresRepository, fingerprint
from tools.eval.targets.v4_durable import DurableCore30Target

from .test_eval_quota_clear_pg import central
from .test_eval_quota_resume_pending_support import core_state, rows


def bind(value):
    target = value.target
    value.dsn, value.schema, value.owner = target.dsn, target.schema, target.owner
    value.session = target.lifecycle_session
    value.run = target.repo.fetch_run(target.owner, target.run_ids[-1])


def observer(value):
    target = DurableCore30Target(
        model=value.binding.model, dsn=value.dsn, environment=value.live.environment, adapter_factory=value.live.factory
    )
    assert target.repo is None and target.lifecycle_session is None
    value.live.targets.append(target)
    return target


@contextmanager
def reader(value):
    with closing(PostgresRepository(value.dsn, schema=value.schema, initialize=False)) as repo:
        current = SimpleNamespace(**vars(value))
        current.target = SimpleNamespace(repo=repo, owner=value.owner)
        with repo.transaction() as connection:
            assert connection.execute("SELECT to_regnamespace(%s) AS present", (value.schema,)).fetchone()["present"]
        yield current


def whole_state(value):
    with reader(value) as current:
        core = core_state(current)
    with value.control.connect() as connection:
        control = connection.execute(
            sql.SQL("SELECT * FROM {} ORDER BY session_id").format(value.control.table())
        ).fetchall()
    return core, fingerprint(central(value)), fingerprint(control), len(value.live.sent)


def physical(value):
    records = quota_rows(value.live.guard)
    assert len({row["attempt_id"] for row in records}) == len(records)
    assert all(row["run_id"] == value.run["id"] and row["scenario_id"] == value.binding.scenario_id for row in records)
    return records


def assert_usage(result, *, inherited, new, historical):
    def counts(pair):
        return {"target": pair[0], "judge": pair[1], "total": sum(pair)}

    expected = {
        "inherited": counts(inherited),
        "new": counts(new),
        "historical_actual": counts(historical),
    }
    usage = result["execution_usage"]
    assert {key: usage[key] for key in expected} == expected
    assert usage["current_observation_only"] is True
    for name, pair in (("inherited", inherited), ("new", new), ("historical_actual", historical)):
        actual = usage[name + "_usage"]
        assert actual["target_model_calls"] == pair[0] and actual["judge_model_calls"] == pair[1]
        assert actual["model_calls"] == sum(pair)
    case = result["case"]
    assert case["target_model_calls"] == historical[0] and case["judge_model_calls"] == historical[1]
    assert case["model_calls"] == sum(historical)


def prefix(value):
    with reader(value) as current:
        repo = current.target.repo
        native = [
            row
            for row in sorted(rows(current, "core_run_steps"), key=lambda row: row["seq"])
            if row["seq"] < value.pending_seq
        ]
        private = [
            row
            for row in repo.list(value.owner, "runtime_step", include_deleted=True)
            if row.get("run_id") == value.run["id"]
            and (
                row.get("stage") in {"agent_initial_context", "agent_model_request"}
                or row.get("stage") == "agent_model_attempts"
                and row["value"]["seq"] < value.pending_seq
            )
        ]
        return {
            "facts": repo.list(value.owner, "fact", include_deleted=True),
            "steps": native,
            "private": sorted(private, key=lambda row: row["id"]),
            "events": [
                row
                for row in rows(current, "core_run_events")
                if row["kind"] in {"started", "tool_call", "tool_result"}
            ],
        }
