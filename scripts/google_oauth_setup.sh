#!/usr/bin/env bash
# Convenience wrapper: load .env on the host and run the OAuth flow.
# Idempotent — re-run any time tokens need refreshing.

set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "No .env found. Copy example.env to .env and fill GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_PROJECT_ID first." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

PYTHON_BIN="${PYTHON_BIN:-python3}"
exec "$PYTHON_BIN" scripts/google_oauth_setup.py
