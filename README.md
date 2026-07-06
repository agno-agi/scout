# Scout — a company brain that navigates your knowledge sources

Scout is an open-source company intelligence agent. Instead of ingesting your org's knowledge into a vector store and hoping retrieval works, Scout **navigates** live sources — web, Slack, Google Drive, wiki, CRM, MCP servers — the way a coding agent navigates a repo: list, search, open, follow the link. As it works with you, it files what it learns into its own wiki and CRM, so the brain compounds. Built for teams who want an AI teammate that actually knows the company, on infrastructure they control.

## How it works

Scout is a **single agent** with pluggable **context providers**. Each provider exposes an information source through at most two natural-language tools — `query_<source>` (reads) and `update_<source>` (writes, where supported) — and a sub-agent behind each provider owns the source's quirks (pagination, auth, API shape). Scout's own context stays clean.

| Provider | Active when | Tools |
|---|---|---|
| Web | always (keyless by default) | `query_web` |
| Workspace | always | `query_workspace` — rooted at the Scout repo, so it can answer questions about its own code |
| CRM (Postgres) | always | `query_crm`, `update_crm` — contacts, projects, notes, follow-ups; creates tables on demand |
| Knowledge wiki | always | `query_knowledge`, `update_knowledge` — Scout's prose memory (filesystem by default, Git-backed optional) |
| Voice wiki | always | `query_voice` — read-only, code-managed style guide |
| Slack | `SLACK_BOT_TOKEN` set | `query_slack` — read-only messages, channel history, threads, users |
| Google Drive | `GOOGLE_SERVICE_ACCOUNT_FILE` set | `query_gdrive` — read-only files, folders, contents |
| MCP servers | registered in [`scout/contexts.py`](scout/contexts.py) | one `query_mcp_<slug>` per server (stdio / SSE / streamable-HTTP) |

The learning loop: *"Josh from Anthropic shared a new RLM paper"* → Scout adds Josh to the CRM (`update_crm`), files the paper into the wiki (`update_knowledge`), and links them. The web backend uses the Parallel SDK when `PARALLEL_API_KEY` is set, otherwise Parallel's free public MCP server — zero config.

## Quick start

> **Prerequisite:** Docker Desktop installed and running ([install guide](https://docs.docker.com/desktop/)).

```sh
git clone https://github.com/agno-agi/scout && cd scout

cp example.env .env
# set OPENAI_API_KEY in .env

docker compose up -d --build
```

Scout is now serving at `http://localhost:8000` (API docs at `/docs`). The compose file runs two containers: `scout-db` (Postgres with pgvector) and `scout-api` (uvicorn with hot reload).

## Interfaces

**AgentOS web UI.** Open [os.agno.com](https://os.agno.com?utm_source=github&utm_medium=example-repo&utm_campaign=agent-example&utm_content=scout&utm_term=agentos), log in, click **Add OS** → **Local**, enter `http://localhost:8000`, then **Connect**. Try the pre-configured prompts.

https://github.com/user-attachments/assets/ed49a6c4-926b-4d5d-a105-8a0d15021d3b

**Slack.** Scout is designed to live in Slack as your teammate. Set `SLACK_BOT_TOKEN` and `SLACK_SIGNING_SECRET` — setup walkthrough in [docs/SLACK_CONNECT.md](docs/SLACK_CONNECT.md).

https://github.com/user-attachments/assets/69d1c409-ff94-4c8e-b5e8-64c6e1a0518a

**Terminal.** With a local venv (`./scripts/venv_setup.sh`, then `source .venv/bin/activate`):

```sh
python -m scout             # interactive chat
python -m scout contexts    # list registered contexts + status
```

## Deploy

Scout runs on any cloud; scripts are provided for Railway ([Railway CLI](https://docs.railway.app/guides/cli) + `railway login` required):

```sh
cp .env .env.production        # gitignored; scripts read it first, fall back to .env
./scripts/railway/up.sh        # first-time: Postgres + app service
./scripts/railway/env.sh       # sync .env.production → Railway
./scripts/railway/redeploy.sh  # push code updates
```

Two things to know before your first deploy:

- **JWT is required at prod boot.** Scout enables AgentOS authorization whenever `RUNTIME_ENV=prd` (the default outside dev), and agno 2.7 refuses to serve in prod without a `JWT_VERIFICATION_KEY`. Generate one at [os.agno.com](https://os.agno.com?utm_source=github&utm_medium=example-repo&utm_campaign=agent-example&utm_content=scout&utm_term=agentos) (**Add OS** → **Live** → enable **Token Based Authorization**), paste the full PEM block into `.env.production` (no surrounding quotes), then `./scripts/railway/env.sh`. Opting out means editing `authorization` in [app/main.py](app/main.py) — not recommended for anything holding real company data.
- **The scheduler assumes a single replica.** [`railway.json`](railway.json) currently sets `numReplicas: 2`; with the built-in scheduler enabled, scheduled tasks can fire once per replica. Set `numReplicas: 1` if you rely on scheduled tasks.

After deploying: point your Slack app's Event Subscriptions Request URL at `https://<your-railway-domain>/slack/events`, and for a wiki that survives container restarts, set `WIKI_REPO_URL` + `WIKI_GITHUB_TOKEN` to switch the knowledge wiki to a Git backend automatically — see [docs/WIKI_GIT.md](docs/WIKI_GIT.md). To auto-deploy on push, connect the repo under the service's **Settings → Source** in the Railway dashboard.

## Configuration

Set in `.env` (see [example.env](example.env) for the full annotated list):

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | **Required** — powers every agent and embeddings |
| `JWT_VERIFICATION_KEY` | Required in prod — AgentOS RBAC public key (PEM) |
| `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET` | Both → Slack interface; token alone → read-only Slack context |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Enables the Drive context (`./scripts/google_setup.sh` provisions it) |
| `PARALLEL_API_KEY` | Optional — switches web research to the Parallel SDK backend |
| `WIKI_REPO_URL`, `WIKI_GITHUB_TOKEN` | Both → Git-backed knowledge wiki |
| `AGENTOS_URL` | Scheduler base URL (default `http://127.0.0.1:8000`) |
| `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASS` / `DB_DATABASE` | Postgres — defaults match docker compose |

## Evals

```sh
python -m evals wiring             # code-level invariants (no LLM)
python -m evals                    # behavioral cases, in-process
python -m evals --case <id>        # single case
python -m evals judges             # LLM-scored quality tier
```

See [docs/EVALS.md](docs/EVALS.md) for the full picture.

## Source / links

- Built on [Agno](https://github.com/agno-agi/agno) and [AgentOS](https://docs.agno.com?utm_source=github&utm_medium=example-repo&utm_campaign=agent-example&utm_content=scout&utm_term=docs)
- Setup guides: [Slack](docs/SLACK_CONNECT.md) · [Google Drive](docs/GDRIVE_CONNECT.md) · [MCP servers](docs/MCP_CONNECT.md) · [Git-backed wiki](docs/WIKI_GIT.md)
- Implementation notes for agents and contributors: [AGENTS.md](AGENTS.md)
- License: [Apache-2.0](LICENSE)
