"""Run with `python -m web.tests.fixture_server` from the repository root."""

import importlib
import json
import os


def main():
    for name in list(os.environ):
        if name.endswith("_API_KEY"):
            os.environ.pop(name, None)
    os.environ.update(
        LANGSMITH_TRACING="false",
        MINGJING_MODEL_PORT="",
        MODELS_CONFIG="",
        MINGJING_TOKEN="synthetic-frontend-token",
        MINGJING_OWNER_ID="frontend-owner",
        ZHIMING_TOKEN_OWNERS=json.dumps({"synthetic-frontend-other": "frontend-other"}),
    )
    importlib.import_module("web.tests.fixture_app").serve()


if __name__ == "__main__":
    main()
