"""Startup uses a real isolated ledger and local official encoder, never HTTP or permits."""

from __future__ import annotations

import copy
import os
import urllib.request
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from langgraph.checkpoint.postgres import PostgresSaver
from models.test_quota_guard_pg import configure_central
from psycopg import sql

from mingjing_core.agent.context_types import InputMeterUnverified
from mingjing_core.application import consultation
from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.application.production_agent import configured_agent
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.models.config_policy import ConfigError
from mingjing_core.models.port import ChatMessage
from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.models.quota_store import QuotaStore
from mingjing_core.models.quota_types import GuardRejected
from mingjing_core.models.registry import RegistryPort
from mingjing_core.repositories.postgres import PostgresRepository

ROOT = Path(__file__).resolve().parents[3]


@dataclass
class Startup:
    repo: PostgresRepository
    environment: dict[str, str]
    model_path: Path
    models: dict[str, Any]
    store: QuotaStore

    def write_models(self) -> None:
        self.model_path.write_text(yaml.safe_dump(self.models), encoding="utf-8")


@pytest.fixture
def startup(p2_repo: PostgresRepository, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Startup]:
    central = configure_central(p2_repo, monkeypatch)
    models = yaml.safe_load((ROOT / "config/models.yaml").read_text(encoding="utf-8"))
    model_path = tmp_path / "models.yaml"
    environment = {
        "MINGJING_AGENT_ENABLED": "true",
        "K3_TOKENIZER_DIR": str(tmp_path / "not-installed"),
        "MODELS_CONFIG": str(model_path),
        "KIMI_API_KEY": "synthetic-startup-only",
        "MEMBER_CENTRAL_DSN": central["central_dsn"],
        "MEMBER_CENTRAL_SCHEMA": central["central_schema"],
        "MEMBER_ACCOUNT_ID": central["account_id"],
        "MEMBER_LEDGER_IDENTITY": central["ledger_identity"],
    }
    p2_repo.max_running = 3
    store = QuotaStore(
        central["central_dsn"], central["central_schema"], central["account_id"], central["ledger_identity"]
    )
    context = Startup(p2_repo, environment, model_path, models, store)
    context.write_models()
    effects = []

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        effects.append(True)
        raise AssertionError("Startup must not issue HTTP, provision accounts or reserve model permits")

    monkeypatch.setattr(httpx.Client, "send", forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "send", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(QuotaGuard, "acquire", forbidden)
    monkeypatch.setattr(QuotaStore, "provision", forbidden)
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY"):
        monkeypatch.setenv(key, "1")
    yield context
    assert effects == []
    with store.connect() as connection:
        for table in ("core_model_usage", "core_model_batches", "core_model_authorizations"):
            assert (
                connection.execute(sql.SQL("SELECT count(*) AS n FROM {}").format(store.table(table))).fetchone()["n"]
                == 0
            )


@pytest.fixture
def artifacts(startup: Startup) -> Path:
    configured = os.getenv("K3_TOKENIZER_ARTIFACT_DIR")
    directory = (
        Path(configured) if configured else ROOT.parent / "zhiming-v4/private/artifacts/kimi-k3-installer-20261023"
    )
    if not directory.is_dir():
        pytest.skip("requires explicitly installed pinned public K3 files; startup never downloads")
    startup.environment["K3_TOKENIZER_DIR"] = str(directory)
    return directory


def install_environment(startup: Startup, monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in startup.environment.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("ZHIMING_DATABASE_URL", startup.repo.dsn)
    monkeypatch.setenv("CORE_RUN_CONCURRENCY", "3")
    monkeypatch.setenv("CORE_DB_POOL_SIZE", "4")


def repository_factory(startup: Startup, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls = []

    def construct(dsn: str, **kwargs: Any) -> PostgresRepository:
        assert dsn == startup.repo.dsn
        calls.append(kwargs)
        startup.repo.max_running = kwargs["max_running"]
        return startup.repo

    monkeypatch.setattr(consultation, "PostgresRepository", construct)
    return calls


def from_base_with_isolated_checkpoints(startup: Startup) -> ConsultationService:
    # Populate actual library migrations only in this test's disposable schema.
    with startup.repo.pool.connection() as connection:
        connection.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(startup.repo.schema)))
        try:
            PostgresSaver(connection).setup()
        finally:
            connection.execute("RESET search_path")
    with startup.repo.transaction() as connection:
        connection.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(startup.repo.schema)))
        return ConsultationService.from_base()


