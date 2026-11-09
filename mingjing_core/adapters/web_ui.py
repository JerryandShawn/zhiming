"""Which page the site root serves: the new web app by default, the legacy page as a fixed fallback.

The new app (web/, built into static/dist) is served under /app/ so its relative asset paths and
service-worker scope stay inside one directory. The legacy page always stays reachable at /legacy/.
Switching the root back to the legacy page is one environment value plus a web restart; nginx is
not touched. A missing build never leaves the root broken: it falls back to the legacy page and
/api/health reports which page is actually served.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

LOG = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
SWITCH_ENV = "MINGJING_WEB_UI"
MODES = ("v4", "legacy")
APP_PATH = "/app/"
LEGACY_PATH = "/legacy/"


def requested_mode(environment: Mapping[str, str] | None = None) -> str:
    value = (os.environ if environment is None else environment).get(SWITCH_ENV, "v4")
    if value not in MODES:
        raise ValueError("MINGJING_WEB_UI 只能是 v4 或 legacy")
    return value


def served_mode(root: Path = ROOT, environment: Mapping[str, str] | None = None) -> str:
    mode = requested_mode(environment)
    if mode == "v4" and not (root / "static/dist/index.html").is_file():
        LOG.warning("New web build missing; serving the legacy page at the site root")
        return "legacy"
    return mode


def mount_web_ui(app: FastAPI, root: Path = ROOT, environment: Mapping[str, str] | None = None) -> str:
    """Validate the switch at startup so a typo fails the service instead of silently changing pages."""
    mode = served_mode(root, environment)
    legacy_index = root / "static/index.html"
    build = root / "static/dist"
    if (build / "index.html").is_file():
        app.mount(APP_PATH.rstrip("/"), StaticFiles(directory=build, html=True), name="web-app")

    @app.get("/")
    async def index() -> Response:
        if mode == "v4":
            return RedirectResponse(APP_PATH, status_code=302)
        return FileResponse(legacy_index)

    @app.get(LEGACY_PATH)
    async def legacy() -> FileResponse:
        return FileResponse(legacy_index)

    app.state.web_ui = mode
    return mode
