"""
Scout API
=========

Production deployment entry point for Scout.

Run:
    python -m app.main
"""

import sys
import os

# Force unbuffered output
os.environ["PYTHONUNBUFFERED"] = "1"

def log(msg: str) -> None:
    """Log to both stdout and stderr to ensure visibility."""
    print(msg, flush=True)
    print(msg, file=sys.stderr, flush=True)

log("=== Scout startup begin ===")
log(f"Python version: {sys.version}")
log(f"Working directory: {os.getcwd()}")

try:
    from pathlib import Path
    log("Step 1: Basic imports OK")

    from agno.os import AgentOS
    log("Step 2: AgentOS import OK")

    from db import get_postgres_db
    log("Step 3: db import OK")

    from scout.agents import reasoning_scout, scout, scout_knowledge
    log("Step 4: agents import OK")

    from scout.teams import scout_team
    log("Step 5: teams import OK")

    # ============================================================================
    # Create AgentOS
    # ============================================================================
    log("Step 6: Creating AgentOS...")
    db = get_postgres_db()
    log(f"Step 6a: Database connection: {db}")

    agent_os = AgentOS(
        name="Scout",
        tracing=True,
        db=db,
        agents=[scout, reasoning_scout],
        teams=[scout_team],
        knowledge=[scout_knowledge],
        config=str(Path(__file__).parent / "config.yaml"),
    )
    log("Step 7: AgentOS created OK")

    app = agent_os.get_app()
    log("Step 8: FastAPI app created OK")

except Exception as e:
    log("=== STARTUP ERROR ===")
    log(f"Error type: {type(e).__name__}")
    log(f"Error message: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    log(f"Starting uvicorn on port {port}")
    # Pass app object directly to avoid re-importing the module
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False)



# if __name__ == "__main__":
#     agent_os.serve(
#         app="main:app",
#         reload=getenv("RUNTIME_ENV", "prd") == "dev",
#     )