"""
Scout API
=========

Production deployment entry point for Scout.

Run:
    python -m app.main
"""

from os import getenv
from pathlib import Path

from agno.os import AgentOS

from db import get_postgres_db
from scout.agents import reasoning_scout, scout, scout_knowledge
from scout.teams import scout_team

# ============================================================================
# Create AgentOS
# ============================================================================
agent_os = AgentOS(
    name="Scout",
    tracing=True,
    db=get_postgres_db(),
    agents=[scout, reasoning_scout],
    teams=[scout_team],
    knowledge=[scout_knowledge],
    config=str(Path(__file__).parent / "config.yaml"),
)

app = agent_os.get_app()

# if __name__ == "__main__":
#     agent_os.serve(
#         app="main:app",
#         reload=getenv("RUNTIME_ENV", "prd") == "dev",
#     )

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))  # <-- Railway dynamically sets this
    reload = os.environ.get("RUNTIME_ENV", "prd") == "dev"

    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=reload)