@pytest.mark.parametrize("flag", [None, "false"])
def test_missing_or_false_switch_keeps_agent_uninstalled(startup: Startup, flag: str | None) -> None:
    source = {} if flag is None else {"MINGJING_AGENT_ENABLED": flag}
    startup.repo.max_running = None
    assert configured_agent(startup.repo, environment=source) is None


@pytest.mark.parametrize("flag", ["", "True", "1", "yes", True])
def test_enable_switch_is_explicit_and_strict(startup: Startup, flag: Any) -> None:
    with pytest.raises(EvidenceError, match="true 或 false"):
        configured_agent(startup.repo, environment=dict(startup.environment, MINGJING_AGENT_ENABLED=flag))


@pytest.mark.parametrize("capacity", [None, 1, 2, True, "3", 3.0])
def test_agent_requires_explicit_integer_capacity(startup: Startup, capacity: Any) -> None:
    startup.repo.max_running = capacity
    with pytest.raises(EvidenceError, match="容量"):
        configured_agent(startup.repo, environment=startup.environment)


@pytest.mark.parametrize(
    "key", ["MEMBER_CENTRAL_DSN", "MEMBER_CENTRAL_SCHEMA", "MEMBER_ACCOUNT_ID", "MEMBER_LEDGER_IDENTITY"]
)
def test_missing_central_configuration_never_installs_agent(startup: Startup, key: str) -> None:
    source = dict(startup.environment)
    source.pop(key)
    with pytest.raises(GuardRejected) as caught:
        configured_agent(startup.repo, environment=source)
    assert caught.value.kind == "ledger_unavailable"


@pytest.mark.parametrize("change", ["identity", "account", "schema", "missing_account"])
def test_startup_checks_actual_deployed_ledger_identity(startup: Startup, change: str) -> None:
    source = dict(startup.environment)
    if change == "identity":
        source["MEMBER_LEDGER_IDENTITY"] = str(uuid.uuid4())
    elif change == "account":
        source["MEMBER_ACCOUNT_ID"] = "not-provisioned"
    elif change == "schema":
        source["MEMBER_CENTRAL_SCHEMA"] = "not_provisioned"
    else:
        with startup.store.connect() as connection:
            connection.execute(sql.SQL("DELETE FROM {}").format(startup.store.table("core_model_accounts")))
    with pytest.raises(GuardRejected) as caught:
        configured_agent(startup.repo, environment=source)
    assert caught.value.kind == "ledger_unavailable"
    if change == "missing_account":
        with startup.store.connect() as connection:
            assert (
                connection.execute(
                    sql.SQL("SELECT count(*) AS n FROM {}").format(startup.store.table("core_model_accounts"))
                ).fetchone()["n"]
                == 0
            )


@pytest.mark.parametrize(
    "change", ["empty", "lock", "effort", "thinking_off", "membership", "tools", "mixed_fallback", "env_override"]
)
def test_primary_configuration_is_locked_and_homogeneous(startup: Startup, change: str) -> None:
    primary = startup.models["models"]["kimi-code-main"]
    if change == "empty":
        startup.models["roles"]["primary"] = []
    elif change == "lock":
        primary["settings"].pop("model_lock")
    elif change == "effort":
        primary["settings"]["effort"] = "low"
    elif change == "thinking_off":
        primary["settings"]["thinking"] = {"type": "disabled"}
    elif change == "membership":
        primary["settings"]["membership"] = False
    elif change == "tools":
        primary["caps"]["tools"] = False
    elif change == "mixed_fallback":
        fallback = copy.deepcopy(primary)
        fallback["model"] = fallback["settings"]["model_lock"] = "k3"
        startup.models["models"]["synthetic-fallback"] = fallback
        startup.models["roles"]["primary"].append("synthetic-fallback")
    else:
        primary["model_env"] = "SYNTHETIC_MODEL_OVERRIDE"
        startup.environment["SYNTHETIC_MODEL_OVERRIDE"] = "k3"
    startup.write_models()
    with pytest.raises((EvidenceError, ConfigError)):
        configured_agent(startup.repo, environment=startup.environment)


