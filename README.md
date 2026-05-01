# Scout: Company Intelligence Agent

Scout is an open-source company intelligence agent. It navigates live information sources (web, slack, drive, wiki, CRM, MCP servers) to assemble context on demand - and builds its own wiki and CRM as it learns about your company.

YC's Summer 2026 RFS named "Company Brain" and "AI Operating System for Companies" — the same idea from two angles: pull knowledge out of fragmented sources and turn it into something AI can act on. The brain is the data layer. The OS runs on top of it. Neither exists as a finished product today, but the pieces do.

Scout stitches them together using patterns that already work: **navigation over search**, **context providers**, agentic SQL, and persistent memory.

**Navigation over search.** The default move when working with knowledge sources is to ingest everything into a vector db, chunk, embed, and pray. There are many reasons this doesn't work. Coding agents figured out the right approach. They navigate: `ls`, `grep`, open the file, follow the import. Scout does the same thing across Slack, Drive, and the rest.

**Scout maintains its own wiki and CRM.** Most information Scout learns from working with you is perfect for a wiki and CRM. *"Josh from Anthropic shared a new RLM paper"*. Scout adds Josh to the CRM, parses the paper into the wiki, and links them.

## Quick start

> **Prerequisite:** Docker Desktop installed and running ([install guide](https://docs.docker.com/desktop/)).

```sh
git clone https://github.com/agno-agi/scout && cd scout

cp example.env .env
# set OPENAI_API_KEY in .env

docker compose up -d --build
```

Scout is now running at `http://localhost:8000`.

## Chat with Scout

1. Open [os.agno.com](https://os.agno.com?utm_source=github&utm_medium=example-repo&utm_campaign=agent-example&utm_content=scout&utm_term=agentos) and log in.
2. Click **Add OS**, choose **Local**, enter **http://localhost:8000**, then **Connect**.
3. Try the pre-configured prompts.

https://github.com/user-attachments/assets/ed49a6c4-926b-4d5d-a105-8a0d15021d3b

## Scout UI — chat + live dashboard in your browser

A Next.js dashboard that pairs Scout chat with a real Google Calendar week grid, an interactive Gmail unread list (open thread, mark read/unread), a Postgres-backed follow-ups widget, and an LLM-summarized web news card. Streaming chat over SSE, light/dark theme, draggable splitter.

```sh
docker compose up -d --build
# Open http://localhost:3000
```

Setup, architecture, and troubleshooting in [`web/README.md`](web/README.md).

## Chat with Scout in Slack

Scout is designed to live in Slack as your teammate. Follow [docs/SLACK_CONNECT.md](docs/SLACK_CONNECT.md) to add Scout to your slack workspace.

https://github.com/user-attachments/assets/69d1c409-ff94-4c8e-b5e8-64c6e1a0518a

## How Scout works

Scout is a single agent with multiple context providers. Each context provider exposes 2 natural-language tools to interact with an information source:

- `query_<source>`: reads
- `update_<source>`: writes (when supported)

This thin layer solves three problems that hit any agent with a diverse tool surface: context pollution from too many tools, degrading performance from overlapping scopes, and the main agent forgetting its job because its context is all tool quirks.

The win is that **a sub-agent behind each provider owns the source's quirks**. Scout sees `query_slack`. Behind it, a sub-agent knows to look up the user before DMing, paginate by cursor, and prefer `conversations.replies` for threads. Scout's context never sees any of that.

> *"Find the latest benchmark numbers for model X."* → `query_web`, cites sources.
>
> *"Save that as a note."* → `update_crm` → write sub-agent `INSERT`s into `scout.scout_notes`.
>
> *"File a runbook for incident response."* → `update_knowledge` → wiki sub-agent writes a markdown page under `wiki/knowledge/runbooks/`.
>
> *"Track my coffee consumption: flat white, extra shot."* → `update_crm` → write sub-agent creates `scout.scout_coffee_orders` and inserts the row. Schema on demand.
>
> *"Draft a Slack message announcing the launch."* → `query_voice` first to load the style guide, then drafts in that voice.

## Context Providers

A `ContextProvider` exposes an information source to the agent.

| Provider | Trigger | Tools |
|---|---|---|
| **`WebContextProvider`** | always on | `query_web` |
| **`WorkspaceContextProvider`** | always on | `query_workspace` — rooted at the scout repo, so Scout can answer questions about its own codebase |
| **`DatabaseContextProvider`** (CRM) | always on | `query_crm`, `update_crm` — contacts, projects, notes, follow-ups |
| **`WikiContextProvider`** (knowledge) | always on | `query_knowledge`, `update_knowledge` — Scout's prose memory |
| **`WikiContextProvider`** (voice) | always on | `query_voice` — code-managed style guide for emails, Slack, X, long-form |
| **`SlackContextProvider`** | `SLACK_BOT_TOKEN` | `query_slack` — read-only access to messages, channel history, threads, users |
| **`GDriveContextProvider`** | `GOOGLE_SERVICE_ACCOUNT_FILE` | `query_gdrive` — read-only access to files, folders, contents |
| **`MCPContextProvider`** | per-server in [`scout/contexts.py`](scout/contexts.py) | one `query_mcp_<slug>` per registered server (stdio / SSE / streamable-HTTP) |

The **Web backend** uses the Parallel SDK when `PARALLEL_API_KEY` is set, otherwise the free Parallel MCP server.

**Setup guides:**
- [Slack](docs/SLACK_CONNECT.md)
- [Google Drive](docs/GDRIVE_CONNECT.md)
- [MCP Servers](docs/MCP_CONNECT.md)
- [Git-backed wiki](docs/WIKI_GIT.md)

## Evals

```sh
python -m evals wiring             # code-level invariants (no LLM)
python -m evals                    # behavioral cases, in-process
python -m evals --case <id>        # single case
python -m evals judges             # LLM-scored quality tier
```

See [`docs/EVALS.md`](docs/EVALS.md) for the full picture.

## Deploy to Railway

Scout runs on any cloud provider. We provide scripts for Railway.

**Prereqs:** [Railway CLI](https://docs.railway.app/guides/cli) installed and `railway login` run.

### 1. Set up your production env

```sh
cp .env .env.production
```

Edit `.env.production` if any values should differ from local (e.g. a different Slack workspace, larger model budget, production-only credentials). The Railway scripts read `.env.production` first and fall back to `.env`.

> `.env.production` is gitignored. Don't commit it.

### 2. Provision and deploy

```sh
./scripts/railway/up.sh        # first-time: Postgres + app service
```

Scripts to update env and redeploy after code changes

```sh
./scripts/railway/env.sh       # sync .env.production → Railway
./scripts/railway/redeploy.sh  # push code updates after up.sh
```

### 3. Your first deploy will fail. That's expected.

Production endpoints require RBAC authorization by default (Scout enables it when `RUNTIME_ENV=prd`). Without a `JWT_VERIFICATION_KEY`, the app refuses to serve traffic. Scout's job is to keep your company data off the public web. The fix is to generate a key from AgentOS and set it in your env.

### 4. Get your verification key

1. Open [os.agno.com](https://os.agno.com?utm_source=github&utm_medium=example-repo&utm_campaign=agent-example&utm_content=scout&utm_term=agentos), click **Add OS** → **Live**, and enter your Railway domain. 2. Enable **Token Based Authorization**
3. Paste the public key into `.env.production` (the full PEM block, no surrounding quotes):

```sh
JWT_VERIFICATION_KEY=-----BEGIN PUBLIC KEY-----
MIIBIjANBgkq...
-----END PUBLIC KEY-----
```

4. Sync and redeploy:

```sh
./scripts/railway/env.sh
```

Railway will auto-deploy when values change, but if you need to redeploy manually:

```sh
./scripts/railway/redeploy.sh
```

Once redeployed, AgentOS connects, Scout starts serving requests, and every API call (UI, Slack, scheduled tasks) runs signed-and-verified from here on. The Agno control plane handles JWT issuance, session management, traces, metrics, and the web UI. Scout just verifies the JWTs it sees. See the [AgentOS Security docs](https://docs.agno.com/agent-os/security/overview) for details.

### Opting out of JWT verification (not recommended)

If you must run production without auth (e.g. inside a private VPC behind another auth layer), flip `authorization=False` at [app/main.py:67](app/main.py:67) and redeploy. We strongly recommend keeping authorization on for any deploy that holds real company data. Without it, anyone who guesses your Railway domain can query your CRM, wiki, and connected sources.

### 5. Point Slack at the new URL

1. Copy your Railway domain.
2. In your [Slack App settings](https://api.slack.com/apps) → **Event Subscriptions**, set the Request URL to `https://<your-railway-domain>/slack/events`.
3. Wait for Slack to verify.

If you were running ngrok locally, you can shut it down. Slack will route to the deployed instance.

### 6. Use GitHub for the knowledge wiki (recommended)

The filesystem wiki resets on every container restart. For production, swap to a Git-backed wiki so pages persist with an audit trail and reviewers can comment. Full setup guide in [docs/WIKI_GIT.md](docs/WIKI_GIT.md).

1. Create a private wiki repo and mint a fine-grained PAT (Contents: Read and write, scoped to that one repo).
2. Add to `.env.production`:

```sh
WIKI_REPO_URL=https://github.com/your-org/your-wiki.git
WIKI_GITHUB_TOKEN=github_pat_***
```

3. Sync and redeploy:

```sh
./scripts/railway/env.sh
```

Scout detects both env vars on startup and switches the knowledge wiki to `GitBackend` automatically — no code changes needed. On boot you'll see `Knowledge wiki: GitBackend (<repo_url>)` in the logs.

Railway will auto-deploy when values change, but if you need to redeploy manually:

```sh
./scripts/railway/redeploy.sh
```

### 7. Connect Railway to GitHub for auto-deploys

So far every code update needs `./scripts/railway/redeploy.sh`. To auto-deploy on every push to `main` instead, connect the repo in Railway:

1. Open the Railway dashboard → your project → the **scout** service → **Settings**.
2. Under **Source**, click **Connect Repo** and pick the repo where Scout lives.
3. Set the deploy branch to `main`, then save.

Every push to `main` now triggers a fresh build and rolling deploy. `./scripts/railway/env.sh` is still how you sync `.env.production` changes.

> Scout deploys with **2 replicas** by default — configured in [`railway.json`](railway.json) (`"numReplicas": 2`, `4Gi` memory, 2 vCPU per replica). Two replicas give you zero-downtime rolling deploys and modest fault tolerance. Bump `numReplicas` and `limits` as your usage grows.

## What's next

- **Scheduled tasks.** Scout surfaces pending follow-ups automatically (e.g. a daily 8am summary of `scout_followups` where `due_at <= NOW()`).
- **Proactive provider actions.** `update_slack`, `update_github` running on cron, not just on demand.
- **GitHub, Gmail, Calendar providers.** Built and verified on `feat/slack-interface`. Landing in the next release once we've tested with real tokens.

## Architecture

Built on [Agno](https://github.com/agno-agi/agno) and AgentOS ([docs.agno.com](https://docs.agno.com?utm_source=github&utm_medium=example-repo&utm_campaign=agent-example&utm_content=scout&utm_term=docs)).

Implementation notes: [AGENTS.md](AGENTS.md).
