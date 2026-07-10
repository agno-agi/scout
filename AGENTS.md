# AGENTS.md

## Project Overview

Scout is an **enterprise context agent** — a single `agno.Agent` with N `ContextProvider`s. Ships with `WebContextProvider`, `WorkspaceContextProvider` (local files via `agno.tools.Workspace`), `DatabaseContextProvider` (the CRM — user's contacts/projects/notes/follow-ups), two `WikiContextProvider`s (a writable `knowledge` wiki and a read-only `voice` wiki), `SlackContextProvider`, `GDriveContextProvider`, and `MCPContextProvider` (any MCP server → one `query_mcp_<slug>` tool on Scout). GitHub, Gmail, and Calendar land in the next release (were built and verified on the `feat/slack-interface` branch; dropped from the ship slice until we can test end-to-end with real tokens).

## Architecture

```
Scout (single Agent — one LLM hop per turn)
  tools = <query_|update_ tools from every registered ContextProvider> + list_contexts
```

Every source is a `ContextProvider`. The database is a provider too: `DatabaseContextProvider` exposes `query_crm` (reads) + `update_crm` (writes), each backed by a dedicated sub-agent so the read path never sees the write engine.

## ContextProvider

`agno.context.provider` defines the base. Every external source subclasses `ContextProvider` and implements:

- `query(question) -> Answer` / `aquery(question) -> Answer` — natural-language read
- `status() -> Status` / `astatus() -> Status` — is the source reachable?

Providers that support writes override `aupdate(instruction) -> Answer` (and optionally `update`). The base raises `NotImplementedError`; `_update_tool()` translates that into a readable "<name> is read-only" error so calling agents see a clean failure. Today only `DatabaseContextProvider` overrides it.

`mode` controls how the provider surfaces itself to the calling agent:

| Mode | Exposure |
|---|---|
| `default` | The provider's recommended exposure. Each subclass decides. |
| `agent` | One `query_<id>` tool wrapping a sub-agent. |
| `tools` | The underlying tools directly. |

`model` swaps the model used by the internal sub-agent (when one is built). `instructions()` returns mode-aware usage guidance for the calling agent.

The full type set:
- `Status(ok: bool, detail: str = "")`
- `Document(id, name, uri=None, source=None, snippet=None)` — a piece of content
- `Answer(results: list[Document] = [], text: str | None = None)` — what `query()` returns

## One write surface

| Write surface | Owner | Call |
|---|---|---|
| `scout_*` user-data tables | `DatabaseContextProvider` write sub-agent | `update_crm(instruction)` — SQL DDL + DML, scoped to the `scout` schema (`get_sql_engine()`) |

Everything else reads. The CRM read sub-agent uses `get_readonly_engine()` (PostgreSQL's `default_transaction_read_only`). The scout engine has a `before_cursor_execute` hook that rejects any DDL/DML targeting `public` or `ai` — so even if Scout is tricked into calling `update_crm` with an out-of-schema statement, the engine rejects it.

## Interfaces

Chat surfaces beyond AgentOS's built-in UI. Wired in `app/main.py` and passed to `AgentOS(interfaces=...)`.

| Interface | Trigger | Notes |
|---|---|---|
| Slack | `SLACK_BOT_TOKEN` **and** `SLACK_SIGNING_SECRET` set | Webhook at `/slack/events`; each Slack thread → a persistent session. `resolve_user_identity=True` maps Slack user IDs to names. Setup: [`docs/SLACK_CONNECT.md`](docs/SLACK_CONNECT.md). |

Both Slack env vars must be set for the interface to light up; otherwise `interfaces=[]` and Scout runs headless + on AgentOS. We explicitly pass `token=SLACK_BOT_TOKEN` because agno's default env-var read is `SLACK_TOKEN` — keeping the `_BOT_` name is intentional.

## Structure

```
scout/
├── __init__.py
├── __main__.py                     # CLI: chat | contexts
├── agent.py                        # The single `scout` Agent
├── instructions.py                 # Scout-tuned prompts: SCOUT_INSTRUCTIONS + CRM read/write
├── settings.py                     # Runtime objects: agent_db + default_model() factory
└── contexts.py                     # create/get/update/close_context_providers + list_contexts tool + status row helpers

# The ContextProvider library (base ABC + shipped providers) lives in `agno.context`
# as of agno 2.6 — see `agno.context.{database,gdrive,mcp,slack,web,wiki,workspace}`.

app/
├── main.py                         # AgentOS entry (lifespan wires contexts; Slack interface if env set)
├── router.py                       # /contexts/* endpoints
└── config.yaml

db/
├── session.py                      # get_sql_engine (guarded) / get_readonly_engine / get_postgres_db / create_knowledge
├── url.py                          # DB URL builder
└── tables.py                       # Canonical DDL: scout_contacts / projects / notes / followups

wiki/
├── knowledge/                      # Prose memory Scout files into (gitignored except README)
└── voice/                          # Code-managed style guide (committed, read-only to Scout)

evals/
├── cases.py                        # Behavioral Case dataclass + CASES tuple
├── runner.py                       # In-process transport + fixtures
├── wiring.py                       # Code-level invariants, no LLM (W1-W6)
├── judges.py                       # LLM-scored quality tier
└── __main__.py                     # CLI dispatch
```

## Commands

```bash
./scripts/venv_setup.sh && source .venv/bin/activate
./scripts/format.sh                   # Format code
./scripts/validate.sh                 # ruff + mypy

# CLI
python -m scout                       # Chat
python -m scout contexts              # List contexts + status

# Tables (also run automatically on app startup)
python -m db.tables

# Evals
python -m evals wiring                # Code-level invariants (no LLM)
python -m evals                       # Behavioral cases, in-process
python -m evals --case <id>           # Single case
python -m evals --verbose             # Response + tool previews
python -m evals judges                # LLM-scored quality tier
```

### Environment loading for CLI work

Secrets live in `.env`. Anything that hits OpenAI / Parallel from the host (`python -m evals`, etc.) needs `.env` loaded:

1. **Prefer direnv:** `direnv allow .` once per repo.
2. **Fallback:** `set -a; source .env; set +a; python -m evals`
3. **Per-invocation (Bash tool):** `set -a && source .env && set +a && ...`

Docker picks up `.env` automatically via `docker compose`, so code inside `scout-api` has everything. Only direct host-shell invocations need the explicit source.

## Testing & Evals

**Static checks** — `./scripts/validate.sh` runs ruff + mypy. Both run even if one fails; the script exits non-zero if either reports problems, warns if no virtualenv is active.

**Three eval tiers** under `python -m evals`:

| Tier | Command | Speed | LLM? | What it catches |
|---|---|---|---|---|
| Wiring | `python -m evals wiring` | <1s | No | Scout's tool shape drifts (bare SQL on Scout, CRM provider loses `update_crm`, schema guard removed, default `user_id` sentinel regresses, GDrive backend drops shared-drive coverage, MCP lifecycle breaks, voice gains a write tool, `scout_followups` falls out of canonical DDL) |
| Behavioral | `python -m evals` | ~3min | Yes (gpt-5.6-sol) | Scout picks the wrong tool, over-tools, responses miss expected substrings |
| Judges | `python -m evals judges` | ~1min/case | Yes | Answer quality a regex can't express |

Flags: `--case <id>` narrows to one case; `--verbose` prints response + tool previews. Details: [`docs/EVALS.md`](docs/EVALS.md).

**Fixing a failing case** — paste [`docs/EVAL_AND_IMPROVE.md`](docs/EVAL_AND_IMPROVE.md) into a fresh agent session. It runs the suite, diagnoses each failure (agent bug vs. stale assertion vs. runner bug), fixes what's in scope, and flags what isn't.

## Contexts

`scout/contexts.py::create_context_providers()` is the env-driven factory. The app lifespan calls it at startup to warm a module-level cache; `get_context_providers()` lazy-builds on first access. `update_context_providers()` swaps the cached list in place (used by eval fixtures). The web provider is always on; others opt-in via env.

Registered provider set (in order):

| Provider | Trigger | Notes |
|---|---|---|
| `WebContextProvider` | always | Backend picked below |
| `WorkspaceContextProvider` | always | Read-only; `Workspace` scoped to `SCOUT_FS_ROOT` in `scout/contexts.py` (the scout repo — Scout answers questions about itself). One `query_workspace` tool that routes through a tuned sub-agent. |
| `DatabaseContextProvider` | always | CRM — the user's contacts/projects/notes/follow-ups. Exposes `query_crm` + `update_crm`; read path uses `get_readonly_engine()`, write path uses `get_sql_engine()` (scout-schema-guarded). |
| `WikiContextProvider` (knowledge) | always | Prose memory — runbooks, design notes, learnings. `FileSystemBackend` on `wiki/knowledge/` by default; swap to `GitBackend` for durability + audit trail (see [`docs/WIKI_GIT.md`](docs/WIKI_GIT.md)). Tools: `query_knowledge` + `update_knowledge`. |
| `WikiContextProvider` (voice) | always | Read-only (`write=False`) style guide for external content. Filesystem-backed on `wiki/voice/`; rules are code-managed (PR, not agent edits). Tool: `query_voice` only — no `update_voice`. |
| `SlackContextProvider` | `SLACK_BOT_TOKEN` | Read-only; search + channel history + threads. Sending is disabled (Slack interface handles posting). Setup: [`docs/SLACK_CONNECT.md`](docs/SLACK_CONNECT.md) |
| `GDriveContextProvider` | `GOOGLE_SERVICE_ACCOUNT_FILE` | Read-only; Scout authenticates as its own service account (no user impersonation). Setup: [`docs/GDRIVE_CONNECT.md`](docs/GDRIVE_CONNECT.md) or `./scripts/google_setup.sh` |
| `MCPContextProvider` | wired in `scout/contexts.py` | One per server; transports `stdio`/`sse`/`streamable-http`. Sub-agent instructions rebuilt from `list_tools()` at connect. `aclose()` closes the session on shutdown. Setup: [`docs/MCP_CONNECT.md`](docs/MCP_CONNECT.md) |

`create_context_providers()` dedupes by `id` globally (first wins, warns on collision) so Scout never ends up with two `query_<id>` tools sharing a name.

Web backend selection:

| Trigger | Backend |
|---|---|
| `PARALLEL_API_KEY` set | `ParallelBackend` (Parallel SDK — `web_search` + `web_extract`) |
| unset | `ParallelMCPBackend` (keyless, via Parallel's public MCP — `web_search` + `web_fetch`) |

## User Data Tables

Shipped tables under the `scout` schema (created on first startup via `db/tables.py`). All carry `id SERIAL PK`, `user_id TEXT NOT NULL`, `created_at TIMESTAMPTZ DEFAULT NOW()`.

| Table | Purpose | Domain columns |
|---|---|---|
| `scout_contacts` | People | `name`, `emails TEXT[]`, `phone`, `tags TEXT[]`, `notes` |
| `scout_projects` | Things in motion | `name`, `status`, `tags TEXT[]` |
| `scout_notes` | Free-form notes | `title`, `body`, `tags TEXT[]`, `source_url` |
| `scout_followups` | Things to come back to | `title`, `notes`, `due_at TIMESTAMPTZ`, `status` (`pending` / `done` / `dropped`), `tags TEXT[]` |

Beyond these four, the CRM provider's write sub-agent creates new `scout_*` tables on demand — always in the `scout` schema, always with the standard columns. `scout_followups` is the closed-loop primitive: a future scheduled cron reads `due_at <= NOW() AND status = 'pending'` to surface what needs attention each morning.

## Tools on Scout

| Surface | Tools |
|---------|-------|
| Scout (single Agent) | `query_<id>` + `update_<id>` for each registered provider (`provider.get_tools()`), `list_contexts` |
| CRM read sub-agent | `SQLTools` (**read-only engine**, `scout` schema) |
| CRM write sub-agent | `SQLTools` (scout engine, **schema-guarded** to `scout`) |

**Per-provider tools are built by the registry.** `scout.contexts.create_context_providers()` builds the provider list and caches it on the module; `get_context_providers()` reads it (lazy-builds on first access). Scout's `tools=scout_tools` is a callable (`cache_callables=False`), so agno resolves the tool list from the current registry on every run. The app lifespan calls `create_context_providers()` once at startup to warm the cache and log which backend was selected; eval fixtures swap providers via `update_context_providers`.

## API Endpoints

On top of AgentOS's defaults (`/agents/scout/runs`, `/health`, …):

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/contexts` | GET | List every registered context + status |
| `/contexts/{id}/status` | GET | One context's status |
| `/contexts/{id}/query` | POST | Debug: ask one context directly |

## Model

Scout and every provider sub-agent run on `OpenAIResponses(id="gpt-5.6-sol")` via `agno.models.openai`, built through the `default_model()` factory in `scout/settings.py` (fresh instance per agent — avoids shared-state footguns). Each provider takes a `model=` kwarg so `agno.context` stays portable — no hard OpenAI dep inside the library.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | **Yes** | GPT-5.6-sol for every agent |
| `PARALLEL_API_KEY` | No | Selects `ParallelBackend` (Parallel SDK). Without it, web falls back to `ParallelMCPBackend` (keyless). |
| `SLACK_BOT_TOKEN` | No | Bot User OAuth Token. Pair with `SLACK_SIGNING_SECRET` to enable Slack interface. |
| `SLACK_SIGNING_SECRET` | No | Slack request signing secret. Pair with `SLACK_BOT_TOKEN`. |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | No | Path to Scout's Google service-account JSON key. Activates the Drive context provider. |
| `DB_HOST / PORT / USER / PASS / DATABASE` | No | PostgreSQL config. Compose defaults work locally. |
| `RUNTIME_ENV` | No | `dev` for hot reload (compose sets this); `prd` enables JWT-gated endpoints. |
| `AGENTOS_URL` | No | Scheduler base URL; defaults to `http://127.0.0.1:8000`. |

## Conventions

### ContextProvider

Every external source subclasses `ContextProvider` (in `agno.context.provider`). Each provider lives in its own module under `agno.context.<kind>` — the class is in `provider.py`, pluggable backends are flat modules in the same folder (e.g. `agno.context.web.parallel`). Implementation is agentic by default — `_build_agent()` wraps a sub-agent with backend tools when needed (lazy). Each provider exposes its tools via `.get_tools()`; Scout wires them directly via the `scout_tools()` callable factory.

### Database

- Use `get_postgres_db()` from the `db` module for agent session storage.
- Use `get_sql_engine()` for tools that need to write to the `scout` schema (CRM write sub-agent, migrations). This engine has a guard that rejects writes to `public` / `ai`.
- Use `get_readonly_engine()` for tools that should never write (CRM read sub-agent). PostgreSQL's `default_transaction_read_only` enforces this at the DB level.
- `db/tables.py` runs at startup; safe to rerun.

### Imports

```python
from db import db_url, get_postgres_db, get_sql_engine, get_readonly_engine, SCOUT_SCHEMA
from scout.agent import scout
from scout.settings import agent_db
from scout.contexts import create_context_providers, get_context_providers, update_context_providers, list_contexts, status_row, astatus_row
from agno.context import ContextBackend, ContextProvider, ContextMode, Answer, Document, Status
from agno.context.database import DatabaseContextProvider
from agno.context.workspace import WorkspaceContextProvider
from agno.context.wiki import FileSystemBackend, GitBackend, WikiContextProvider
from agno.context.gdrive import GDriveContextProvider
from agno.context.mcp import MCPContextProvider
from agno.context.slack import SlackContextProvider
from agno.context.web import WebContextProvider
from agno.context.web.parallel import ParallelBackend
from agno.context.web.parallel_mcp import ParallelMCPBackend
```
