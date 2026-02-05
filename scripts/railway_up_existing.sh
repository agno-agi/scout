#!/bin/bash

############################################################################
#
#    Agno Railway Deployment (Existing Project + Auto-railway.toml)
#
#    Usage: ./scripts/railway_up.sh
#
#    Prerequisites:
#      - Railway CLI installed
#      - Logged in via `railway login`
#      - OPENAI_API_KEY set in environment
#
############################################################################

set -e

# Colors
ORANGE='\033[38;5;208m'
DIM='\033[2m'
BOLD='\033[1m'
NC='\033[0m'

echo ""
echo -e "${ORANGE}"
cat << 'BANNER'
     █████╗  ██████╗ ███╗   ██╗ ██████╗
    ██╔══██╗██╔════╝ ████╗  ██║██╔═══██╗
    ███████║██║  ███╗██╔██╗ ██║██║   ██║
    ██╔══██║██║   ██║██║╚██╗██║██║   ██║
    ██║  ██║╚██████╔╝██║ ╚████║╚██████╔╝
    ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝ ╚═════╝
BANNER
echo -e "${NC}"

# Load .env if it exists
if [[ -f .env ]]; then
    set -a
    source .env
    set +a
    echo -e "${DIM}Loaded .env${NC}"
fi

# Preflight
if ! command -v railway &> /dev/null; then
    echo "Railway CLI not found. Install: https://docs.railway.app/guides/cli"
    exit 1
fi

if [[ -z "$OPENAI_API_KEY" ]]; then
    echo "OPENAI_API_KEY not set. Add to .env or export it."
    exit 1
fi

# --- Link to existing project ---
EXISTING_PROJECT_ID="65105ec7-fe2c-45e4-acb8-045e7c1e2659"  # Replace with your Railway project ID
echo -e "${BOLD}Linking to existing project ${EXISTING_PROJECT_ID}...${NC}"
railway link --project $EXISTING_PROJECT_ID

# --- Deploy PgVector database ---
echo ""
echo -e "${BOLD}Deploying PgVector database...${NC}"
railway deploy -t 3jJFCA
echo -e "${DIM}Waiting 10s for database...${NC}"
sleep 10

# --- Ensure scout service exists ---
SERVICE_NAME="scout"
if ! railway service ls | grep -q "^$SERVICE_NAME"; then
    echo -e "${BOLD}Creating application service ${SERVICE_NAME}...${NC}"
    railway add --service $SERVICE_NAME \
        --variables 'DB_USER=${{pgvector.PGUSER}}' \
        --variables 'DB_PASS=${{pgvector.PGPASSWORD}}' \
        --variables 'DB_HOST=${{pgvector.PGHOST}}' \
        --variables 'DB_PORT=${{pgvector.PGPORT}}' \
        --variables 'DB_DATABASE=${{pgvector.PGDATABASE}}' \
        --variables "DB_DRIVER=postgresql+psycopg" \
        --variables "WAIT_FOR_DB=True" \
        --variables "DATA_DIR=/data" \
        --variables "OPENAI_API_KEY=${OPENAI_API_KEY}" \
        --variables "PORT=8000"
else
    echo -e "${DIM}Service ${SERVICE_NAME} already exists, skipping creation.${NC}"
fi

# --- Ensure railway.toml has scout service for dashboard ---
if [[ ! -f railway.toml ]]; then
    echo -e "${DIM}railway.toml not found, creating...${NC}"
    touch railway.toml
fi

if ! grep -q "\[services.$SERVICE_NAME\]" railway.toml; then
    echo -e "${DIM}Adding $SERVICE_NAME service to railway.toml...${NC}"
    cat << TOML_APPEND >> railway.toml

[services.$SERVICE_NAME]
name = "$SERVICE_NAME"
path = "."
start = "uv run app.main:app --host 0.0.0.0 --port 8000"
TOML_APPEND
else
    echo -e "${DIM}$SERVICE_NAME already registered in railway.toml.${NC}"
fi

# --- Deploy the application ---
echo ""
echo -e "${BOLD}Deploying application ${SERVICE_NAME}...${NC}"
railway up --service $SERVICE_NAME -d

# --- Ensure domain exists ---
echo ""
echo -e "${BOLD}Creating domain for ${SERVICE_NAME}...${NC}"
railway domain --service $SERVICE_NAME || echo -e "${DIM}Domain may already exist.${NC}"

echo ""
echo -e "${BOLD}Done.${NC} Domain may take ~5 minutes."
echo -e "${DIM}Logs: railway logs --service $SERVICE_NAME${NC}"
echo ""