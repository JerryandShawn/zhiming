"""Site root: new app by default, legacy page as fixed fallback, one switch back, no broken root."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mingjing_core.adapters.web_ui import mount_web_ui, requested_mode

LEGACY = "<html>synthetic legacy page</html>"
NEW = "<html>synthetic new app</html>"


def site(tmp_path: Path, *, built: bool) -> Path:
    (tmp_path / "static/dist/assets").mkdir(parents=True)
    (tmp_path / "static/index.html").write_text(LEGACY, encoding="utf-8")
    if built:
        (tmp_path / "static/dist/index.html").write_text(NEW, encoding="utf-8")
        (tmp_path / "static/dist/assets/app.js").write_text("console.log(1)", encoding="utf-8")
    return tmp_path


def client(root: Path, environment: dict[str, str]) -> tuple[TestClient, str]:
    app = FastAPI()
    mode = mount_web_ui(app, root, environment)
    return TestClient(app, follow_redirects=False), mode


def test_default_root_is_new_app_and_legacy_stays_on_fixed_path(tmp_path):
    web, mode = client(site(tmp_path, built=True), {})
    assert mode == "v4"
    root = web.get("/")
    assert root.status_code == 302 and root.headers["location"] == "/app/"
    assert web.get("/app/").text == NEW and web.get("/app/assets/app.js").status_code == 200
    assert web.get("/legacy/").text == LEGACY


def test_switch_back_serves_legacy_at_root_and_keeps_new_app_reachable(tmp_path):
    web, mode = client(site(tmp_path, built=True), {"MINGJING_WEB_UI": "legacy"})
    assert mode == "legacy"
    assert web.get("/").text == LEGACY and web.get("/legacy/").text == LEGACY
    assert web.get("/app/").text == NEW


def test_missing_build_falls_back_to_legacy_instead_of_a_broken_root(tmp_path):
    web, mode = client(site(tmp_path, built=False), {})
    assert mode == "legacy" and web.get("/").text == LEGACY
    assert web.get("/app/").status_code == 404


def test_unknown_switch_value_fails_at_startup():
    with pytest.raises(ValueError):
        requested_mode({"MINGJING_WEB_UI": "v5"})
