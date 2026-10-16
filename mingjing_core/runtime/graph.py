"""One LangGraph execution. Checkpoints contain identifiers, never history bodies."""
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from ..domain.consultation import CoreError, InvalidAnswer
from ..domain.contracts import ScopeError, RevisionConflict, LeaseConflict, BudgetExceeded


class RunState(TypedDict):
    owner: str
    run_id: str
    phase: str


PHASES = ("intake", "memory", "snapshot", "plan", "calculation", "specialists", "synthesis", "review", "validation", "commit")


class LangGraphRuntime:
    def __init__(self, repo, *, initialize=True):
        self.repo = repo
        self.checkpointer = PostgresSaver(repo.pool)
        if initialize:
            self.checkpointer.setup()
        else:
            with repo.connection() as connection:
                migration = connection.execute('SELECT max(v) AS version FROM checkpoint_migrations').fetchone()
                if migration['version'] != len(self.checkpointer.MIGRATIONS) - 1:
                    raise RuntimeError('LangGraph checkpoint schema needs an explicit migration')

    def execute(self, service, owner, run_id, lease_token, emit=None):
        existing = self.repo.fetch_run(owner, run_id)
        if existing['status'] == 'succeeded':
            return existing['result']
        graph = StateGraph(RunState)
        def node(phase):
            def execute_stage(state):
                try:
                    service.execute_stage(owner, run_id, lease_token, phase, emit)
                except Exception as exc:
                    # LangGraph serializes node failures. Never let provider values,
                    # input validation dumps or private content enter its error blob.
                    safe_types = (CoreError, ScopeError, RevisionConflict, LeaseConflict, BudgetExceeded, TimeoutError)
                    safe_type = type(exc) if isinstance(exc, safe_types) else InvalidAnswer
                    raise safe_type('本轮阶段未完成（' + phase + '）；请查询运行状态或恢复原请求') from None
                return {"phase": phase}
            return execute_stage
        previous = START
        for phase in PHASES:
            graph.add_node(phase, node(phase))
            graph.add_edge(previous, phase)
            previous = phase
        graph.add_edge(previous, END)
        runtime = graph.compile(checkpointer=self.checkpointer)
        epoch = existing.get('retry_epoch', 0)
        config = {"configurable": {"thread_id": run_id + ':e' + str(epoch)}, "recursion_limit": 20}
        checkpoint = runtime.get_state(config)
        runtime.invoke(None if checkpoint.next else {"owner": owner, "run_id": run_id, "phase": "queued"}, config)
        return self.repo.fetch_run(owner, run_id)['result']

    def purge(self, run_id, epoch=0):
        self.checkpointer.delete_thread(run_id + ':e' + str(epoch))
