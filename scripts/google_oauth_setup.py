"""One-time OAuth setup for Gmail + Calendar context providers.

Run this on the HOST (not inside Docker) after setting GOOGLE_CLIENT_ID,
GOOGLE_CLIENT_SECRET, and GOOGLE_PROJECT_ID in .env.

Opens your browser for each scope, then writes:
  .scout/gmail_token.json
  .scout/calendar_token.json

Compose bind-mounts the repo into scout-api so the container picks up
the tokens automatically. Re-run this script if tokens expire or if
you change scopes.

Usage:
    set -a && source .env && set +a
    python scripts/google_oauth_setup.py
"""

from __future__ import annotations

import json
import sys
from os import getenv
from pathlib import Path

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print(
        "google_auth_oauthlib is missing. Install it on the host:\n"
        "    pip install google-auth-oauthlib",
        file=sys.stderr,
    )
    sys.exit(1)


REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = REPO_ROOT / ".scout"

# gmail.modify covers read AND label changes (mark read/unread, apply labels).
# It does NOT include send/compose/delete — that needs gmail.send/.compose.
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def _client_config() -> dict:
    client_id = getenv("GOOGLE_CLIENT_ID")
    client_secret = getenv("GOOGLE_CLIENT_SECRET")
    project_id = getenv("GOOGLE_PROJECT_ID", "scout-local")
    if not client_id or not client_secret:
        print(
            "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set.\n"
            "Load .env first:  set -a && source .env && set +a",
            file=sys.stderr,
        )
        sys.exit(1)
    return {
        "installed": {
            "client_id": client_id,
            "project_id": project_id,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": client_secret,
            "redirect_uris": ["http://localhost"],
        }
    }


def _run_flow(scopes: list[str], out_path: Path, label: str) -> None:
    print(f"\n--- {label} ---")
    print(f"Scopes: {', '.join(scopes)}")
    flow = InstalledAppFlow.from_client_config(_client_config(), scopes)
    creds = flow.run_local_server(port=0, open_browser=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(creds.to_json())
    print(f"Wrote {out_path.relative_to(REPO_ROOT)}")


def main() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _run_flow(GMAIL_SCOPES, STATE_DIR / "gmail_token.json", "Gmail")
    _run_flow(CALENDAR_SCOPES, STATE_DIR / "calendar_token.json", "Calendar")
    print("\nDone. Restart scout-api to pick up the new tokens:")
    print("    docker compose restart scout-api")


if __name__ == "__main__":
    main()
