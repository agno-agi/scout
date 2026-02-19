"""
Scout AgentOS
========

Production deployment entry point for Scout.

Run:
    python -m app.main
"""

from os import getenv
from pathlib import Path

from agno.os import AgentOS

from scout.agent import scout
from db import get_postgres_db

# ---------------------------------------------------------------------------
# Create AgentOS
# ---------------------------------------------------------------------------
agent_os = AgentOS(
    name="Scout",
    agents=[scout],
    tracing=True,
    scheduler=True,
   scheduler_base_url=getenv("SCHEDULER_BASE_URL", "http://localhost:8000"),
    db=get_postgres_db(),
    config=str(Path(__file__).parent / "config.yaml"),
)

app = agent_os.get_app()

if __name__ == "__main__":
    agent_os.serve(
        app="main:app",
        reload=getenv("RUNTIME_ENV", "prd") == "dev",
    )