@pytest.mark.parametrize("kind", ["relative", "missing", "corrupt"])
def test_missing_or_corrupt_local_tokenizer_fails_closed(startup: Startup, tmp_path: Path, kind: str) -> None:
    directory = tmp_path / "broken-bundle"
    if kind == "corrupt":
        directory.mkdir()
        (directory / "config.json").write_bytes(b"not the pinned public config")
    source = dict(startup.environment, K3_TOKENIZER_DIR="relative" if kind == "relative" else str(directory))
    with pytest.raises((EvidenceError, InputMeterUnverified)):
        configured_agent(startup.repo, environment=source)


def test_real_local_encoder_and_primary_only_are_installed(startup: Startup, artifacts: Path) -> None:
    agent = configured_agent(startup.repo, environment=startup.environment)
    assert isinstance(agent, AgentRuntime) and agent.repo is startup.repo and agent.offline is False
    assert isinstance(agent.port, RegistryPort) and agent.port.role == "primary" and agent.port.stop_on_quota
    assert agent.reviewer.port is None and agent.meter.live_admissible
    assert agent.meter.model == agent.port.registry.resolve("primary")[0].model == "k3-256k"
    assert agent.meter.counter.artifact.parent == artifacts
    measured = agent.meter.measure((ChatMessage("user", "合成启动计量核对"),), (), tool_choice="auto")
    assert measured.estimated > 0 and measured.upper_bound >= 4000


def test_from_base_success_installs_real_agent_without_changing_legacy_port(
    startup: Startup, artifacts: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_environment(startup, monkeypatch)
    calls = repository_factory(startup, monkeypatch)
    service = from_base_with_isolated_checkpoints(startup)
    assert service.runtime_assembly.require_agent().meter.live_admissible
    assert service.runtime is service.runtime_assembly and service.runtime_assembly.legacy.repo is startup.repo
    assert service.runtime_assembly.agent.reviewer.port is None
    assert type(service.model).__name__ == "PortBackedModel" and service.model.role == "primary"
    assert calls == [{"initialize": False, "max_size": 4, "max_running": 3}]
    assert not startup.repo.pool.closed


def test_from_base_default_false_preserves_legacy_only(startup: Startup, monkeypatch: pytest.MonkeyPatch) -> None:
    install_environment(startup, monkeypatch)
    monkeypatch.delenv("MINGJING_AGENT_ENABLED")
    monkeypatch.delenv("MODELS_CONFIG")
    monkeypatch.delenv("MINGJING_MODEL_PORT", raising=False)
    monkeypatch.delenv("CORE_RUN_CONCURRENCY")
    repository_factory(startup, monkeypatch)
    service = from_base_with_isolated_checkpoints(startup)
    assert service.runtime_assembly.agent is None and service.runtime is service.runtime_assembly.legacy
    assert startup.repo.max_running == 1 and type(service.model).__name__ == "ConfiguredModel"


@pytest.mark.parametrize("failure", ["agent_config", "model_config", "schema"])
def test_from_base_failure_closes_repository_without_falling_back(
    startup: Startup, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    install_environment(startup, monkeypatch)
    repository_factory(startup, monkeypatch)
    if failure == "agent_config":
        monkeypatch.setenv("MINGJING_AGENT_ENABLED", "invalid")
    elif failure == "model_config":
        startup.models["models"]["kimi-code-main"]["model"] = "unexpected-model"
        startup.write_models()
    else:

        def unavailable() -> None:
            raise EvidenceError("synthetic schema unavailable")

        monkeypatch.setattr(startup.repo, "verify_schema", unavailable)
    with pytest.raises((EvidenceError, ConfigError)):
        ConsultationService.from_base()
    assert startup.repo.pool.closed
