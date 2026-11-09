"""Health reports the configured model under MODELS_CONFIG instead of the old constant 'test'."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from mingjing_core.adapters.web import create_app, health_model
from mingjing_core.models.legacy import PortBackedModel
from mingjing_core.models.registry import ModelRegistry

PROFILE = Path(__file__).resolve().parents[3] / "config/models.first-release.yaml"
SECRET = "synthetic-health-key-never-returned"


def port_model(environment: dict[str, str]) -> PortBackedModel:
    return PortBackedModel(
        ModelRegistry(PROFILE, environment=environment), role="primary"
    )


def test_port_backed_model_reports_first_usable_primary_model():
    assert port_model({"KIMI_API_KEY": SECRET}).configured_model() == "k3.1-pro"
    assert port_model({"MOONSHOT_API_KEY": SECRET}).configured_model() == "k3.1-pro"
    assert port_model({}).configured_model() == "unavailable"


def test_health_model_keeps_other_service_shapes():
    assert health_model(None) == "test"
    assert health_model(SimpleNamespace(model="scripted-model")) == "scripted-model"
    assert health_model(port_model({"KIMI_API_KEY": SECRET})) == "k3.1-pro"


def test_health_endpoint_reports_real_model_without_credentials(monkeypatch):
    monkeypatch.setenv("MINGJING_TOKEN", "synthetic-token")
    monkeypatch.delenv("ZHIMING_TOKEN_OWNERS", raising=False)
    service = SimpleNamespace(
        model=port_model({"KIMI_API_KEY": SECRET}),
        repo=SimpleNamespace(ensure_owner=lambda owner: None),
        memory=SimpleNamespace(facts=lambda owner: []),
    )
    client = TestClient(create_app(service=service))
    response = client.get("/api/health", headers={"X-Token": "synthetic-token"})
    assert response.status_code == 200
    assert response.json()["model"] == "k3.1-pro"
    assert SECRET not in response.text
