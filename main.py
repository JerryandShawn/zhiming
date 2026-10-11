"""Production web entrypoint: the independent Core v3."""
from mingjing_core.adapters.web import create_app

app = create_app()
