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

from db import get_postgres_db
from scout.agent import scout

interfaces: list = []
if (slack_token := getenv("SLACK_TOKEN")) and (slack_signing_secret := getenv("SLACK_SIGNING_SECRET")):
    from agno.os.interfaces.slack import Slack

    interfaces.append(
        Slack(
            agent=scout,
            streaming=True,
            token=slack_token,
            signing_secret=slack_signing_secret,
            resolve_user_identity=True,
        )
    )

agent_os = AgentOS(
    name="Scout",
    agents=[scout],
    tracing=True,
    scheduler=True,
    db=get_postgres_db(),
    interfaces=interfaces,
    config=str(Path(__file__).parent / "config.yaml"),
)

app = agent_os.get_app()

if __name__ == "__main__":
    agent_os.serve(
        app="main:app",
        reload=getenv("RUNTIME_ENV", "prd") == "dev",
    )
