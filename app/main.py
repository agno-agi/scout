"""
Scout API
=========

Production deployment entry point for Scout.

Run:
    python -m app.main
"""

import sys
print("=== Scout startup begin ===", flush=True)

try:
    from os import getenv
    from pathlib import Path
    print("Step 1: Basic imports OK", flush=True)

    from agno.os import AgentOS
    print("Step 2: AgentOS import OK", flush=True)

    from db import get_postgres_db
    print("Step 3: db import OK", flush=True)

    from scout.agents import reasoning_scout, scout, scout_knowledge
    print("Step 4: agents import OK", flush=True)

    from scout.teams import scout_team
    print("Step 5: teams import OK", flush=True)

    # ============================================================================
    # Create AgentOS
    # ============================================================================
    print("Step 6: Creating AgentOS...", flush=True)
    db = get_postgres_db()
    print(f"Step 6a: Database connection: {db}", flush=True)

    agent_os = AgentOS(
        name="Scout",
        tracing=True,
        db=db,
        agents=[scout, reasoning_scout],
        teams=[scout_team],
        knowledge=[scout_knowledge],
        config=str(Path(__file__).parent / "config.yaml"),
    )
    print("Step 7: AgentOS created OK", flush=True)

    app = agent_os.get_app()
    print("Step 8: FastAPI app created OK", flush=True)

except Exception as e:
    print(f"=== STARTUP ERROR ===", flush=True)
    print(f"Error type: {type(e).__name__}", flush=True)
    print(f"Error message: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)

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